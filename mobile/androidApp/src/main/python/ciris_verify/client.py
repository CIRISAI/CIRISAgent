"""CIRISVerify client - Python FFI wrapper for the verification binary.

This module provides a high-level Python interface to the CIRISVerify
Rust binary via C FFI. It handles JSON encoding/decoding and type conversion.
"""

import os
import json
import ctypes
import asyncio
import hashlib
import platform
import socket
from pathlib import Path
from typing import Optional, Set
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

from .types import (
    LicenseStatus,
    LicenseTier,
    LicenseDetails,
    MandatoryDisclosure,
    DisclosureSeverity,
    LicenseStatusResponse,
    CapabilityCheckResult,
    FileIntegrityResult,
    HardwareType,
    ValidationStatus,
    SourceDetails,
    AttestationData,
)
from .exceptions import (
    BinaryNotFoundError,
    BinaryTamperedError,
    VerificationFailedError,
    TimeoutError as CIRISTimeoutError,
    CommunicationError,
)


# Default paths for the CIRISVerify binary by platform
DEFAULT_BINARY_PATHS = {
    "Linux": [
        "/usr/lib/ciris/libciris_verify.so",
        "/usr/local/lib/ciris/libciris_verify.so",
        "./target/release/libciris_verify_ffi.so",
    ],
    "Darwin": [
        "/usr/local/lib/ciris/libciris_verify.dylib",
        "./target/release/libciris_verify_ffi.dylib",
    ],
    "Windows": [
        "C:\\Program Files\\CIRIS\\ciris_verify.dll",
        ".\\target\\release\\ciris_verify_ffi.dll",
    ],
    "iOS": [
        # iOS framework bundle paths (relative to app bundle)
        # The actual path is resolved at runtime via _find_ios_framework()
    ],
}

# Map Rust LicenseStatus enum variants (serde string serialization) to Python IntEnum
_RUST_STATUS_MAP = {
    "LicensedProfessional": LicenseStatus.LICENSED_PROFESSIONAL,
    "LicensedCommunityPlus": LicenseStatus.LICENSED_PROFESSIONAL_GRACE,
    "UnlicensedCommunity": LicenseStatus.UNLICENSED_COMMUNITY,
    "UnlicensedUnverified": LicenseStatus.RESTRICTED_VERIFICATION_FAILED,
    "ErrorBinaryTampered": LicenseStatus.LOCKDOWN_INTEGRITY_FAILURE,
    "ErrorSourcesDisagree": LicenseStatus.LOCKDOWN_ATTACK_DETECTED,
    "ErrorVerificationFailed": LicenseStatus.ERROR_VERIFICATION_FAILED,
    "ErrorLicenseRevoked": LicenseStatus.ERROR_REVOKED,
    "ErrorLicenseExpired": LicenseStatus.ERROR_EXPIRED,
}

# Map Rust DisclosureSeverity variants to Python enum
_RUST_SEVERITY_MAP = {
    "Info": DisclosureSeverity.INFO,
    "Warning": DisclosureSeverity.WARNING,
    "Critical": DisclosureSeverity.CRITICAL,
}

# Map Rust HardwareType to Python enum (from PlatformAttestation variant)
_RUST_HARDWARE_MAP = {
    "AndroidKeystore": HardwareType.ANDROID_KEYSTORE,
    "AndroidStrongbox": HardwareType.ANDROID_STRONGBOX,
    "IosSecureEnclave": HardwareType.IOS_SECURE_ENCLAVE,
    "Tpm20": HardwareType.TPM_DISCRETE,
    "IntelSgx": HardwareType.INTEL_SGX,
    "SoftwareOnly": HardwareType.SOFTWARE_ONLY,
    "Software": HardwareType.SOFTWARE_ONLY,
}

# Map Rust ValidationStatus variants to Python enum
_RUST_VALIDATION_MAP = {
    "AllSourcesAgree": ValidationStatus.ALL_SOURCES_AGREE,
    "PartialAgreement": ValidationStatus.PARTIAL_AGREEMENT,
    "SourcesDisagree": ValidationStatus.SOURCES_DISAGREE,
    "NoSourcesReachable": ValidationStatus.NO_SOURCES_REACHABLE,
    "ValidationError": ValidationStatus.VALIDATION_ERROR,
}


class CIRISVerify:
    """High-level client for CIRISVerify license verification.

    This class wraps the CIRISVerify Rust binary via C FFI, providing
    a Pythonic interface for license verification operations.

    Usage:
        verifier = CIRISVerify()
        status = await verifier.get_license_status(challenge_nonce=os.urandom(32))

        if status.allows_licensed_operation():
            # Professional capabilities available
            pass

    Thread Safety:
        The client is thread-safe. Multiple threads can call methods
        concurrently. Async methods use a thread pool for FFI calls.
    """

    def __init__(
        self,
        binary_path: Optional[str] = None,
        deployment_id: Optional[str] = None,
        skip_integrity_check: bool = False,
        timeout_seconds: float = 10.0,
    ):
        """Initialize CIRISVerify client.

        Args:
            binary_path: Path to CIRISVerify binary. If None, searches
                         default system paths.
            deployment_id: Unique deployment identifier. If None, generated
                          from hostname.
            skip_integrity_check: Skip binary integrity verification.
                                  WARNING: Only for development/testing.
            timeout_seconds: Default timeout for verification operations.

        Raises:
            BinaryNotFoundError: If binary cannot be found.
            BinaryTamperedError: If binary integrity check fails.
        """
        self._timeout = timeout_seconds
        self._deployment_id = deployment_id or self._generate_deployment_id()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ciris_verify")
        self._lib: Optional[ctypes.CDLL] = None
        self._handle = None

        # Find and load binary
        self._binary_path = self._find_binary(binary_path)

        if not skip_integrity_check:
            self._verify_binary_integrity()

        self._load_library()

    @staticmethod
    def _generate_deployment_id() -> str:
        """Generate a deployment ID from the hostname."""
        hostname = socket.gethostname()
        return f"deploy-{hashlib.sha256(hostname.encode()).hexdigest()[:16]}"

    @staticmethod
    def _is_ios() -> bool:
        """Check if running on iOS."""
        # Python 3.13+ sets sys.platform to "ios"
        if hasattr(__import__("sys"), "platform") and __import__("sys").platform == "ios":
            return True
        # Fallback: check for iOS-specific environment variable
        if os.environ.get("CIRIS_IOS_FRAMEWORK_PATH"):
            return True
        return False

    @staticmethod
    def _is_android() -> bool:
        """Check if running on Android (Chaquopy).

        Android detection via:
        1. ANDROID_ROOT environment variable (set by Android runtime)
        2. Chaquopy's Java module availability
        """
        # Chaquopy sets ANDROID_ROOT environment variable
        if os.environ.get("ANDROID_ROOT"):
            return True
        # Check for Chaquopy-specific marker
        try:
            import java  # noqa: F401
            return True
        except ImportError:
            pass
        return False

    @staticmethod
    def _find_ios_framework() -> Optional[Path]:
        """Find CIRISVerify framework on iOS."""
        # Check explicit env var first
        env_path = os.environ.get("CIRIS_IOS_FRAMEWORK_PATH")
        if env_path:
            path = Path(env_path)
            if path.exists():
                return path

        # Search app bundle for CIRISVerify.framework
        # On iOS, frameworks are in {app_bundle}/Frameworks/
        module_dir = Path(__file__).parent
        # Walk up to find the app bundle root
        for parent in module_dir.parents:
            framework = parent / "Frameworks" / "CIRISVerify.framework" / "CIRISVerify"
            if framework.exists():
                return framework

        # Check for .fwork redirect file (Python on iOS pattern)
        fwork = module_dir / "libciris_verify_ffi.fwork"
        if fwork.exists():
            redirect_target = fwork.read_text().strip()
            redirect_path = module_dir / redirect_target
            if redirect_path.exists():
                return redirect_path

        return None

    @staticmethod
    def _find_android_library() -> Optional[Path]:
        """Find CIRISVerify library on Android.

        On Android with Chaquopy, native libraries from jniLibs are loaded
        into the app's native library directory. ctypes.util.find_library()
        doesn't return filesystem paths on Android, so we need to use the
        Java context to get nativeLibraryDir.
        """
        import logging
        logger = logging.getLogger(__name__)

        # Use Chaquopy's Java context to get nativeLibraryDir
        try:
            from java import jclass
            context = jclass("com.chaquo.python.Python").getPlatform().getApplication()
            native_lib_dir = context.getApplicationInfo().nativeLibraryDir
            logger.info(f"[CIRISVerify] Android nativeLibraryDir: {native_lib_dir}")

            lib_path = Path(native_lib_dir) / "libciris_verify_ffi.so"
            if lib_path.exists():
                return lib_path
        except Exception as e:
            logger.warning(f"[CIRISVerify] Chaquopy context lookup failed: {e}")

        # Fallback paths for common Android app locations
        android_paths = [
            "/data/app/ai.ciris.mobile/lib/arm64/libciris_verify_ffi.so",
            "/data/data/ai.ciris.mobile/lib/libciris_verify_ffi.so",
        ]
        for path_str in android_paths:
            path = Path(path_str)
            if path.exists():
                return path

        return None

    def _find_binary(self, explicit_path: Optional[str]) -> Path:
        """Find CIRISVerify binary."""
        if explicit_path:
            path = Path(explicit_path)
            if path.exists():
                return path
            raise BinaryNotFoundError(explicit_path)

        # iOS-specific framework search
        if self._is_ios():
            ios_path = self._find_ios_framework()
            if ios_path:
                return ios_path
            raise BinaryNotFoundError(
                "CIRISVerify.framework not found in app bundle. "
                "Ensure CIRISVerify.xcframework is linked in Xcode."
            )

        # Android-specific library search (Chaquopy)
        if self._is_android():
            android_path = self._find_android_library()
            if android_path:
                return android_path
            raise BinaryNotFoundError(
                "libciris_verify_ffi.so not found on Android. "
                "Ensure the native library is included in jniLibs."
            )

        # Search default paths
        system = platform.system()
        paths = DEFAULT_BINARY_PATHS.get(system, [])

        for path_str in paths:
            path = Path(path_str)
            if path.exists():
                return path

        # Also check relative to this module
        module_dir = Path(__file__).parent
        for suffix in [".so", ".dylib", ".dll"]:
            candidate = module_dir / f"libciris_verify_ffi{suffix}"
            if candidate.exists():
                return candidate

        raise BinaryNotFoundError(f"Searched: {paths}")

    def _verify_binary_integrity(self) -> None:
        """Verify binary hasn't been tampered with."""
        try:
            with open(self._binary_path, "rb") as f:
                magic = f.read(4)
                if not magic:
                    raise BinaryTamperedError("Empty binary file")

                valid_magic = [
                    b"\x7fELF",           # ELF
                    b"\xfe\xed\xfa\xce",  # Mach-O 32 BE
                    b"\xfe\xed\xfa\xcf",  # Mach-O 64 BE
                    b"\xce\xfa\xed\xfe",  # Mach-O 32 LE
                    b"\xcf\xfa\xed\xfe",  # Mach-O 64 LE (macOS/iOS arm64)
                    b"\xca\xfe\xba\xbe",  # Mach-O Universal
                    b"!\x0a<arch>",       # Static library (ar archive)
                    b"MZ\x90\x00",        # PE
                    b"MZ\x00\x00",        # PE variant
                ]

                if not any(magic.startswith(m[:len(magic)]) for m in valid_magic):
                    raise BinaryTamperedError(f"Invalid binary magic: {magic.hex()}")

        except (OSError, IOError) as e:
            raise BinaryTamperedError(f"Cannot read binary: {e}")

    def _load_library(self) -> None:
        """Load the shared library and set up FFI bindings."""
        try:
            self._lib = ctypes.CDLL(str(self._binary_path))
        except OSError as e:
            raise CommunicationError(f"Failed to load library: {e}", e)

        # ciris_verify_init() -> *mut CirisVerifyHandle
        self._lib.ciris_verify_init.argtypes = []
        self._lib.ciris_verify_init.restype = ctypes.c_void_p

        # ciris_verify_get_status(handle, request_data, request_len, response_data, response_len) -> i32
        # NOTE: response_data is JSON text (no null bytes), but use c_void_p for
        # consistency with other output pointer patterns.
        self._lib.ciris_verify_get_status.argtypes = [
            ctypes.c_void_p,                    # handle
            ctypes.c_char_p,                    # request_data (JSON bytes, input)
            ctypes.c_size_t,                    # request_len
            ctypes.POINTER(ctypes.c_void_p),    # response_data (out)
            ctypes.POINTER(ctypes.c_size_t),    # response_len (out)
        ]
        self._lib.ciris_verify_get_status.restype = ctypes.c_int

        # ciris_verify_check_capability(handle, capability, action, required_tier, allowed) -> i32
        self._lib.ciris_verify_check_capability.argtypes = [
            ctypes.c_void_p,                    # handle
            ctypes.c_char_p,                    # capability
            ctypes.c_char_p,                    # action
            ctypes.c_int,                       # required_tier
            ctypes.POINTER(ctypes.c_int),       # allowed (out)
        ]
        self._lib.ciris_verify_check_capability.restype = ctypes.c_int

        # ciris_verify_check_agent_integrity(handle, manifest_data, manifest_len,
        #   agent_root, spot_check_count, response_data, response_len) -> i32
        self._lib.ciris_verify_check_agent_integrity.argtypes = [
            ctypes.c_void_p,                    # handle
            ctypes.c_char_p,                    # manifest_data (JSON bytes, input)
            ctypes.c_size_t,                    # manifest_len
            ctypes.c_char_p,                    # agent_root (null-terminated path, input)
            ctypes.c_uint32,                    # spot_check_count (0 = full)
            ctypes.POINTER(ctypes.c_void_p),    # response_data (out)
            ctypes.POINTER(ctypes.c_size_t),    # response_len (out)
        ]
        self._lib.ciris_verify_check_agent_integrity.restype = ctypes.c_int

        # ciris_verify_sign(handle, data, data_len, sig_data, sig_len) -> i32
        # NOTE: Use c_void_p for output sig_data — c_char_p truncates at null bytes.
        self._lib.ciris_verify_sign.argtypes = [
            ctypes.c_void_p,                    # handle
            ctypes.c_char_p,                    # data (input, null-terminated OK)
            ctypes.c_size_t,                    # data_len
            ctypes.POINTER(ctypes.c_void_p),    # signature_data (out)
            ctypes.POINTER(ctypes.c_size_t),    # signature_len (out)
        ]
        self._lib.ciris_verify_sign.restype = ctypes.c_int

        # ciris_verify_get_public_key(handle, key_data, key_len, algorithm, algorithm_len) -> i32
        # NOTE: Use c_void_p (not c_char_p) for output data pointers because
        # c_char_p truncates at null bytes, and public keys contain 0x00 bytes.
        self._lib.ciris_verify_get_public_key.argtypes = [
            ctypes.c_void_p,                    # handle
            ctypes.POINTER(ctypes.c_void_p),    # key_data (out)
            ctypes.POINTER(ctypes.c_size_t),    # key_len (out)
            ctypes.POINTER(ctypes.c_void_p),    # algorithm (out)
            ctypes.POINTER(ctypes.c_size_t),    # algorithm_len (out)
        ]
        self._lib.ciris_verify_get_public_key.restype = ctypes.c_int

        # ciris_verify_export_attestation(handle, challenge, challenge_len, proof_data, proof_len) -> i32
        self._lib.ciris_verify_export_attestation.argtypes = [
            ctypes.c_void_p,                    # handle
            ctypes.c_char_p,                    # challenge (input)
            ctypes.c_size_t,                    # challenge_len
            ctypes.POINTER(ctypes.c_void_p),    # proof_data (out)
            ctypes.POINTER(ctypes.c_size_t),    # proof_len (out)
        ]
        self._lib.ciris_verify_export_attestation.restype = ctypes.c_int

        # ciris_verify_free(data)
        self._lib.ciris_verify_free.argtypes = [ctypes.c_char_p]
        self._lib.ciris_verify_free.restype = None

        # ciris_verify_destroy(handle)
        self._lib.ciris_verify_destroy.argtypes = [ctypes.c_void_p]
        self._lib.ciris_verify_destroy.restype = None

        # Ed25519 Portal key functions (optional - may not exist in older libraries)
        # These functions enable agent identity signing with Portal-issued keys.
        self._has_ed25519_support = False
        try:
            # ciris_verify_import_key(handle, key_data, key_len) -> i32
            self._lib.ciris_verify_import_key.argtypes = [
                ctypes.c_void_p,  # handle
                ctypes.c_char_p,  # key_data
                ctypes.c_size_t,  # key_len
            ]
            self._lib.ciris_verify_import_key.restype = ctypes.c_int

            # ciris_verify_has_key(handle) -> i32
            self._lib.ciris_verify_has_key.argtypes = [ctypes.c_void_p]
            self._lib.ciris_verify_has_key.restype = ctypes.c_int

            # ciris_verify_delete_key(handle) -> i32
            self._lib.ciris_verify_delete_key.argtypes = [ctypes.c_void_p]
            self._lib.ciris_verify_delete_key.restype = ctypes.c_int

            # ciris_verify_sign_ed25519(handle, data, data_len, sig_data, sig_len) -> i32
            self._lib.ciris_verify_sign_ed25519.argtypes = [
                ctypes.c_void_p,                    # handle
                ctypes.c_char_p,                    # data
                ctypes.c_size_t,                    # data_len
                ctypes.POINTER(ctypes.c_void_p),    # signature_data (out)
                ctypes.POINTER(ctypes.c_size_t),    # signature_len (out)
            ]
            self._lib.ciris_verify_sign_ed25519.restype = ctypes.c_int

            # ciris_verify_get_ed25519_public_key(handle, key_data, key_len) -> i32
            self._lib.ciris_verify_get_ed25519_public_key.argtypes = [
                ctypes.c_void_p,                    # handle
                ctypes.POINTER(ctypes.c_void_p),    # key_data (out)
                ctypes.POINTER(ctypes.c_size_t),    # key_len (out)
            ]
            self._lib.ciris_verify_get_ed25519_public_key.restype = ctypes.c_int

            self._has_ed25519_support = True
        except AttributeError:
            import logging
            logging.getLogger(__name__).info(
                "[CIRISVerify] Ed25519 key functions not available in this library version"
            )

        # ciris_verify_get_diagnostics (optional - added in 0.4.3)
        try:
            self._lib.ciris_verify_get_diagnostics.argtypes = [
                ctypes.c_void_p,                    # handle
                ctypes.POINTER(ctypes.c_void_p),    # diag_data (out)
                ctypes.POINTER(ctypes.c_size_t),    # diag_len (out)
            ]
            self._lib.ciris_verify_get_diagnostics.restype = ctypes.c_int
        except AttributeError:
            pass  # Older library version, diagnostics not available

        # ciris_verify_audit_trail (optional - added in 0.6.16)
        try:
            self._lib.ciris_verify_audit_trail.argtypes = [
                ctypes.c_void_p,                    # handle (can be null)
                ctypes.c_char_p,                    # db_path
                ctypes.c_char_p,                    # jsonl_path (optional)
                ctypes.c_char_p,                    # portal_key_id (optional)
                ctypes.POINTER(ctypes.c_void_p),    # result_json (out)
                ctypes.POINTER(ctypes.c_size_t),    # result_len (out)
            ]
            self._lib.ciris_verify_audit_trail.restype = ctypes.c_int
            self._has_audit_trail_support = True
        except AttributeError:
            self._has_audit_trail_support = False

        # ciris_verify_run_attestation (optional - added in 0.6.17)
        # Full unified attestation running all 5 levels
        try:
            self._lib.ciris_verify_run_attestation.argtypes = [
                ctypes.c_void_p,                    # handle
                ctypes.c_char_p,                    # request_json (input)
                ctypes.c_size_t,                    # request_len
                ctypes.POINTER(ctypes.c_void_p),    # result_json (out)
                ctypes.POINTER(ctypes.c_size_t),    # result_len (out)
            ]
            self._lib.ciris_verify_run_attestation.restype = ctypes.c_int
            self._has_run_attestation_support = True
        except AttributeError:
            self._has_run_attestation_support = False

        # Initialize handle
        self._handle = self._lib.ciris_verify_init()
        if not self._handle:
            raise CommunicationError("Failed to initialize CIRISVerify handle")

    def __del__(self):
        """Clean up resources."""
        if self._handle and self._lib:
            try:
                self._lib.ciris_verify_destroy(self._handle)
            except Exception:
                pass
        if self._executor:
            self._executor.shutdown(wait=False)

    def _sync_get_license_status(
        self,
        challenge_nonce: bytes,
        device_fingerprint: Optional[bytes] = None,
    ) -> LicenseStatusResponse:
        """Synchronous license status check (internal).

        Sends a JSON-encoded LicenseStatusRequest to the Rust FFI and
        parses the JSON-encoded LicenseStatusResponse.
        """
        if len(challenge_nonce) < 32:
            raise ValueError("challenge_nonce must be at least 32 bytes")

        # Build JSON request matching Rust LicenseStatusRequest
        request_obj = {
            "deployment_id": self._deployment_id,
            "challenge_nonce": list(challenge_nonce),
            "force_refresh": False,
        }
        request_bytes = json.dumps(request_obj).encode("utf-8")

        # Call FFI
        response_data = ctypes.c_void_p()
        response_len = ctypes.c_size_t()

        result = self._lib.ciris_verify_get_status(
            self._handle,
            request_bytes,
            len(request_bytes),
            ctypes.byref(response_data),
            ctypes.byref(response_len),
        )

        if result != 0:
            raise VerificationFailedError(result, f"FFI call failed with code {result}")

        try:
            response_bytes = ctypes.string_at(response_data.value, response_len.value)
            return self._parse_response(response_bytes)
        finally:
            if response_data.value:
                self._lib.ciris_verify_free(ctypes.c_char_p(response_data.value))

    def _parse_response(self, data: bytes) -> LicenseStatusResponse:
        """Parse JSON response from Rust FFI into LicenseStatusResponse."""
        try:
            resp = json.loads(data)
        except json.JSONDecodeError as e:
            raise CommunicationError(f"Invalid JSON response: {e}")

        # Map Rust status string to Python IntEnum
        rust_status = resp.get("status", "ErrorVerificationFailed")
        status = _RUST_STATUS_MAP.get(rust_status, LicenseStatus.ERROR_VERIFICATION_FAILED)

        # Parse mandatory_disclosure
        md = resp.get("mandatory_disclosure", {})
        severity_str = md.get("severity", "Warning")
        severity = _RUST_SEVERITY_MAP.get(severity_str, DisclosureSeverity.WARNING)
        disclosure = MandatoryDisclosure(
            text=md.get("text", self._default_disclosure(status)),
            severity=severity,
            locale=md.get("locale", "en"),
        )

        # Parse hardware type from attestation.platform
        attestation_data = resp.get("attestation", {})
        platform_info = attestation_data.get("platform", {})
        hardware_type = self._parse_hardware_type(platform_info)

        # Parse validation results
        validation = resp.get("validation", {})
        overall_str = validation.get("overall", "ValidationError")
        dns_us = validation.get("dns_us", {})
        dns_eu = validation.get("dns_eu", {})
        https_src = validation.get("https", {})

        source_details = SourceDetails(
            dns_us_reachable=dns_us.get("reachable", False),
            dns_eu_reachable=dns_eu.get("reachable", False),
            https_reachable=https_src.get("reachable", False),
            validation_status=_RUST_VALIDATION_MAP.get(
                overall_str, ValidationStatus.VALIDATION_ERROR
            ),
            sources_agreeing=sum([
                dns_us.get("valid", False),
                dns_eu.get("valid", False),
                https_src.get("valid", False),
            ]),
            # Error details (added in v0.6.6)
            dns_us_error=dns_us.get("error_details") or dns_us.get("error"),
            dns_us_error_category=dns_us.get("error_category"),
            dns_eu_error=dns_eu.get("error_details") or dns_eu.get("error"),
            dns_eu_error_category=dns_eu.get("error_category"),
            https_error=https_src.get("error_details") or https_src.get("error"),
            https_error_category=https_src.get("error_category"),
        )

        # Parse license details if present
        license_details = None
        lic = resp.get("license")
        if lic:
            license_details = self._parse_license_details(lic)

        # Parse metadata for cache info
        metadata = resp.get("metadata", {})

        return LicenseStatusResponse(
            status=status,
            license=license_details,
            mandatory_disclosure=disclosure,
            hardware_type=hardware_type,
            source_details=source_details,
            cached=False,
            verification_timestamp=datetime.now(timezone.utc),
        )

    def _parse_hardware_type(self, platform_info: dict) -> HardwareType:
        """Parse hardware type from Rust PlatformAttestation."""
        if not platform_info:
            return HardwareType.SOFTWARE_ONLY

        # PlatformAttestation is a tagged enum in Rust serde
        # It serializes as {"Software": {...}} or {"Android": {...}} etc.
        for key in platform_info:
            mapped = _RUST_HARDWARE_MAP.get(key)
            if mapped:
                return mapped

        return HardwareType.SOFTWARE_ONLY

    def _parse_license_details(self, lic: dict) -> Optional[LicenseDetails]:
        """Parse license details from Rust JSON."""
        try:
            return LicenseDetails(
                license_id=lic.get("license_id", "unknown"),
                tier=LicenseTier(lic.get("max_autonomy_tier", 0)),
                capabilities=set(lic.get("capabilities", [])),
                prohibited_capabilities=set(lic.get("capabilities_denied", [])),
                issued_at=datetime.fromtimestamp(lic.get("not_before", 0), tz=timezone.utc),
                expires_at=datetime.fromtimestamp(lic.get("expires_at", 0), tz=timezone.utc),
                issuer=lic.get("issuer", "unknown"),
                holder_name=lic.get("holder_name"),
                holder_organization=lic.get("organization_name"),
                responsible_party=lic.get("responsible_party", ""),
                public_contact_email=lic.get("responsible_party_contact", ""),
            )
        except Exception:
            return None

    def _default_disclosure(self, status: LicenseStatus, reason: str = "") -> str:
        """Generate default disclosure text based on status."""
        if status.allows_licensed_operation():
            return "This agent is professionally licensed and verified."
        elif status.is_community_mode():
            reason_text = f"Reason: {reason} " if reason else ""
            return (
                "COMMUNITY MODE: This is an unlicensed community agent. "
                "Professional capabilities (medical, legal, financial advice) "
                f"are NOT available. {reason_text}"
                "Outputs are for informational purposes only."
            )
        elif status.requires_restricted():
            reason_text = f"Reason: {reason} " if reason else ""
            return (
                f"WARNING: License verification encountered issues. {reason_text}"
                "Operating in restricted mode with limited capabilities."
            )
        else:
            reason_text = f"Reason: {reason} " if reason else ""
            return (
                f"CRITICAL: License verification failed. {reason_text}"
                "Agent capabilities are severely restricted."
            )

    async def get_license_status(
        self,
        challenge_nonce: bytes,
        device_fingerprint: Optional[bytes] = None,
        timeout: Optional[float] = None,
    ) -> LicenseStatusResponse:
        """Get current license status with cryptographic attestation.

        Args:
            challenge_nonce: Random 32+ byte nonce to prevent replay attacks.
            device_fingerprint: Optional device identifier for binding.
            timeout: Operation timeout in seconds.

        Returns:
            LicenseStatusResponse with complete verification results.

        Raises:
            ValueError: If challenge_nonce is too short.
            TimeoutError: If operation times out.
            VerificationFailedError: If verification fails.
        """
        timeout = timeout or self._timeout

        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    self._executor,
                    self._sync_get_license_status,
                    challenge_nonce,
                    device_fingerprint,
                ),
                timeout=timeout,
            )
            return result
        except asyncio.TimeoutError:
            raise CIRISTimeoutError("get_license_status", timeout)

    async def check_capability(
        self,
        capability: str,
        timeout: Optional[float] = None,
    ) -> CapabilityCheckResult:
        """Check if a specific capability is allowed.

        Args:
            capability: Capability string to check (e.g., "medical:diagnosis").
            timeout: Operation timeout in seconds.

        Returns:
            CapabilityCheckResult with allow/deny decision and reason.
        """
        timeout = timeout or self._timeout

        def _check() -> CapabilityCheckResult:
            result = ctypes.c_int()
            ret = self._lib.ciris_verify_check_capability(
                self._handle,
                capability.encode("utf-8"),
                b"",  # action (default empty)
                0,    # required_tier (default 0)
                ctypes.byref(result),
            )

            if ret != 0:
                return CapabilityCheckResult(
                    capability=capability,
                    allowed=False,
                    reason=f"Check failed with code {ret}",
                )

            allowed = result.value == 1
            reason = "Capability granted" if allowed else "Capability denied by license"

            return CapabilityCheckResult(
                capability=capability,
                allowed=allowed,
                reason=reason,
            )

        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(self._executor, _check),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise CIRISTimeoutError("check_capability", timeout)

    async def check_agent_integrity(
        self,
        manifest_path: str,
        agent_root: str,
        spot_check_count: int = 0,
        timeout: Optional[float] = None,
    ) -> FileIntegrityResult:
        """Check agent file integrity (Tripwire-style).

        Validates that CIRISAgent Python files have not been modified
        since the distribution was built. ANY unauthorized change
        (except .env, log, audit files) means the agent is compromised.

        Args:
            manifest_path: Path to the JSON manifest file.
            agent_root: Root directory of the agent installation.
            spot_check_count: Number of files to spot-check. 0 = full check.
            timeout: Operation timeout in seconds.

        Returns:
            FileIntegrityResult with integrity status.
            If integrity_valid is False, the agent MUST shut down.
        """
        timeout = timeout or self._timeout

        def _check() -> FileIntegrityResult:
            # Read manifest file
            with open(manifest_path, "rb") as f:
                manifest_bytes = f.read()

            response_data = ctypes.c_void_p()
            response_len = ctypes.c_size_t()

            ret = self._lib.ciris_verify_check_agent_integrity(
                self._handle,
                manifest_bytes,
                len(manifest_bytes),
                agent_root.encode("utf-8"),
                spot_check_count,
                ctypes.byref(response_data),
                ctypes.byref(response_len),
            )

            if ret != 0:
                return FileIntegrityResult(
                    integrity_valid=False,
                    failure_reason=f"FFI call failed with code {ret}",
                )

            try:
                result_bytes = ctypes.string_at(response_data.value, response_len.value)
                result_dict = json.loads(result_bytes)
                return FileIntegrityResult(**result_dict)
            finally:
                if response_data.value:
                    self._lib.ciris_verify_free(ctypes.c_char_p(response_data.value))

        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(self._executor, _check),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise CIRISTimeoutError("check_agent_integrity", timeout)

    async def sign(
        self,
        data: bytes,
        timeout: Optional[float] = None,
    ) -> bytes:
        """Sign data using the hardware-bound private key.

        This is the vault-style signing interface: the agent delegates
        signing to CIRISVerify, which uses the hardware security module.
        The private key never leaves the secure hardware.

        Args:
            data: Data to sign.
            timeout: Operation timeout in seconds.

        Returns:
            Signature bytes (64 bytes for Ed25519/ECDSA P-256).

        Raises:
            VerificationFailedError: If signing fails.
            TimeoutError: If operation times out.
        """
        timeout = timeout or self._timeout

        def _sign() -> bytes:
            sig_data = ctypes.c_void_p()
            sig_len = ctypes.c_size_t()

            ret = self._lib.ciris_verify_sign(
                self._handle,
                data,
                len(data),
                ctypes.byref(sig_data),
                ctypes.byref(sig_len),
            )

            if ret != 0:
                raise VerificationFailedError(ret, f"Signing failed with code {ret}")

            try:
                return ctypes.string_at(sig_data.value, sig_len.value)
            finally:
                if sig_data.value:
                    self._lib.ciris_verify_free(ctypes.c_char_p(sig_data.value))

        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(self._executor, _sign),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise CIRISTimeoutError("sign", timeout)

    async def get_public_key(
        self,
        timeout: Optional[float] = None,
    ) -> tuple[bytes, str]:
        """Get the public key from the hardware-bound keypair.

        Returns:
            Tuple of (public_key_bytes, algorithm_name).
            - Ed25519: 32 bytes, "Ed25519"
            - ECDSA P-256: 65 bytes (uncompressed), "EcdsaP256"

        Raises:
            VerificationFailedError: If key retrieval fails.
            TimeoutError: If operation times out.
        """
        timeout = timeout or self._timeout

        def _get_key() -> tuple[bytes, str]:
            key_data = ctypes.c_void_p()
            key_len = ctypes.c_size_t()
            algo_data = ctypes.c_void_p()
            algo_len = ctypes.c_size_t()

            ret = self._lib.ciris_verify_get_public_key(
                self._handle,
                ctypes.byref(key_data),
                ctypes.byref(key_len),
                ctypes.byref(algo_data),
                ctypes.byref(algo_len),
            )

            if ret != 0:
                raise VerificationFailedError(ret, f"Get public key failed with code {ret}")

            try:
                key_bytes = ctypes.string_at(key_data.value, key_len.value)
                algo_str = ctypes.string_at(algo_data.value, algo_len.value).decode("utf-8")
                return key_bytes, algo_str
            finally:
                if key_data.value:
                    self._lib.ciris_verify_free(ctypes.c_char_p(key_data.value))
                if algo_data.value:
                    self._lib.ciris_verify_free(ctypes.c_char_p(algo_data.value))

        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(self._executor, _get_key),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise CIRISTimeoutError("get_public_key", timeout)

    async def export_attestation(
        self,
        challenge: bytes,
        timeout: Optional[float] = None,
    ) -> dict:
        """Export a remote attestation proof for third-party verification.

        The proof contains hardware attestation, dual (classical + PQC) signatures
        over the challenge, and the Merkle root from the transparency log.

        Args:
            challenge: Verifier-provided challenge nonce (must be >= 32 bytes).
            timeout: Operation timeout in seconds.

        Returns:
            Dictionary containing the AttestationProof with:
            - platform_attestation: Hardware attestation data
            - classical_public_key: Ed25519/ECDSA public key bytes (hex)
            - pqc_public_key: ML-DSA-65 public key bytes (hex)
            - classical_signature: Signature over challenge (hex)
            - pqc_signature: Signature over challenge||classical_sig (hex)
            - merkle_root: Current transparency log root (hex)
            - log_size: Number of entries in transparency log
            - binary_version: CIRISVerify version
            - hardware_type: Detected hardware security module

        Raises:
            ValueError: If challenge is too short.
            VerificationFailedError: If attestation export fails.
            TimeoutError: If operation times out.
        """
        if len(challenge) < 32:
            raise ValueError("challenge must be at least 32 bytes")

        timeout = timeout or self._timeout

        def _export() -> dict:
            proof_data = ctypes.c_void_p()
            proof_len = ctypes.c_size_t()

            ret = self._lib.ciris_verify_export_attestation(
                self._handle,
                challenge,
                len(challenge),
                ctypes.byref(proof_data),
                ctypes.byref(proof_len),
            )

            if ret != 0:
                raise VerificationFailedError(ret, f"Attestation export failed with code {ret}")

            try:
                proof_bytes = ctypes.string_at(proof_data.value, proof_len.value)
                return json.loads(proof_bytes)
            finally:
                if proof_data.value:
                    self._lib.ciris_verify_free(ctypes.c_char_p(proof_data.value))

        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(self._executor, _export),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise CIRISTimeoutError("export_attestation", timeout)

    def export_attestation_sync(
        self,
        challenge: bytes,
    ) -> dict:
        """Synchronous version of export_attestation for non-async contexts.

        Args:
            challenge: Verifier-provided challenge nonce (must be >= 32 bytes).

        Returns:
            Dictionary containing the AttestationProof.

        Raises:
            ValueError: If challenge is too short.
            VerificationFailedError: If attestation export fails.
        """
        if len(challenge) < 32:
            raise ValueError("challenge must be at least 32 bytes")

        proof_data = ctypes.c_void_p()
        proof_len = ctypes.c_size_t()

        ret = self._lib.ciris_verify_export_attestation(
            self._handle,
            challenge,
            len(challenge),
            ctypes.byref(proof_data),
            ctypes.byref(proof_len),
        )

        if ret != 0:
            raise VerificationFailedError(ret, f"Attestation export failed with code {ret}")

        try:
            proof_bytes = ctypes.string_at(proof_data.value, proof_len.value)
            return json.loads(proof_bytes)
        finally:
            if proof_data.value:
                self._lib.ciris_verify_free(ctypes.c_char_p(proof_data.value))

    # ========================================================================
    # Audit Trail Verification
    # ========================================================================

    @property
    def has_audit_trail_support(self) -> bool:
        """Check if audit trail verification is available.

        Returns:
            True if the library supports audit trail verification.
        """
        return getattr(self, "_has_audit_trail_support", False)

    async def verify_audit_trail(
        self,
        db_path: str,
        jsonl_path: Optional[str] = None,
        portal_key_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """Verify the agent's audit trail for integrity.

        This reads the audit trail from the specified SQLite database
        and/or JSONL file and verifies:
        - Hash chain integrity (each entry links to previous)
        - Hash validity (each entry's hash matches computed hash)
        - Genesis validity (first entry has "genesis" as previous_hash)
        - Optional signature verification

        Args:
            db_path: Path to ciris_audit.db SQLite database.
            jsonl_path: Optional path to audit_logs.jsonl for cross-checking.
            portal_key_id: Optional Portal key ID for signature verification.
            timeout: Operation timeout in seconds.

        Returns:
            Dictionary containing AuditVerificationResult with:
            - valid: Whether audit trail is valid
            - total_entries: Total entries in audit log
            - entries_verified: Number of entries verified
            - hash_chain_valid: Whether hash chain is intact
            - signatures_valid: Whether signatures are valid
            - genesis_valid: Whether genesis entry is proper
            - portal_key_used: Whether Portal key was used
            - first_tampered_sequence: First tampered sequence (if any)
            - errors: List of error messages
            - verification_time_ms: Verification time in milliseconds
            - chain_summary: Summary of the chain state

        Raises:
            RuntimeError: If audit trail support is not available.
            VerificationFailedError: If verification fails to run.
            TimeoutError: If operation times out.
        """
        if not self.has_audit_trail_support:
            raise RuntimeError("Audit trail verification not available in this library version")

        timeout = timeout or self._timeout

        def _verify() -> dict:
            result_data = ctypes.c_void_p()
            result_len = ctypes.c_size_t()

            # Encode paths as C strings
            db_path_bytes = db_path.encode('utf-8')
            jsonl_path_bytes = jsonl_path.encode('utf-8') if jsonl_path else None
            portal_key_bytes = portal_key_id.encode('utf-8') if portal_key_id else None

            ret = self._lib.ciris_verify_audit_trail(
                self._handle,
                db_path_bytes,
                jsonl_path_bytes,
                portal_key_bytes,
                ctypes.byref(result_data),
                ctypes.byref(result_len),
            )

            if ret != 0:
                raise VerificationFailedError(ret, f"Audit trail verification failed with code {ret}")

            try:
                result_bytes = ctypes.string_at(result_data.value, result_len.value)
                return json.loads(result_bytes)
            finally:
                if result_data.value:
                    self._lib.ciris_verify_free(ctypes.c_char_p(result_data.value))

        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(self._executor, _verify),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise CIRISTimeoutError("verify_audit_trail", timeout)

    def verify_audit_trail_sync(
        self,
        db_path: str,
        jsonl_path: Optional[str] = None,
        portal_key_id: Optional[str] = None,
    ) -> dict:
        """Synchronous version of verify_audit_trail.

        Args:
            db_path: Path to ciris_audit.db SQLite database.
            jsonl_path: Optional path to audit_logs.jsonl for cross-checking.
            portal_key_id: Optional Portal key ID for signature verification.

        Returns:
            Dictionary containing AuditVerificationResult.

        Raises:
            RuntimeError: If audit trail support is not available.
            VerificationFailedError: If verification fails to run.
        """
        if not self.has_audit_trail_support:
            raise RuntimeError("Audit trail verification not available in this library version")

        result_data = ctypes.c_void_p()
        result_len = ctypes.c_size_t()

        # Encode paths as C strings
        db_path_bytes = db_path.encode('utf-8')
        jsonl_path_bytes = jsonl_path.encode('utf-8') if jsonl_path else None
        portal_key_bytes = portal_key_id.encode('utf-8') if portal_key_id else None

        ret = self._lib.ciris_verify_audit_trail(
            self._handle,
            db_path_bytes,
            jsonl_path_bytes,
            portal_key_bytes,
            ctypes.byref(result_data),
            ctypes.byref(result_len),
        )

        if ret != 0:
            raise VerificationFailedError(ret, f"Audit trail verification failed with code {ret}")

        try:
            result_bytes = ctypes.string_at(result_data.value, result_len.value)
            return json.loads(result_bytes)
        finally:
            if result_data.value:
                self._lib.ciris_verify_free(ctypes.c_char_p(result_data.value))

    # ========================================================================
    # Full Unified Attestation
    # ========================================================================

    @property
    def has_run_attestation_support(self) -> bool:
        """Check if full unified attestation is available.

        Returns:
            True if the library supports run_attestation.
        """
        return getattr(self, "_has_run_attestation_support", False)

    async def run_attestation(
        self,
        challenge: bytes,
        agent_version: Optional[str] = None,
        agent_root: Optional[str] = None,
        spot_check_count: int = 0,
        audit_entries: Optional[list] = None,
        portal_key_id: Optional[str] = None,
        skip_registry: bool = False,
        skip_file_integrity: bool = False,
        skip_audit: bool = False,
        timeout: Optional[float] = None,
    ) -> dict:
        """Run full unified attestation with all 5 verification levels.

        This is the comprehensive attestation function that runs:
        - Level 1: Library loaded verification
        - Level 2: Binary self-verification (hash against registry)
        - Level 3: Registry cross-validation (multi-source consensus)
        - Level 4: Agent file integrity (Tripwire-style)
        - Level 5: Portal key + audit trail verification

        Args:
            challenge: Verifier-provided challenge nonce (>= 32 bytes).
            agent_version: Agent version to verify against registry (e.g., "2.0.0").
            agent_root: Agent root directory for file integrity checks.
            spot_check_count: Number of files for spot check (0 = skip spot check).
            audit_entries: Audit entries for verification (list of dicts).
            portal_key_id: Portal key ID for audit signature verification.
            skip_registry: Skip registry manifest fetch (offline operation).
            skip_file_integrity: Skip file integrity checks.
            skip_audit: Skip audit trail verification.
            timeout: Operation timeout in seconds.

        Returns:
            Dictionary containing FullAttestationResult with:
            - valid: Overall attestation validity (bool)
            - level: Attestation level achieved (0-5)
            - key_attestation: Key attestation result (dict or None)
            - file_integrity: File integrity result (dict or None)
            - sources: Source validation results (dict)
            - audit_trail: Audit verification result (dict or None)
            - checks_passed: Number of checks passed (int)
            - checks_total: Total checks run (int)
            - diagnostics: Diagnostic information (str)
            - errors: List of error messages (list)

        Raises:
            RuntimeError: If run_attestation is not available.
            ValueError: If challenge is too short.
            VerificationFailedError: If attestation fails to run.
            TimeoutError: If operation times out.
        """
        if not self.has_run_attestation_support:
            raise RuntimeError("run_attestation not available in this library version (requires >= 0.6.17)")

        if len(challenge) < 32:
            raise ValueError("challenge must be at least 32 bytes")

        timeout = timeout or self._timeout

        def _run() -> dict:
            # Build request JSON
            request_obj = {
                "challenge": list(challenge),
            }
            if agent_version is not None:
                request_obj["agent_version"] = agent_version
            if agent_root is not None:
                request_obj["agent_root"] = agent_root
            if spot_check_count > 0:
                request_obj["spot_check_count"] = spot_check_count
            if audit_entries is not None:
                request_obj["audit_entries"] = audit_entries
            if portal_key_id is not None:
                request_obj["portal_key_id"] = portal_key_id
            request_obj["skip_registry"] = skip_registry
            request_obj["skip_file_integrity"] = skip_file_integrity
            request_obj["skip_audit"] = skip_audit

            request_bytes = json.dumps(request_obj).encode("utf-8")

            result_data = ctypes.c_void_p()
            result_len = ctypes.c_size_t()

            ret = self._lib.ciris_verify_run_attestation(
                self._handle,
                request_bytes,
                len(request_bytes),
                ctypes.byref(result_data),
                ctypes.byref(result_len),
            )

            if ret != 0:
                raise VerificationFailedError(ret, f"run_attestation failed with code {ret}")

            try:
                result_bytes = ctypes.string_at(result_data.value, result_len.value)
                return json.loads(result_bytes)
            finally:
                if result_data.value:
                    self._lib.ciris_verify_free(ctypes.c_char_p(result_data.value))

        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(self._executor, _run),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise CIRISTimeoutError("run_attestation", timeout)

    def run_attestation_sync(
        self,
        challenge: bytes,
        agent_version: Optional[str] = None,
        agent_root: Optional[str] = None,
        spot_check_count: int = 0,
        audit_entries: Optional[list] = None,
        portal_key_id: Optional[str] = None,
        skip_registry: bool = False,
        skip_file_integrity: bool = False,
        skip_audit: bool = False,
    ) -> dict:
        """Synchronous version of run_attestation.

        Args:
            challenge: Verifier-provided challenge nonce (>= 32 bytes).
            agent_version: Agent version to verify against registry.
            agent_root: Agent root directory for file integrity checks.
            spot_check_count: Number of files for spot check (0 = skip).
            audit_entries: Audit entries for verification.
            portal_key_id: Portal key ID for audit signature verification.
            skip_registry: Skip registry manifest fetch.
            skip_file_integrity: Skip file integrity checks.
            skip_audit: Skip audit trail verification.

        Returns:
            Dictionary containing FullAttestationResult.

        Raises:
            RuntimeError: If run_attestation is not available.
            ValueError: If challenge is too short.
            VerificationFailedError: If attestation fails.
        """
        if not self.has_run_attestation_support:
            raise RuntimeError("run_attestation not available in this library version (requires >= 0.6.17)")

        if len(challenge) < 32:
            raise ValueError("challenge must be at least 32 bytes")

        # Build request JSON
        request_obj = {
            "challenge": list(challenge),
        }
        if agent_version is not None:
            request_obj["agent_version"] = agent_version
        if agent_root is not None:
            request_obj["agent_root"] = agent_root
        if spot_check_count > 0:
            request_obj["spot_check_count"] = spot_check_count
        if audit_entries is not None:
            request_obj["audit_entries"] = audit_entries
        if portal_key_id is not None:
            request_obj["portal_key_id"] = portal_key_id
        request_obj["skip_registry"] = skip_registry
        request_obj["skip_file_integrity"] = skip_file_integrity
        request_obj["skip_audit"] = skip_audit

        request_bytes = json.dumps(request_obj).encode("utf-8")

        result_data = ctypes.c_void_p()
        result_len = ctypes.c_size_t()

        ret = self._lib.ciris_verify_run_attestation(
            self._handle,
            request_bytes,
            len(request_bytes),
            ctypes.byref(result_data),
            ctypes.byref(result_len),
        )

        if ret != 0:
            raise VerificationFailedError(ret, f"run_attestation failed with code {ret}")

        try:
            result_bytes = ctypes.string_at(result_data.value, result_len.value)
            return json.loads(result_bytes)
        finally:
            if result_data.value:
                self._lib.ciris_verify_free(ctypes.c_char_p(result_data.value))

    def get_mandatory_disclosure(self, status: LicenseStatus) -> MandatoryDisclosure:
        """Get mandatory disclosure for a given status.

        Args:
            status: License status to get disclosure for.

        Returns:
            MandatoryDisclosure with text and severity.
        """
        if status.requires_lockdown():
            severity = DisclosureSeverity.CRITICAL
        elif status.requires_restricted():
            severity = DisclosureSeverity.WARNING
        else:
            severity = DisclosureSeverity.INFO

        return MandatoryDisclosure(
            text=self._default_disclosure(status),
            severity=severity,
        )

    # ========================================================================
    # Ed25519 Key Management (Portal-issued keys)
    # ========================================================================

    @property
    def has_ed25519_support(self) -> bool:
        """Check if Ed25519 key functions are available.

        Returns:
            True if the library supports Ed25519 Portal key operations.
        """
        return getattr(self, "_has_ed25519_support", False)

    def import_key_sync(self, key_bytes: bytes) -> bool:
        """Import an Ed25519 signing key from Portal.

        This imports a 32-byte Ed25519 seed/private key issued by CIRISPortal.
        The key is stored in memory and used for agent identity signing.

        Args:
            key_bytes: 32-byte Ed25519 seed/private key

        Returns:
            True if key was imported successfully, False otherwise.

        Raises:
            ValueError: If key_bytes is not 32 bytes.
            NotImplementedError: If Ed25519 support is not available.
        """
        if not self._has_ed25519_support:
            raise NotImplementedError(
                "Ed25519 key functions not available in this library version. "
                "Update to ciris-verify >= 0.4.0 for Portal key support."
            )
        if len(key_bytes) != 32:
            raise ValueError(f"Ed25519 key must be 32 bytes, got {len(key_bytes)}")

        ret = self._lib.ciris_verify_import_key(
            self._handle,
            key_bytes,
            len(key_bytes),
        )

        return ret == 0

    def has_key_sync(self) -> bool:
        """Check if an Ed25519 signing key is loaded.

        Returns:
            True if a key is loaded, False otherwise.

        Raises:
            NotImplementedError: If Ed25519 support is not available.
        """
        if not self._has_ed25519_support:
            raise NotImplementedError(
                "Ed25519 key functions not available in this library version."
            )
        ret = self._lib.ciris_verify_has_key(self._handle)
        return ret == 1

    def delete_key_sync(self) -> bool:
        """Delete the loaded Ed25519 signing key.

        Returns:
            True if deletion succeeded, False otherwise.

        Raises:
            NotImplementedError: If Ed25519 support is not available.
        """
        if not self._has_ed25519_support:
            raise NotImplementedError(
                "Ed25519 key functions not available in this library version."
            )
        ret = self._lib.ciris_verify_delete_key(self._handle)
        return ret == 0

    def sign_ed25519_sync(self, data: bytes) -> bytes:
        """Sign data using the Portal-issued Ed25519 key.

        This signs with the Ed25519 key imported via import_key_sync(),
        not the hardware-bound key. Use sign() for hardware signing.

        Args:
            data: Data to sign.

        Returns:
            64-byte Ed25519 signature.

        Raises:
            NotImplementedError: If Ed25519 support is not available.
            VerificationFailedError: If no key is loaded or signing fails.
        """
        if not self._has_ed25519_support:
            raise NotImplementedError(
                "Ed25519 key functions not available in this library version."
            )
        sig_data = ctypes.c_void_p()
        sig_len = ctypes.c_size_t()

        ret = self._lib.ciris_verify_sign_ed25519(
            self._handle,
            data,
            len(data),
            ctypes.byref(sig_data),
            ctypes.byref(sig_len),
        )

        if ret != 0:
            raise VerificationFailedError(ret, f"Ed25519 signing failed with code {ret}")

        try:
            return ctypes.string_at(sig_data.value, sig_len.value)
        finally:
            if sig_data.value:
                self._lib.ciris_verify_free(ctypes.c_char_p(sig_data.value))

    def get_ed25519_public_key_sync(self) -> bytes:
        """Get the Ed25519 public key from the Portal-issued key.

        Returns:
            32-byte Ed25519 public key.

        Raises:
            NotImplementedError: If Ed25519 support is not available.
            VerificationFailedError: If no key is loaded.
        """
        if not self._has_ed25519_support:
            raise NotImplementedError(
                "Ed25519 key functions not available in this library version."
            )
        key_data = ctypes.c_void_p()
        key_len = ctypes.c_size_t()

        ret = self._lib.ciris_verify_get_ed25519_public_key(
            self._handle,
            ctypes.byref(key_data),
            ctypes.byref(key_len),
        )

        if ret != 0:
            raise VerificationFailedError(ret, f"Get Ed25519 public key failed with code {ret}")

        try:
            return ctypes.string_at(key_data.value, key_len.value)
        finally:
            if key_data.value:
                self._lib.ciris_verify_free(ctypes.c_char_p(key_data.value))

    def get_diagnostics_sync(self) -> str:
        """Get diagnostic information about the Ed25519 signer state.

        Returns detailed diagnostic info including:
        - Key alias
        - Whether key is loaded in memory
        - Storage path for persistence
        - Environment variables affecting storage

        Returns:
            Diagnostic string with key state information.

        Raises:
            CommunicationError: If diagnostics retrieval fails.
        """
        diag_data = ctypes.c_void_p()
        diag_len = ctypes.c_size_t()

        # Check if function exists (added in 0.4.3)
        if not hasattr(self._lib, "ciris_verify_get_diagnostics"):
            return "Diagnostics not available (library version < 0.4.3)"

        ret = self._lib.ciris_verify_get_diagnostics(
            self._handle,
            ctypes.byref(diag_data),
            ctypes.byref(diag_len),
        )

        if ret != 0:
            return f"Diagnostics retrieval failed with code {ret}"

        try:
            return ctypes.string_at(diag_data.value, diag_len.value).decode("utf-8")
        finally:
            if diag_data.value:
                self._lib.ciris_verify_free(ctypes.c_char_p(diag_data.value))


class MockCIRISVerify(CIRISVerify):
    """Mock CIRISVerify client for testing without the actual binary.

    Usage:
        verifier = MockCIRISVerify(
            mock_status=LicenseStatus.UNLICENSED_COMMUNITY
        )
        status = await verifier.get_license_status(os.urandom(32))
        assert status.status == LicenseStatus.UNLICENSED_COMMUNITY
    """

    def __init__(
        self,
        mock_status: LicenseStatus = LicenseStatus.UNLICENSED_COMMUNITY,
        mock_hardware: HardwareType = HardwareType.SOFTWARE_ONLY,
        mock_capabilities: Optional[Set[str]] = None,
    ):
        """Initialize mock client.

        Args:
            mock_status: Status to return from get_license_status().
            mock_hardware: Hardware type to report.
            mock_capabilities: Set of allowed capabilities.
        """
        self._mock_status = mock_status
        self._mock_hardware = mock_hardware
        self._mock_capabilities = mock_capabilities
        self._timeout = 10.0
        # Don't call parent __init__ - no binary needed

    def _find_binary(self, path):
        return None

    def _verify_binary_integrity(self):
        pass

    def _load_library(self):
        pass

    def __del__(self):
        pass

    async def get_license_status(
        self,
        challenge_nonce: bytes,
        device_fingerprint: Optional[bytes] = None,
        timeout: Optional[float] = None,
    ) -> LicenseStatusResponse:
        """Return mock license status."""
        if len(challenge_nonce) < 32:
            raise ValueError("challenge_nonce must be at least 32 bytes")

        severity = DisclosureSeverity.INFO
        if self._mock_status.requires_lockdown():
            severity = DisclosureSeverity.CRITICAL
        elif self._mock_status.requires_restricted():
            severity = DisclosureSeverity.WARNING

        license_details = None
        if self._mock_status.allows_licensed_operation():
            license_details = LicenseDetails(
                license_id="mock-license-001",
                tier=LicenseTier.PROFESSIONAL_FULL,
                capabilities=self._mock_capabilities or {"*"},
                prohibited_capabilities=set(),
                issued_at=datetime.now(timezone.utc),
                expires_at=datetime(2099, 12, 31, tzinfo=timezone.utc),
                issuer="mock-issuer",
            )

        mock_reason = (
            "Using MockCIRISVerify (no real binary). "
            "Install ciris-verify with hardware support for licensed operation."
        )
        return LicenseStatusResponse(
            status=self._mock_status,
            license=license_details,
            mandatory_disclosure=MandatoryDisclosure(
                text="[MOCK] " + self._default_disclosure(self._mock_status, reason=mock_reason),
                severity=severity,
            ),
            hardware_type=self._mock_hardware,
            source_details=SourceDetails(
                dns_us_reachable=True,
                dns_eu_reachable=True,
                https_reachable=True,
                validation_status=ValidationStatus.ALL_SOURCES_AGREE,
                sources_agreeing=3,
            ),
            cached=False,
            verification_timestamp=datetime.now(timezone.utc),
        )

    async def check_capability(
        self,
        capability: str,
        timeout: Optional[float] = None,
    ) -> CapabilityCheckResult:
        """Return mock capability check.

        In community mode, standard operations (standard:*, tool:*) are
        allowed. Professional domain capabilities (medical, legal, financial,
        etc.) are blocked.
        """
        # Standard operations are always allowed, even in community mode
        cap_lower = capability.lower()
        is_standard = (
            cap_lower.startswith("standard:")
            or cap_lower.startswith("tool:")
        )

        if not self._mock_status.allows_licensed_operation():
            if is_standard:
                return CapabilityCheckResult(
                    capability=capability,
                    allowed=True,
                    reason="Standard operation allowed",
                )
            return CapabilityCheckResult(
                capability=capability,
                allowed=False,
                reason="Community mode - professional capabilities not available",
            )

        if self._mock_capabilities is None:
            allowed = True
        else:
            allowed = capability in self._mock_capabilities or "*" in self._mock_capabilities

        return CapabilityCheckResult(
            capability=capability,
            allowed=allowed,
            reason="Allowed by mock" if allowed else "Not in mock capabilities",
        )

    async def check_agent_integrity(
        self,
        manifest_path: str,
        agent_root: str,
        spot_check_count: int = 0,
        timeout: Optional[float] = None,
    ) -> FileIntegrityResult:
        """Mock agent integrity check — always passes."""
        return FileIntegrityResult(
            integrity_valid=True,
            total_files=0,
            files_checked=0,
            files_passed=0,
            files_failed=0,
            files_missing=0,
            files_unexpected=0,
            failure_reason="",
        )

    async def sign(
        self,
        data: bytes,
        timeout: Optional[float] = None,
    ) -> bytes:
        """Mock sign — uses software Ed25519 key for testing.

        Generates a deterministic mock signature. NOT cryptographically
        secure — for testing only.
        """
        # Use a mock Ed25519 signing key
        if not hasattr(self, "_mock_private_key"):
            from cryptography.hazmat.primitives.asymmetric import ed25519
            self._mock_private_key = ed25519.Ed25519PrivateKey.generate()
            self._mock_public_key = self._mock_private_key.public_key()

        return self._mock_private_key.sign(data)

    async def get_public_key(
        self,
        timeout: Optional[float] = None,
    ) -> tuple[bytes, str]:
        """Mock get_public_key — returns software Ed25519 key."""
        if not hasattr(self, "_mock_private_key"):
            from cryptography.hazmat.primitives.asymmetric import ed25519
            self._mock_private_key = ed25519.Ed25519PrivateKey.generate()
            self._mock_public_key = self._mock_private_key.public_key()

        from cryptography.hazmat.primitives import serialization
        key_bytes = self._mock_public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return key_bytes, "Ed25519"

    @property
    def has_run_attestation_support(self) -> bool:
        """Mock always supports run_attestation."""
        return True

    async def run_attestation(
        self,
        challenge: bytes,
        agent_version: Optional[str] = None,
        agent_root: Optional[str] = None,
        spot_check_count: int = 0,
        audit_entries: Optional[list] = None,
        portal_key_id: Optional[str] = None,
        skip_registry: bool = False,
        skip_file_integrity: bool = False,
        skip_audit: bool = False,
        timeout: Optional[float] = None,
    ) -> dict:
        """Mock run_attestation — returns successful attestation."""
        if len(challenge) < 32:
            raise ValueError("challenge must be at least 32 bytes")

        return {
            "valid": True,
            "level": 3,  # Registry cross-validation level
            "key_attestation": {
                "valid": True,
                "hardware_type": "Software",
            },
            "file_integrity": None,  # Skipped in mock
            "sources": {
                "dns_us": {"reachable": True, "valid": True},
                "dns_eu": {"reachable": True, "valid": True},
                "https": {"reachable": True, "valid": True},
            },
            "audit_trail": None,  # Skipped in mock
            "checks_passed": 3,
            "checks_total": 3,
            "diagnostics": "[MOCK] Using MockCIRISVerify",
            "errors": [],
        }

    def run_attestation_sync(
        self,
        challenge: bytes,
        agent_version: Optional[str] = None,
        agent_root: Optional[str] = None,
        spot_check_count: int = 0,
        audit_entries: Optional[list] = None,
        portal_key_id: Optional[str] = None,
        skip_registry: bool = False,
        skip_file_integrity: bool = False,
        skip_audit: bool = False,
    ) -> dict:
        """Synchronous mock run_attestation."""
        if len(challenge) < 32:
            raise ValueError("challenge must be at least 32 bytes")

        return {
            "valid": True,
            "level": 3,
            "key_attestation": {"valid": True, "hardware_type": "Software"},
            "file_integrity": None,
            "sources": {
                "dns_us": {"reachable": True, "valid": True},
                "dns_eu": {"reachable": True, "valid": True},
                "https": {"reachable": True, "valid": True},
            },
            "audit_trail": None,
            "checks_passed": 3,
            "checks_total": 3,
            "diagnostics": "[MOCK] Using MockCIRISVerify",
            "errors": [],
        }

    def _default_disclosure(self, status: LicenseStatus, reason: str = "") -> str:
        """Generate default disclosure for mock."""
        return super()._default_disclosure(status, reason=reason)
