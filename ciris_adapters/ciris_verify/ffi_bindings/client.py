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
    PythonModuleHashes,
    PythonIntegrityResult,
    SecurityAdvisory,
    HardwareLimitation,
    HardwareInfo,
    StorageDescriptor,
    StorageKind,
    KeyringScope,
)
from .exceptions import (
    BinaryNotFoundError,
    BinaryTamperedError,
    VerificationFailedError,
    TimeoutError as CIRISTimeoutError,
    CommunicationError,
    AttestationInProgressError,
)

# FFI error codes
CIRIS_ERROR_ATTESTATION_IN_PROGRESS = -100


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
    # Serde externally-tagged enum keys (from PlatformAttestation variants)
    "Android": HardwareType.ANDROID_KEYSTORE,
    "Ios": HardwareType.IOS_SECURE_ENCLAVE,
    "Tpm": HardwareType.TPM_DISCRETE,
    "Software": HardwareType.SOFTWARE_ONLY,
    # Legacy/alternate keys for backwards compatibility
    "AndroidKeystore": HardwareType.ANDROID_KEYSTORE,
    "AndroidStrongbox": HardwareType.ANDROID_STRONGBOX,
    "IosSecureEnclave": HardwareType.IOS_SECURE_ENCLAVE,
    "Tpm20": HardwareType.TPM_DISCRETE,
    "IntelSgx": HardwareType.INTEL_SGX,
    "SoftwareOnly": HardwareType.SOFTWARE_ONLY,
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

        # ciris_verify_signer_storage_descriptor(handle, descriptor_data, descriptor_len) -> i32 (v1.7)
        # Older libraries do not export this; gated by _has_storage_descriptor.
        self._has_storage_descriptor = False
        if hasattr(self._lib, "ciris_verify_signer_storage_descriptor"):
            self._lib.ciris_verify_signer_storage_descriptor.argtypes = [
                ctypes.c_void_p,                    # handle
                ctypes.POINTER(ctypes.c_void_p),    # descriptor_data (out)
                ctypes.POINTER(ctypes.c_size_t),    # descriptor_len (out)
            ]
            self._lib.ciris_verify_signer_storage_descriptor.restype = ctypes.c_int
            self._has_storage_descriptor = True

        # ciris_verify_free(data)
        # NOTE: MUST be c_void_p, not c_char_p! c_char_p treats the pointer as a
        # null-terminated string and can corrupt memory by reading past allocation.
        self._lib.ciris_verify_free.argtypes = [ctypes.c_void_p]
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

            # ciris_verify_generate_key(handle) -> i32
            # CRITICAL: Must be set or ctypes truncates 64-bit pointers to 32-bit!
            self._lib.ciris_verify_generate_key.argtypes = [ctypes.c_void_p]
            self._lib.ciris_verify_generate_key.restype = ctypes.c_int

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

        # ciris_verify_device_attestation_failed (optional - added in 1.5.3)
        # Report device attestation failure (Play Integrity / App Attest token acquisition failed)
        try:
            self._lib.ciris_verify_device_attestation_failed.argtypes = [
                ctypes.c_void_p,                    # handle
                ctypes.c_char_p,                    # platform ("android" or "ios")
                ctypes.c_int,                       # error_code
                ctypes.c_char_p,                    # error_message (nullable)
            ]
            self._lib.ciris_verify_device_attestation_failed.restype = ctypes.c_int
            self._has_device_attestation_failed_support = True
        except AttributeError:
            self._has_device_attestation_failed_support = False

        # ciris_verify_save_manifest_cache (optional - added in 1.2.0)
        # Save manifests with hardware signature for offline L1
        try:
            self._lib.ciris_verify_save_manifest_cache.argtypes = [
                ctypes.c_void_p,                    # handle
                ctypes.c_char_p,                    # binary_manifest_json
                ctypes.c_size_t,                    # binary_manifest_len
                ctypes.c_char_p,                    # function_manifest_json (nullable)
                ctypes.c_size_t,                    # function_manifest_len
                ctypes.c_char_p,                    # build_record_json (nullable)
                ctypes.c_size_t,                    # build_record_len
            ]
            self._lib.ciris_verify_save_manifest_cache.restype = ctypes.c_int

            self._lib.ciris_verify_load_manifest_cache.argtypes = [
                ctypes.c_void_p,                    # handle
                ctypes.POINTER(ctypes.c_void_p),    # result_json (out)
                ctypes.POINTER(ctypes.c_size_t),    # result_len (out)
            ]
            self._lib.ciris_verify_load_manifest_cache.restype = ctypes.c_int

            self._lib.ciris_verify_manifest_cache_exists.argtypes = [
                ctypes.c_void_p,                    # handle (can be null)
            ]
            self._lib.ciris_verify_manifest_cache_exists.restype = ctypes.c_int
            self._has_manifest_cache_support = True
        except AttributeError:
            self._has_manifest_cache_support = False

        # ciris_verify_get_hardware_info (optional - added in 1.2.0)
        # Get hardware information and security limitations
        try:
            self._lib.ciris_verify_get_hardware_info.argtypes = [
                ctypes.c_void_p,                    # handle (can be null)
                ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),  # result_json
                ctypes.POINTER(ctypes.c_size_t),   # result_len
            ]
            self._lib.ciris_verify_get_hardware_info.restype = ctypes.c_int

            self._lib.ciris_verify_get_hardware_info_android.argtypes = [
                ctypes.c_void_p,                    # handle (can be null)
                ctypes.c_char_p,                    # hardware
                ctypes.c_char_p,                    # board
                ctypes.c_char_p,                    # manufacturer
                ctypes.c_char_p,                    # model
                ctypes.c_char_p,                    # security_patch
                ctypes.c_char_p,                    # fingerprint
                ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),  # result_json
                ctypes.POINTER(ctypes.c_size_t),   # result_len
            ]
            self._lib.ciris_verify_get_hardware_info_android.restype = ctypes.c_int
            self._has_hardware_info_support = True
        except AttributeError:
            self._has_hardware_info_support = False

        # ciris_verify_set_log_callback (optional - added in 0.9.1)
        # Register a callback to receive internal log messages
        try:
            # Callback signature: void callback(int level, const char* target, const char* message)
            # Level: 1=ERROR, 2=WARN, 3=INFO, 4=DEBUG, 5=TRACE
            self._log_callback_type = ctypes.CFUNCTYPE(
                None,           # return type (void)
                ctypes.c_int,   # level
                ctypes.c_char_p,  # target
                ctypes.c_char_p,  # message
            )
            self._lib.ciris_verify_set_log_callback.argtypes = [self._log_callback_type]
            self._lib.ciris_verify_set_log_callback.restype = None
            self._has_log_callback_support = True
            # Keep reference to prevent garbage collection
            self._active_log_callback = None
        except AttributeError:
            self._has_log_callback_support = False
            self._log_callback_type = None
            self._active_log_callback = None

        # ciris_verify_derive_secp256k1_pubkey (optional - added in 1.3.0)
        # Derive secp256k1 public key for EVM wallet
        try:
            self._lib.ciris_verify_derive_secp256k1_pubkey.argtypes = [
                ctypes.c_void_p,                    # handle
                ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),  # pubkey_data (out)
                ctypes.POINTER(ctypes.c_size_t),    # pubkey_len (out)
            ]
            self._lib.ciris_verify_derive_secp256k1_pubkey.restype = ctypes.c_int

            self._lib.ciris_verify_get_evm_address.argtypes = [
                ctypes.POINTER(ctypes.c_uint8),     # pubkey
                ctypes.c_size_t,                    # pubkey_len
                ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),  # address_data (out)
                ctypes.POINTER(ctypes.c_size_t),    # address_len (out)
            ]
            self._lib.ciris_verify_get_evm_address.restype = ctypes.c_int

            self._lib.ciris_verify_get_evm_address_checksummed.argtypes = [
                ctypes.POINTER(ctypes.c_uint8),     # pubkey
                ctypes.c_size_t,                    # pubkey_len
                ctypes.POINTER(ctypes.c_char_p),    # address_str (out)
                ctypes.POINTER(ctypes.c_size_t),    # address_str_len (out)
            ]
            self._lib.ciris_verify_get_evm_address_checksummed.restype = ctypes.c_int

            self._lib.ciris_verify_sign_secp256k1.argtypes = [
                ctypes.c_void_p,                    # handle
                ctypes.POINTER(ctypes.c_uint8),     # message_hash
                ctypes.c_size_t,                    # hash_len
                ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),  # signature_data (out)
                ctypes.POINTER(ctypes.c_size_t),    # signature_len (out)
            ]
            self._lib.ciris_verify_sign_secp256k1.restype = ctypes.c_int

            self._lib.ciris_verify_sign_evm_transaction.argtypes = [
                ctypes.c_void_p,                    # handle
                ctypes.POINTER(ctypes.c_uint8),     # tx_hash
                ctypes.c_size_t,                    # hash_len
                ctypes.c_uint64,                    # chain_id
                ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),  # signature_data (out)
                ctypes.POINTER(ctypes.c_size_t),    # signature_len (out)
            ]
            self._lib.ciris_verify_sign_evm_transaction.restype = ctypes.c_int

            self._lib.ciris_verify_sign_typed_data.argtypes = [
                ctypes.c_void_p,                    # handle
                ctypes.POINTER(ctypes.c_uint8),     # domain_hash
                ctypes.c_size_t,                    # domain_len
                ctypes.POINTER(ctypes.c_uint8),     # message_hash
                ctypes.c_size_t,                    # message_len
                ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),  # signature_data (out)
                ctypes.POINTER(ctypes.c_size_t),    # signature_len (out)
            ]
            self._lib.ciris_verify_sign_typed_data.restype = ctypes.c_int

            self._lib.ciris_verify_recover_evm_address.argtypes = [
                ctypes.POINTER(ctypes.c_uint8),     # message_hash
                ctypes.c_size_t,                    # hash_len
                ctypes.POINTER(ctypes.c_uint8),     # signature
                ctypes.c_size_t,                    # signature_len
                ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),  # address_data (out)
                ctypes.POINTER(ctypes.c_size_t),    # address_len (out)
            ]
            self._lib.ciris_verify_recover_evm_address.restype = ctypes.c_int

            self._lib.ciris_verify_get_wallet_info.argtypes = [
                ctypes.c_void_p,                    # handle
                ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),  # result_json (out)
                ctypes.POINTER(ctypes.c_size_t),    # result_len (out)
            ]
            self._lib.ciris_verify_get_wallet_info.restype = ctypes.c_int

            self._has_wallet_support = True
        except AttributeError:
            self._has_wallet_support = False

        # Named key storage functions (v1.5.0)
        self._has_named_key_support = False
        try:
            # ciris_verify_store_named_key(handle, key_id, seed, seed_len) -> i32
            self._lib.ciris_verify_store_named_key.argtypes = [
                ctypes.c_void_p,  # handle
                ctypes.c_char_p,  # key_id
                ctypes.c_char_p,  # seed
                ctypes.c_size_t,  # seed_len
            ]
            self._lib.ciris_verify_store_named_key.restype = ctypes.c_int

            # ciris_verify_sign_with_named_key(handle, key_id, data, data_len, sig_out, sig_len_out) -> i32
            self._lib.ciris_verify_sign_with_named_key.argtypes = [
                ctypes.c_void_p,  # handle
                ctypes.c_char_p,  # key_id
                ctypes.c_char_p,  # data
                ctypes.c_size_t,  # data_len
                ctypes.POINTER(ctypes.c_void_p),  # signature_data (out)
                ctypes.POINTER(ctypes.c_size_t),  # signature_len (out)
            ]
            self._lib.ciris_verify_sign_with_named_key.restype = ctypes.c_int

            # ciris_verify_has_named_key(handle, key_id) -> i32
            self._lib.ciris_verify_has_named_key.argtypes = [
                ctypes.c_void_p,  # handle
                ctypes.c_char_p,  # key_id
            ]
            self._lib.ciris_verify_has_named_key.restype = ctypes.c_int

            # ciris_verify_delete_named_key(handle, key_id) -> i32
            self._lib.ciris_verify_delete_named_key.argtypes = [
                ctypes.c_void_p,  # handle
                ctypes.c_char_p,  # key_id
            ]
            self._lib.ciris_verify_delete_named_key.restype = ctypes.c_int

            # ciris_verify_get_named_key_public(handle, key_id, pk_out, pk_len_out) -> i32
            self._lib.ciris_verify_get_named_key_public.argtypes = [
                ctypes.c_void_p,  # handle
                ctypes.c_char_p,  # key_id
                ctypes.POINTER(ctypes.c_void_p),  # pubkey_data (out)
                ctypes.POINTER(ctypes.c_size_t),  # pubkey_len (out)
            ]
            self._lib.ciris_verify_get_named_key_public.restype = ctypes.c_int

            # ciris_verify_list_named_keys(handle, json_out) -> i32
            self._lib.ciris_verify_list_named_keys.argtypes = [
                ctypes.c_void_p,  # handle
                ctypes.POINTER(ctypes.c_char_p),  # json_out
            ]
            self._lib.ciris_verify_list_named_keys.restype = ctypes.c_int

            # ciris_verify_free_string(str) -> void
            self._lib.ciris_verify_free_string.argtypes = [ctypes.c_char_p]
            self._lib.ciris_verify_free_string.restype = None

            self._has_named_key_support = True
        except AttributeError:
            self._has_named_key_support = False

        # Initialize handle
        self._handle = self._lib.ciris_verify_init()
        if not self._handle:
            raise CommunicationError("Failed to initialize CIRISVerify handle")

    def __del__(self):
        """Clean up resources."""
        # Clear log callback first to prevent calls during destruction
        # Use getattr to handle partial initialization
        if getattr(self, '_has_log_callback_support', False) and getattr(self, '_lib', None):
            try:
                # Pass null function pointer to disable callback
                log_cb_type = getattr(self, '_log_callback_type', None)
                if log_cb_type:
                    null_callback = ctypes.cast(None, log_cb_type)
                    self._lib.ciris_verify_set_log_callback(null_callback)
            except Exception:
                pass
        # Clear the reference after FFI call
        if hasattr(self, '_active_log_callback'):
            self._active_log_callback = None
        if getattr(self, '_handle', None) and getattr(self, '_lib', None):
            try:
                self._lib.ciris_verify_destroy(self._handle)
            except Exception:
                pass
        if getattr(self, '_executor', None):
            self._executor.shutdown(wait=False)

    def set_log_callback(self, callback=None, level: int = 3):
        """Set a callback to receive internal log messages.

        Args:
            callback: A callable(level: int, target: str, message: str) or None to disable.
                      Level: 1=ERROR, 2=WARN, 3=INFO, 4=DEBUG, 5=TRACE
            level: Minimum log level to receive (1-5). Default 3 (INFO).

        Example:
            def my_logger(level, target, message):
                level_names = {1: "ERROR", 2: "WARN", 3: "INFO", 4: "DEBUG", 5: "TRACE"}
                print(f"[{level_names.get(level, '?')}] [{target}] {message}")

            verifier.set_log_callback(my_logger, level=4)  # DEBUG and above

        Note:
            The callback may be invoked from any thread (Rust async runtime).
            Keep the callback fast to avoid blocking verification operations.
        """
        if not self._has_log_callback_support:
            import warnings
            warnings.warn("Log callback not supported in this library version (requires 0.9.1+)")
            return

        if callback is None:
            # Pass null function pointer to disable callback
            null_callback = ctypes.cast(None, self._log_callback_type)
            self._lib.ciris_verify_set_log_callback(null_callback)
            self._active_log_callback = None
            return

        min_level = level

        def c_callback(lvl: int, target: ctypes.c_char_p, message: ctypes.c_char_p):
            if lvl > min_level:
                return
            try:
                target_str = target.decode("utf-8") if target else ""
                message_str = message.decode("utf-8") if message else ""
                callback(lvl, target_str, message_str)
            except Exception:
                pass  # Never let exceptions escape to Rust

        # Wrap in CFUNCTYPE and keep reference
        self._active_log_callback = self._log_callback_type(c_callback)
        self._lib.ciris_verify_set_log_callback(self._active_log_callback)

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
                self._lib.ciris_verify_free(response_data.value)

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
                    self._lib.ciris_verify_free(response_data.value)

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
                    self._lib.ciris_verify_free(sig_data.value)

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
                    self._lib.ciris_verify_free(key_data.value)
                if algo_data.value:
                    self._lib.ciris_verify_free(algo_data.value)

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
                    self._lib.ciris_verify_free(proof_data.value)

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
                self._lib.ciris_verify_free(proof_data.value)

    # ========================================================================
    # Storage Descriptor (v1.7)
    # ========================================================================

    @property
    def has_storage_descriptor_support(self) -> bool:
        """Check if the underlying library exports the v1.7 descriptor API."""
        return getattr(self, "_has_storage_descriptor", False)

    def storage_descriptor(self) -> StorageDescriptor:
        """Get the storage descriptor of the signer's identity material.

        Use this at boot to detect ephemeral storage before identity churn
        silently breaks longitudinal scoring (PoB §2.4 S-factor decay window
        cannot accumulate behind an unstable identity). For an agent, the
        check looks like:

            desc = client.storage_descriptor()
            if desc.kind == StorageKind.SOFTWARE_FILE:
                path = desc.disk_path()
                if path and any(path.startswith(p) for p in ("/tmp/", "/var/cache/")):
                    raise RuntimeError(f"identity in ephemeral storage: {path}")

        Returns:
            A `StorageDescriptor` with `kind` and variant-specific fields.

        Raises:
            VerificationFailedError: If the FFI call returns non-zero.
            RuntimeError: If the underlying library predates v1.7
                (check `has_storage_descriptor_support` first).
        """
        if not self.has_storage_descriptor_support:
            raise RuntimeError(
                "Underlying ciris-verify library does not expose "
                "ciris_verify_signer_storage_descriptor (added in v1.7). "
                "Upgrade the native library."
            )

        descriptor_data = ctypes.c_void_p()
        descriptor_len = ctypes.c_size_t()

        ret = self._lib.ciris_verify_signer_storage_descriptor(
            self._handle,
            ctypes.byref(descriptor_data),
            ctypes.byref(descriptor_len),
        )

        if ret != 0:
            raise VerificationFailedError(
                ret, f"storage_descriptor failed with code {ret}"
            )

        try:
            payload = ctypes.string_at(descriptor_data.value, descriptor_len.value)
            return StorageDescriptor.model_validate_json(payload)
        finally:
            if descriptor_data.value:
                self._lib.ciris_verify_free(descriptor_data.value)

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
                    self._lib.ciris_verify_free(result_data.value)

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
                self._lib.ciris_verify_free(result_data.value)

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
        key_fingerprint: Optional[str] = None,
        python_hashes: Optional[PythonModuleHashes] = None,
        expected_python_hash: Optional[str] = None,
        partial_file_check: bool = False,
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
            key_fingerprint: Agent key fingerprint for registry verification (v0.8.1+).
            python_hashes: Python module hashes for mobile code integrity (v0.8.1+).
            expected_python_hash: Expected total hash for Python modules (v0.8.1+).
            partial_file_check: Use partial file check mode (v0.8.1+).
            timeout: Operation timeout in seconds.

        Returns:
            Dictionary containing FullAttestationResult with:
            - valid: Overall attestation validity (bool)
            - level: Attestation level achieved (0-5)
            - key_attestation: Key attestation result (dict or None)
            - file_integrity: File integrity result (dict or None)
            - sources: Source validation results (dict)
            - audit_trail: Audit verification result (dict or None)
            - python_integrity: Python module integrity result (dict or None, v0.8.1+)
            - registry_key_status: Registry key verification status (str, v0.8.1+)
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
            if key_fingerprint is not None:
                request_obj["key_fingerprint"] = key_fingerprint
            if python_hashes is not None:
                # Convert PythonModuleHashes to dict for JSON serialization
                request_obj["python_hashes"] = {
                    "total_hash": python_hashes.total_hash,
                    "module_hashes": python_hashes.module_hashes,
                    "module_count": python_hashes.module_count,
                    "agent_version": python_hashes.agent_version,
                    "computed_at": python_hashes.computed_at,
                }
            if expected_python_hash is not None:
                request_obj["expected_python_hash"] = expected_python_hash
            request_obj["skip_registry"] = skip_registry
            request_obj["skip_file_integrity"] = skip_file_integrity
            request_obj["skip_audit"] = skip_audit
            request_obj["partial_file_check"] = partial_file_check

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
                    self._lib.ciris_verify_free(result_data.value)

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
        key_fingerprint: Optional[str] = None,
        python_hashes: Optional[PythonModuleHashes] = None,
        expected_python_hash: Optional[str] = None,
        partial_file_check: bool = False,
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
            key_fingerprint: Agent key fingerprint for registry verification (v0.8.1+).
            python_hashes: Python module hashes for mobile code integrity (v0.8.1+).
            expected_python_hash: Expected total hash for Python modules (v0.8.1+).
            partial_file_check: Use partial file check mode (v0.8.1+).

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
        if key_fingerprint is not None:
            request_obj["key_fingerprint"] = key_fingerprint
        if python_hashes is not None:
            # Convert PythonModuleHashes to dict for JSON serialization
            request_obj["python_hashes"] = {
                "total_hash": python_hashes.total_hash,
                "module_hashes": python_hashes.module_hashes,
                "module_count": python_hashes.module_count,
                "agent_version": python_hashes.agent_version,
                "computed_at": python_hashes.computed_at,
            }
        if expected_python_hash is not None:
            request_obj["expected_python_hash"] = expected_python_hash
        request_obj["skip_registry"] = skip_registry
        request_obj["skip_file_integrity"] = skip_file_integrity
        request_obj["skip_audit"] = skip_audit
        request_obj["partial_file_check"] = partial_file_check

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
                self._lib.ciris_verify_free(result_data.value)

    # ========================================================================
    # Device Attestation Failure Reporting (v1.5.3)
    # ========================================================================

    @property
    def has_device_attestation_failed_support(self) -> bool:
        """Check if device_attestation_failed is available.

        Returns:
            True if the library supports device_attestation_failed (>= 1.5.3).
        """
        return getattr(self, "_has_device_attestation_failed_support", False)

    def device_attestation_failed_sync(
        self,
        platform: str,
        error_code: int,
        error_message: Optional[str] = None,
    ) -> None:
        """Report device attestation failure (Play Integrity / App Attest).

        Call this when Play Integrity token acquisition fails (Android) or
        App Attest attestation fails (iOS) before reaching the verify endpoint.
        This caches the failure so run_attestation returns level_pending=false.

        Args:
            platform: Platform identifier ("android" or "ios").
            error_code: Platform-specific error code (e.g., -16 for Play Integrity).
            error_message: Optional human-readable error description.

        Raises:
            RuntimeError: If device_attestation_failed is not available.
            ValueError: If platform is not "android" or "ios".
            VerificationFailedError: If the call fails.
        """
        if not self.has_device_attestation_failed_support:
            raise RuntimeError(
                "device_attestation_failed not available in this library version (requires >= 1.5.3)"
            )

        if platform not in ("android", "ios"):
            raise ValueError("platform must be 'android' or 'ios'")

        platform_bytes = platform.encode("utf-8")
        error_msg_bytes = error_message.encode("utf-8") if error_message else None

        ret = self._lib.ciris_verify_device_attestation_failed(
            self._handle,
            platform_bytes,
            error_code,
            error_msg_bytes,
        )

        if ret != 0:
            raise VerificationFailedError(
                ret, f"device_attestation_failed failed with code {ret}"
            )

    async def device_attestation_failed(
        self,
        platform: str,
        error_code: int,
        error_message: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        """Async version of device_attestation_failed_sync.

        Args:
            platform: Platform identifier ("android" or "ios").
            error_code: Platform-specific error code.
            error_message: Optional human-readable error description.
            timeout: Operation timeout in seconds.

        Raises:
            RuntimeError: If device_attestation_failed is not available.
            ValueError: If platform is not "android" or "ios".
            VerificationFailedError: If the call fails.
            TimeoutError: If operation times out.
        """
        timeout = timeout or self._timeout

        def _run() -> None:
            self.device_attestation_failed_sync(platform, error_code, error_message)

        loop = asyncio.get_event_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(self._executor, _run),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise CIRISTimeoutError("device_attestation_failed", timeout)

    # ========================================================================
    # Manifest Cache - Offline L1 Verification
    # ========================================================================

    @property
    def has_manifest_cache_support(self) -> bool:
        """Check if manifest cache functions are available.

        Returns:
            True if the library supports manifest caching (>= 1.2.0).
        """
        return getattr(self, "_has_manifest_cache_support", False)

    @property
    def has_hardware_info_support(self) -> bool:
        """Check if hardware info functions are available.

        Returns:
            True if the library supports hardware info detection (>= 1.2.0).
        """
        return getattr(self, "_has_hardware_info_support", False)

    def save_manifest_cache_sync(
        self,
        binary_manifest: dict,
        function_manifest: Optional[dict] = None,
        build_record: Optional[dict] = None,
    ) -> bool:
        """Save manifests to a hardware-signed cache for offline L1 verification.

        After successful attestation with registry access, call this to cache
        the manifests locally with a hardware signature. When the registry is
        unreachable, the cached manifest can be used for L1 self-verification.

        The cache is signed by the Ed25519 hardware key, ensuring:
        - Authenticity: Only this device could have created the cache
        - Integrity: Tampering invalidates the hardware signature
        - No expiration: Valid as long as the binary and key are unchanged

        Args:
            binary_manifest: BinaryManifest dict from registry (required).
            function_manifest: FunctionManifest dict (optional).
            build_record: BuildRecord dict for file integrity (optional).

        Returns:
            True if cache was saved successfully.

        Raises:
            RuntimeError: If manifest cache support is not available.
            VerificationFailedError: If no key is available or signing fails.
        """
        if not self.has_manifest_cache_support:
            raise RuntimeError("Manifest cache not available in this library version (requires >= 1.2.0)")

        binary_bytes = json.dumps(binary_manifest).encode("utf-8")
        func_bytes = json.dumps(function_manifest).encode("utf-8") if function_manifest else None
        build_bytes = json.dumps(build_record).encode("utf-8") if build_record else None

        ret = self._lib.ciris_verify_save_manifest_cache(
            self._handle,
            binary_bytes,
            len(binary_bytes),
            func_bytes,
            len(func_bytes) if func_bytes else 0,
            build_bytes,
            len(build_bytes) if build_bytes else 0,
        )

        if ret == -5:  # NoKey
            raise VerificationFailedError(ret, "No signing key available to sign manifest cache")
        if ret == -6:  # SigningFailed
            raise VerificationFailedError(ret, "Failed to sign manifest cache")
        if ret != 0:
            raise VerificationFailedError(ret, f"save_manifest_cache failed with code {ret}")

        return True

    def load_manifest_cache_sync(self) -> Optional[dict]:
        """Load and verify a cached manifest for offline L1 verification.

        Returns the cached manifest if signature verification passes.
        Use this when the registry is unreachable to still perform L1 self-verification.

        Returns:
            SignedManifestCache dict if valid, None if not found.
            Contains: binary_manifest, function_manifest, build_record,
                     cached_at, verify_version, target, public_key_fingerprint

        Raises:
            RuntimeError: If manifest cache support is not available.
            VerificationFailedError: If signature verification fails (tampering detected).
        """
        if not self.has_manifest_cache_support:
            raise RuntimeError("Manifest cache not available in this library version (requires >= 1.2.0)")

        result_data = ctypes.c_void_p()
        result_len = ctypes.c_size_t()

        ret = self._lib.ciris_verify_load_manifest_cache(
            self._handle,
            ctypes.byref(result_data),
            ctypes.byref(result_len),
        )

        if ret == -8:  # CacheNotFound
            return None
        if ret == -9:  # SignatureInvalid
            raise VerificationFailedError(ret, "Manifest cache signature invalid - possible tampering!")
        if ret == -10:  # VersionMismatch
            raise VerificationFailedError(ret, "Manifest cache version/target mismatch")
        if ret != 0:
            raise VerificationFailedError(ret, f"load_manifest_cache failed with code {ret}")

        try:
            result_bytes = ctypes.string_at(result_data.value, result_len.value)
            return json.loads(result_bytes)
        finally:
            if result_data.value:
                self._lib.ciris_verify_free(result_data.value)

    def manifest_cache_exists_sync(self) -> bool:
        """Check if a signed manifest cache exists.

        Quick check without loading or verifying the cache.

        Returns:
            True if a cache file exists, False otherwise.
        """
        if not self.has_manifest_cache_support:
            return False

        ret = self._lib.ciris_verify_manifest_cache_exists(self._handle)
        return ret == 1

    # ========================================================================
    # Hardware Information
    # ========================================================================

    def get_hardware_info_sync(self) -> Optional[HardwareInfo]:
        """Get hardware information and security limitations.

        Detects platform-specific hardware characteristics that affect
        attestation trust level:
        - Emulator/VM detection (mobile emulators are suspicious)
        - Root/jailbreak detection
        - SoC vulnerability detection (e.g., MediaTek CVE-2026-20435)
        - TEE implementation identification

        Returns:
            HardwareInfo with platform details and detected limitations,
            or None if detection fails.

        Note:
            On Android, call get_hardware_info_android_sync() with JNI
            properties for more accurate detection.
        """
        if not self._has_hardware_info_support:
            return None

        result_ptr = ctypes.POINTER(ctypes.c_uint8)()
        result_len = ctypes.c_size_t()

        ret = self._lib.ciris_verify_get_hardware_info(
            self._handle,
            ctypes.byref(result_ptr),
            ctypes.byref(result_len),
        )

        if ret != 0:
            return None

        try:
            data = ctypes.string_at(result_ptr, result_len.value)
            self._lib.ciris_verify_free(result_ptr)
            parsed = json.loads(data)
            return self._parse_hardware_info(parsed)
        except Exception:
            return None

    def get_hardware_info_android_sync(
        self,
        hardware: str,
        board: str,
        manufacturer: str,
        model: str,
        security_patch: str,
        fingerprint: str,
    ) -> Optional[HardwareInfo]:
        """Get hardware information with Android-specific properties.

        On Android, some hardware properties can only be read via JNI.
        This method allows the Android app to pass these properties for
        more accurate detection of SoC vulnerabilities.

        Args:
            hardware: Build.HARDWARE value
            board: Build.BOARD value
            manufacturer: Build.MANUFACTURER value
            model: Build.MODEL value
            security_patch: Build.VERSION.SECURITY_PATCH value
            fingerprint: Build.FINGERPRINT value

        Returns:
            HardwareInfo with Android-specific details and detected limitations.
        """
        if not self._has_hardware_info_support:
            return None

        result_ptr = ctypes.POINTER(ctypes.c_uint8)()
        result_len = ctypes.c_size_t()

        ret = self._lib.ciris_verify_get_hardware_info_android(
            self._handle,
            hardware.encode("utf-8") + b"\0",
            board.encode("utf-8") + b"\0",
            manufacturer.encode("utf-8") + b"\0",
            model.encode("utf-8") + b"\0",
            security_patch.encode("utf-8") + b"\0",
            fingerprint.encode("utf-8") + b"\0",
            ctypes.byref(result_ptr),
            ctypes.byref(result_len),
        )

        if ret != 0:
            return None

        try:
            data = ctypes.string_at(result_ptr, result_len.value)
            self._lib.ciris_verify_free(result_ptr)
            parsed = json.loads(data)
            return self._parse_hardware_info(parsed)
        except Exception:
            return None

    def _parse_hardware_info(self, data: dict) -> HardwareInfo:
        """Parse JSON hardware info into HardwareInfo object."""
        limitations = []
        for lim in data.get("limitations", []):
            # Handle Rust enum serialization (externally tagged)
            if isinstance(lim, dict):
                if "Emulator" in lim or lim == "Emulator":
                    limitations.append(HardwareLimitation(limitation_type="Emulator"))
                elif "RootedDevice" in lim or lim == "RootedDevice":
                    limitations.append(HardwareLimitation(limitation_type="RootedDevice"))
                elif "UnlockedBootloader" in lim or lim == "UnlockedBootloader":
                    limitations.append(HardwareLimitation(limitation_type="UnlockedBootloader"))
                elif "VulnerableSoC" in lim:
                    vuln = lim["VulnerableSoC"]
                    advisory = vuln.get("advisory", {})
                    limitations.append(HardwareLimitation(
                        limitation_type="VulnerableSoC",
                        manufacturer=vuln.get("manufacturer"),
                        advisory=SecurityAdvisory(
                            cve=advisory.get("cve", ""),
                            title=advisory.get("title", ""),
                            impact=advisory.get("impact", ""),
                            software_patchable=advisory.get("software_patchable", False),
                            min_patch_level=advisory.get("min_patch_level"),
                        ),
                    ))
                elif "WeakTEE" in lim:
                    limitations.append(HardwareLimitation(
                        limitation_type="WeakTEE",
                        reason=lim["WeakTEE"].get("reason"),
                    ))
                elif "OutdatedPatchLevel" in lim:
                    patch = lim["OutdatedPatchLevel"]
                    limitations.append(HardwareLimitation(
                        limitation_type="OutdatedPatchLevel",
                        current_patch=patch.get("current"),
                        minimum_patch=patch.get("minimum_required"),
                    ))

        return HardwareInfo(
            platform=data.get("platform", "unknown"),
            soc_manufacturer=data.get("soc_manufacturer"),
            soc_model=data.get("soc_model"),
            security_patch_level=data.get("security_patch_level"),
            is_emulator=data.get("is_emulator", False),
            is_suspicious_emulator=data.get("is_suspicious_emulator", False),
            bootloader_unlocked=data.get("bootloader_unlocked"),
            tee_implementation=data.get("tee_implementation"),
            is_rooted=data.get("is_rooted", False),
            limitations=limitations,
            hardware_trust_degraded=data.get("hardware_trust_degraded", False),
            trust_degradation_reason=data.get("trust_degradation_reason"),
        )

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
            AttestationInProgressError: If attestation is currently running.
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

        if ret == CIRIS_ERROR_ATTESTATION_IN_PROGRESS:
            raise AttestationInProgressError("import_key")
        return ret == 0

    def await_key_registration(self, timeout_seconds: int = 5) -> dict:
        """Wait for key registration in registry after portal import.

        Polls registry endpoints once per second until the key is confirmed
        as "active" or timeout is reached.

        Args:
            timeout_seconds: Maximum time to wait (default 5 seconds).

        Returns:
            dict with keys:
                - status: "active" (ready), "pending" (timeout), or "error"
                - fingerprint: The key's fingerprint
                - elapsed_ms: Time spent waiting
                - attempts: Number of registry checks made
                - error: Error message if status is "error"

        Raises:
            NotImplementedError: If Ed25519 support is not available.

        Example:
            verifier.import_key_sync(portal_key)
            result = verifier.await_key_registration()
            if result["status"] == "active":
                # Key confirmed in registry, attestation will have key_type="portal"
                attestation = verifier.attestation_with_challenge(challenge)
            elif result["status"] == "pending":
                # Timeout, but can still proceed with key_type="pending"
                attestation = verifier.attestation_with_challenge(challenge)
        """
        if not self._has_ed25519_support:
            raise NotImplementedError(
                "Ed25519 key functions not available in this library version."
            )

        # Check if the FFI function exists
        if not hasattr(self._lib, "ciris_verify_await_key_registration"):
            # Fallback for older library versions
            return {
                "status": "error",
                "error": "await_key_registration not available in this library version",
                "fingerprint": "",
                "elapsed_ms": 0,
                "attempts": 0,
            }

        result_ptr = ctypes.c_char_p()
        ret = self._lib.ciris_verify_await_key_registration(
            self._handle,
            ctypes.byref(result_ptr),
        )

        if ret != 0:
            return {
                "status": "error",
                "error": f"FFI call failed with code {ret}",
                "fingerprint": "",
                "elapsed_ms": 0,
                "attempts": 0,
            }

        if result_ptr.value:
            import json
            result_json = result_ptr.value.decode("utf-8")
            self._lib.ciris_verify_free_string(result_ptr)
            return json.loads(result_json)
        else:
            return {
                "status": "error",
                "error": "null result from FFI",
                "fingerprint": "",
                "elapsed_ms": 0,
                "attempts": 0,
            }

    def has_key_sync(self) -> bool:
        """Check if an Ed25519 signing key is loaded.

        Returns:
            True if a key is loaded, False otherwise.

        Raises:
            NotImplementedError: If Ed25519 support is not available.
            AttestationInProgressError: If attestation is currently running.
        """
        if not self._has_ed25519_support:
            raise NotImplementedError(
                "Ed25519 key functions not available in this library version."
            )
        ret = self._lib.ciris_verify_has_key(self._handle)
        if ret == CIRIS_ERROR_ATTESTATION_IN_PROGRESS:
            raise AttestationInProgressError("has_key")
        return ret == 1

    def delete_key_sync(self) -> bool:
        """Delete the loaded Ed25519 signing key.

        Returns:
            True if deletion succeeded, False otherwise.

        Raises:
            NotImplementedError: If Ed25519 support is not available.
            AttestationInProgressError: If attestation is currently running.
        """
        if not self._has_ed25519_support:
            raise NotImplementedError(
                "Ed25519 key functions not available in this library version."
            )
        ret = self._lib.ciris_verify_delete_key(self._handle)
        if ret == CIRIS_ERROR_ATTESTATION_IN_PROGRESS:
            raise AttestationInProgressError("delete_key")
        return ret == 0

    def generate_key_sync(self) -> bool:
        """Generate a new ephemeral Ed25519 signing key.

        This creates an ephemeral key that can be used for attestation before
        Portal issues a permanent key. The key is stored with hardware protection
        (TPM/Keystore/Secure Enclave) if available.

        Use cases:
            - Initial attestation before Portal key activation
            - Recovery after orphaned key cleanup
            - Testing/development without Portal

        Returns:
            True if key was generated successfully, False otherwise.
            Returns True if a key already exists (idempotent).

        Raises:
            NotImplementedError: If Ed25519 support is not available.
            AttestationInProgressError: If attestation is currently running.

        Example:
            # Generate ephemeral key for initial attestation
            if not verifier.has_key_sync():
                verifier.generate_key_sync()

            # Now attestation will work with ephemeral key
            attestation = verifier.run_attestation_sync(challenge)
            # attestation["key_attestation"]["key_type"] == "ephemeral"
        """
        if not self._has_ed25519_support:
            raise NotImplementedError(
                "Ed25519 key functions not available in this library version."
            )

        # Check if the FFI function exists
        if not hasattr(self._lib, "ciris_verify_generate_key"):
            raise NotImplementedError(
                "generate_key not available in this library version. "
                "Update to ciris-verify >= 1.1.16."
            )

        ret = self._lib.ciris_verify_generate_key(self._handle)
        if ret == CIRIS_ERROR_ATTESTATION_IN_PROGRESS:
            raise AttestationInProgressError("generate_key")
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
            AttestationInProgressError: If attestation is currently running.
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

        if ret == CIRIS_ERROR_ATTESTATION_IN_PROGRESS:
            raise AttestationInProgressError("sign_ed25519")
        if ret != 0:
            raise VerificationFailedError(ret, f"Ed25519 signing failed with code {ret}")

        try:
            return ctypes.string_at(sig_data.value, sig_len.value)
        finally:
            if sig_data.value:
                self._lib.ciris_verify_free(sig_data.value)

    def get_ed25519_public_key_sync(self) -> bytes:
        """Get the Ed25519 public key from the Portal-issued key.

        Returns:
            32-byte Ed25519 public key.

        Raises:
            NotImplementedError: If Ed25519 support is not available.
            VerificationFailedError: If no key is loaded.
            AttestationInProgressError: If attestation is currently running.
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

        if ret == CIRIS_ERROR_ATTESTATION_IN_PROGRESS:
            raise AttestationInProgressError("get_ed25519_public_key")
        if ret != 0:
            raise VerificationFailedError(ret, f"Get Ed25519 public key failed with code {ret}")

        try:
            return ctypes.string_at(key_data.value, key_len.value)
        finally:
            if key_data.value:
                self._lib.ciris_verify_free(key_data.value)

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
                self._lib.ciris_verify_free(diag_data.value)

    # =========================================================================
    # EVM WALLET SIGNING (v1.3.0)
    # =========================================================================

    def get_wallet_info(self) -> dict:
        """Get wallet information including derived secp256k1 public key and EVM address.

        The secp256k1 key is deterministically derived from the Ed25519 root identity
        using HKDF, ensuring a consistent wallet address across sessions.

        Returns:
            dict: Wallet info with keys:
                - secp256k1_public_key: 65-byte uncompressed pubkey as hex
                - evm_address: 20-byte address as checksummed hex (0x...)
                - derivation_path: Description of the key derivation

        Raises:
            CommunicationError: If wallet info retrieval fails.
            VerificationFailedError: If no Ed25519 key is loaded.
        """
        if not getattr(self, '_has_wallet_support', False):
            raise CommunicationError("Wallet support not available (library version < 1.3.0)")

        result_json = ctypes.POINTER(ctypes.c_uint8)()
        result_len = ctypes.c_size_t()

        ret = self._lib.ciris_verify_get_wallet_info(
            self._handle,
            ctypes.byref(result_json),
            ctypes.byref(result_len),
        )

        if ret == CIRIS_ERROR_ATTESTATION_IN_PROGRESS:
            raise AttestationInProgressError()
        if ret != 0:
            raise VerificationFailedError(f"get_wallet_info failed with code {ret}")

        try:
            json_bytes = ctypes.string_at(result_json, result_len.value)
            return json.loads(json_bytes.decode("utf-8"))
        finally:
            if result_json:
                self._lib.ciris_verify_free(result_json)

    def derive_secp256k1_pubkey(self) -> bytes:
        """Derive the secp256k1 public key from the Ed25519 seed.

        The derivation is deterministic: the same Ed25519 seed always produces
        the same secp256k1 public key.

        Returns:
            bytes: 65-byte uncompressed public key (04 || x || y)

        Raises:
            CommunicationError: If derivation fails.
            VerificationFailedError: If no Ed25519 key is loaded.
        """
        if not getattr(self, '_has_wallet_support', False):
            raise CommunicationError("Wallet support not available (library version < 1.3.0)")

        pubkey_data = ctypes.POINTER(ctypes.c_uint8)()
        pubkey_len = ctypes.c_size_t()

        ret = self._lib.ciris_verify_derive_secp256k1_pubkey(
            self._handle,
            ctypes.byref(pubkey_data),
            ctypes.byref(pubkey_len),
        )

        if ret == CIRIS_ERROR_ATTESTATION_IN_PROGRESS:
            raise AttestationInProgressError()
        if ret != 0:
            raise VerificationFailedError(f"derive_secp256k1_pubkey failed with code {ret}")

        try:
            return ctypes.string_at(pubkey_data, pubkey_len.value)
        finally:
            if pubkey_data:
                self._lib.ciris_verify_free(pubkey_data)

    def get_evm_address(self, pubkey: bytes = None) -> bytes:
        """Get the EVM address from a secp256k1 public key.

        The address is derived by taking keccak256 of the public key (without
        the 04 prefix) and taking the last 20 bytes.

        Args:
            pubkey: 65-byte uncompressed secp256k1 public key. If None, derives
                   the public key first from the Ed25519 seed.

        Returns:
            bytes: 20-byte EVM address

        Raises:
            CommunicationError: If address derivation fails.
            ValueError: If pubkey is not 65 bytes.
        """
        if not getattr(self, '_has_wallet_support', False):
            raise CommunicationError("Wallet support not available (library version < 1.3.0)")

        if pubkey is None:
            pubkey = self.derive_secp256k1_pubkey()

        if len(pubkey) != 65:
            raise ValueError(f"pubkey must be 65 bytes, got {len(pubkey)}")

        pubkey_array = (ctypes.c_uint8 * 65).from_buffer_copy(pubkey)
        address_data = ctypes.POINTER(ctypes.c_uint8)()
        address_len = ctypes.c_size_t()

        ret = self._lib.ciris_verify_get_evm_address(
            pubkey_array,
            ctypes.c_size_t(65),
            ctypes.byref(address_data),
            ctypes.byref(address_len),
        )

        if ret != 0:
            raise CommunicationError(f"get_evm_address failed with code {ret}")

        try:
            return ctypes.string_at(address_data, address_len.value)
        finally:
            if address_data:
                self._lib.ciris_verify_free(address_data)

    def get_evm_address_checksummed(self, pubkey: bytes = None) -> str:
        """Get the checksummed EVM address string from a secp256k1 public key.

        Implements EIP-55 checksum encoding.

        Args:
            pubkey: 65-byte uncompressed secp256k1 public key. If None, derives
                   the public key first from the Ed25519 seed.

        Returns:
            str: Checksummed EVM address (e.g., "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed")

        Raises:
            CommunicationError: If address derivation fails.
            ValueError: If pubkey is not 65 bytes.
        """
        if not getattr(self, '_has_wallet_support', False):
            raise CommunicationError("Wallet support not available (library version < 1.3.0)")

        if pubkey is None:
            pubkey = self.derive_secp256k1_pubkey()

        if len(pubkey) != 65:
            raise ValueError(f"pubkey must be 65 bytes, got {len(pubkey)}")

        pubkey_array = (ctypes.c_uint8 * 65).from_buffer_copy(pubkey)
        address_str = ctypes.c_char_p()
        address_len = ctypes.c_size_t()

        ret = self._lib.ciris_verify_get_evm_address_checksummed(
            pubkey_array,
            ctypes.c_size_t(65),
            ctypes.byref(address_str),
            ctypes.byref(address_len),
        )

        if ret != 0:
            raise CommunicationError(f"get_evm_address_checksummed failed with code {ret}")

        try:
            return address_str.value.decode("utf-8")
        finally:
            if address_str.value:
                self._lib.ciris_verify_free(ctypes.cast(address_str, ctypes.c_void_p))

    def sign_secp256k1(self, message_hash: bytes) -> bytes:
        """Sign a 32-byte message hash with the derived secp256k1 key.

        Args:
            message_hash: 32-byte hash to sign (typically keccak256)

        Returns:
            bytes: 65-byte signature (r || s || v) where v is the recovery id (0 or 1)

        Raises:
            CommunicationError: If signing fails.
            VerificationFailedError: If no Ed25519 key is loaded.
            ValueError: If message_hash is not 32 bytes.
        """
        if not getattr(self, '_has_wallet_support', False):
            raise CommunicationError("Wallet support not available (library version < 1.3.0)")

        if len(message_hash) != 32:
            raise ValueError(f"message_hash must be 32 bytes, got {len(message_hash)}")

        hash_array = (ctypes.c_uint8 * 32).from_buffer_copy(message_hash)
        signature_data = ctypes.POINTER(ctypes.c_uint8)()
        signature_len = ctypes.c_size_t()

        ret = self._lib.ciris_verify_sign_secp256k1(
            self._handle,
            hash_array,
            ctypes.c_size_t(32),
            ctypes.byref(signature_data),
            ctypes.byref(signature_len),
        )

        if ret == CIRIS_ERROR_ATTESTATION_IN_PROGRESS:
            raise AttestationInProgressError()
        if ret != 0:
            raise VerificationFailedError(f"sign_secp256k1 failed with code {ret}")

        try:
            return ctypes.string_at(signature_data, signature_len.value)
        finally:
            if signature_data:
                self._lib.ciris_verify_free(signature_data)

    def sign_evm_transaction(self, tx_hash: bytes, chain_id: int) -> bytes:
        """Sign an EVM transaction hash with EIP-155 replay protection.

        Args:
            tx_hash: 32-byte transaction hash
            chain_id: EVM chain ID for replay protection (e.g., 1 for mainnet, 8453 for Base)

        Returns:
            bytes: 65-byte signature with EIP-155 adjusted v value (27 or 28)

        Raises:
            CommunicationError: If signing fails.
            VerificationFailedError: If no Ed25519 key is loaded.
            ValueError: If tx_hash is not 32 bytes.
        """
        if not getattr(self, '_has_wallet_support', False):
            raise CommunicationError("Wallet support not available (library version < 1.3.0)")

        if len(tx_hash) != 32:
            raise ValueError(f"tx_hash must be 32 bytes, got {len(tx_hash)}")

        hash_array = (ctypes.c_uint8 * 32).from_buffer_copy(tx_hash)
        signature_data = ctypes.POINTER(ctypes.c_uint8)()
        signature_len = ctypes.c_size_t()

        ret = self._lib.ciris_verify_sign_evm_transaction(
            self._handle,
            hash_array,
            ctypes.c_size_t(32),
            ctypes.c_uint64(chain_id),
            ctypes.byref(signature_data),
            ctypes.byref(signature_len),
        )

        if ret == CIRIS_ERROR_ATTESTATION_IN_PROGRESS:
            raise AttestationInProgressError()
        if ret != 0:
            raise VerificationFailedError(f"sign_evm_transaction failed with code {ret}")

        try:
            return ctypes.string_at(signature_data, signature_len.value)
        finally:
            if signature_data:
                self._lib.ciris_verify_free(signature_data)

    def sign_typed_data(self, domain_hash: bytes, message_hash: bytes) -> bytes:
        """Sign EIP-712 typed data.

        Args:
            domain_hash: 32-byte domain separator hash
            message_hash: 32-byte struct hash

        Returns:
            bytes: 65-byte signature over keccak256(0x1901 || domain_hash || message_hash)

        Raises:
            CommunicationError: If signing fails.
            VerificationFailedError: If no Ed25519 key is loaded.
            ValueError: If hashes are not 32 bytes.
        """
        if not getattr(self, '_has_wallet_support', False):
            raise CommunicationError("Wallet support not available (library version < 1.3.0)")

        if len(domain_hash) != 32:
            raise ValueError(f"domain_hash must be 32 bytes, got {len(domain_hash)}")
        if len(message_hash) != 32:
            raise ValueError(f"message_hash must be 32 bytes, got {len(message_hash)}")

        domain_array = (ctypes.c_uint8 * 32).from_buffer_copy(domain_hash)
        message_array = (ctypes.c_uint8 * 32).from_buffer_copy(message_hash)
        signature_data = ctypes.POINTER(ctypes.c_uint8)()
        signature_len = ctypes.c_size_t()

        ret = self._lib.ciris_verify_sign_typed_data(
            self._handle,
            domain_array,
            ctypes.c_size_t(32),
            message_array,
            ctypes.c_size_t(32),
            ctypes.byref(signature_data),
            ctypes.byref(signature_len),
        )

        if ret == CIRIS_ERROR_ATTESTATION_IN_PROGRESS:
            raise AttestationInProgressError()
        if ret != 0:
            raise VerificationFailedError(f"sign_typed_data failed with code {ret}")

        try:
            return ctypes.string_at(signature_data, signature_len.value)
        finally:
            if signature_data:
                self._lib.ciris_verify_free(signature_data)

    def recover_evm_address(self, message_hash: bytes, signature: bytes) -> bytes:
        """Recover the signer's EVM address from a signature.

        Args:
            message_hash: 32-byte hash that was signed
            signature: 65-byte signature (r || s || v)

        Returns:
            bytes: 20-byte recovered EVM address

        Raises:
            CommunicationError: If recovery fails (invalid signature).
            ValueError: If arguments are wrong length.
        """
        if not getattr(self, '_has_wallet_support', False):
            raise CommunicationError("Wallet support not available (library version < 1.3.0)")

        if len(message_hash) != 32:
            raise ValueError(f"message_hash must be 32 bytes, got {len(message_hash)}")
        if len(signature) != 65:
            raise ValueError(f"signature must be 65 bytes, got {len(signature)}")

        hash_array = (ctypes.c_uint8 * 32).from_buffer_copy(message_hash)
        sig_array = (ctypes.c_uint8 * 65).from_buffer_copy(signature)
        address_data = ctypes.POINTER(ctypes.c_uint8)()
        address_len = ctypes.c_size_t()

        ret = self._lib.ciris_verify_recover_evm_address(
            hash_array,
            ctypes.c_size_t(32),
            sig_array,
            ctypes.c_size_t(65),
            ctypes.byref(address_data),
            ctypes.byref(address_len),
        )

        if ret != 0:
            raise CommunicationError(f"recover_evm_address failed with code {ret}")

        try:
            return ctypes.string_at(address_data, address_len.value)
        finally:
            if address_data:
                self._lib.ciris_verify_free(address_data)

    # =========================================================================
    # NAMED KEY STORAGE (v1.5.0)
    # =========================================================================

    def store_named_key(self, key_id: str, seed: bytes) -> bool:
        """Store a named Ed25519 key.

        Keys are stored with hardware protection (TPM/Keystore/SecureEnclave)
        when available.

        Args:
            key_id: Key identifier (e.g., "wa:0x1234...", "session:abc123").
            seed: 32-byte Ed25519 seed.

        Returns:
            True if the key was stored successfully.

        Raises:
            NotImplementedError: If named key support is not available.
            ValueError: If seed is not 32 bytes.
            AttestationInProgressError: If attestation is currently running.
        """
        if not self._has_named_key_support:
            raise NotImplementedError(
                "Named key functions not available (library version < 1.5.0)"
            )
        if len(seed) != 32:
            raise ValueError(f"seed must be 32 bytes, got {len(seed)}")

        key_id_bytes = key_id.encode("utf-8")
        ret = self._lib.ciris_verify_store_named_key(
            self._handle, key_id_bytes, seed, len(seed)
        )

        if ret == CIRIS_ERROR_ATTESTATION_IN_PROGRESS:
            raise AttestationInProgressError("store_named_key")
        return ret == 0

    def sign_with_named_key(self, key_id: str, data: bytes) -> bytes:
        """Sign data with a named Ed25519 key.

        Args:
            key_id: Key identifier.
            data: Data to sign.

        Returns:
            64-byte Ed25519 signature.

        Raises:
            NotImplementedError: If named key support is not available.
            VerificationFailedError: If the key is not found or signing fails.
            AttestationInProgressError: If attestation is currently running.
        """
        if not self._has_named_key_support:
            raise NotImplementedError(
                "Named key functions not available (library version < 1.5.0)"
            )

        sig_data = ctypes.c_void_p()
        sig_len = ctypes.c_size_t()
        key_id_bytes = key_id.encode("utf-8")

        ret = self._lib.ciris_verify_sign_with_named_key(
            self._handle,
            key_id_bytes,
            data,
            len(data),
            ctypes.byref(sig_data),
            ctypes.byref(sig_len),
        )

        if ret == CIRIS_ERROR_ATTESTATION_IN_PROGRESS:
            raise AttestationInProgressError("sign_with_named_key")
        if ret != 0:
            raise VerificationFailedError(
                ret, f"sign_with_named_key failed with code {ret}"
            )

        try:
            return ctypes.string_at(sig_data.value, sig_len.value)
        finally:
            if sig_data.value:
                self._lib.ciris_verify_free(sig_data.value)

    def has_named_key(self, key_id: str) -> bool:
        """Check if a named key exists.

        Args:
            key_id: Key identifier.

        Returns:
            True if the key exists, False otherwise.

        Raises:
            NotImplementedError: If named key support is not available.
            AttestationInProgressError: If attestation is currently running.
        """
        if not self._has_named_key_support:
            raise NotImplementedError(
                "Named key functions not available (library version < 1.5.0)"
            )

        key_id_bytes = key_id.encode("utf-8")
        ret = self._lib.ciris_verify_has_named_key(self._handle, key_id_bytes)

        if ret == CIRIS_ERROR_ATTESTATION_IN_PROGRESS:
            raise AttestationInProgressError("has_named_key")
        return ret == 1

    def delete_named_key(self, key_id: str) -> bool:
        """Delete a named key.

        Args:
            key_id: Key identifier.

        Returns:
            True if the key was deleted successfully.

        Raises:
            NotImplementedError: If named key support is not available.
            AttestationInProgressError: If attestation is currently running.
        """
        if not self._has_named_key_support:
            raise NotImplementedError(
                "Named key functions not available (library version < 1.5.0)"
            )

        key_id_bytes = key_id.encode("utf-8")
        ret = self._lib.ciris_verify_delete_named_key(self._handle, key_id_bytes)

        if ret == CIRIS_ERROR_ATTESTATION_IN_PROGRESS:
            raise AttestationInProgressError("delete_named_key")
        return ret == 0

    def get_named_key_public(self, key_id: str) -> bytes:
        """Get the public key for a named Ed25519 key.

        Args:
            key_id: Key identifier.

        Returns:
            32-byte Ed25519 public key.

        Raises:
            NotImplementedError: If named key support is not available.
            VerificationFailedError: If the key is not found.
            AttestationInProgressError: If attestation is currently running.
        """
        if not self._has_named_key_support:
            raise NotImplementedError(
                "Named key functions not available (library version < 1.5.0)"
            )

        pk_data = ctypes.c_void_p()
        pk_len = ctypes.c_size_t()
        key_id_bytes = key_id.encode("utf-8")

        ret = self._lib.ciris_verify_get_named_key_public(
            self._handle,
            key_id_bytes,
            ctypes.byref(pk_data),
            ctypes.byref(pk_len),
        )

        if ret == CIRIS_ERROR_ATTESTATION_IN_PROGRESS:
            raise AttestationInProgressError("get_named_key_public")
        if ret != 0:
            raise VerificationFailedError(
                ret, f"get_named_key_public failed with code {ret}"
            )

        try:
            return ctypes.string_at(pk_data.value, pk_len.value)
        finally:
            if pk_data.value:
                self._lib.ciris_verify_free(pk_data.value)

    def list_named_keys(self) -> list:
        """List all named keys.

        Returns:
            List of key identifiers.

        Raises:
            NotImplementedError: If named key support is not available.
            CommunicationError: If list retrieval fails.
            AttestationInProgressError: If attestation is currently running.
        """
        if not self._has_named_key_support:
            raise NotImplementedError(
                "Named key functions not available (library version < 1.5.0)"
            )

        json_out = ctypes.c_char_p()
        ret = self._lib.ciris_verify_list_named_keys(
            self._handle, ctypes.byref(json_out)
        )

        if ret == CIRIS_ERROR_ATTESTATION_IN_PROGRESS:
            raise AttestationInProgressError("list_named_keys")
        if ret != 0:
            raise CommunicationError(f"list_named_keys failed with code {ret}")

        try:
            json_str = json_out.value.decode("utf-8")
            return json.loads(json_str)
        finally:
            if json_out.value:
                self._lib.ciris_verify_free_string(json_out)


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
        key_fingerprint: Optional[str] = None,
        python_hashes: Optional[PythonModuleHashes] = None,
        expected_python_hash: Optional[str] = None,
        partial_file_check: bool = False,
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
                "registry_key_status": "active" if key_fingerprint else "not_checked",
            },
            "file_integrity": None,  # Skipped in mock
            "sources": {
                "dns_us": {"reachable": True, "valid": True},
                "dns_eu": {"reachable": True, "valid": True},
                "https": {"reachable": True, "valid": True},
            },
            "audit_trail": None,  # Skipped in mock
            "python_integrity": {
                "valid": True,
                "modules_checked": python_hashes.module_count if python_hashes else 0,
                "modules_passed": python_hashes.module_count if python_hashes else 0,
                "modules_failed": 0,
                "total_hash_valid": True,
            } if python_hashes else None,
            "registry_key_status": "active" if key_fingerprint else "not_checked",
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
        key_fingerprint: Optional[str] = None,
        python_hashes: Optional[PythonModuleHashes] = None,
        expected_python_hash: Optional[str] = None,
        partial_file_check: bool = False,
    ) -> dict:
        """Synchronous mock run_attestation."""
        if len(challenge) < 32:
            raise ValueError("challenge must be at least 32 bytes")

        return {
            "valid": True,
            "level": 3,
            "key_attestation": {
                "valid": True,
                "hardware_type": "Software",
                "registry_key_status": "active" if key_fingerprint else "not_checked",
            },
            "file_integrity": None,
            "sources": {
                "dns_us": {"reachable": True, "valid": True},
                "dns_eu": {"reachable": True, "valid": True},
                "https": {"reachable": True, "valid": True},
            },
            "audit_trail": None,
            "python_integrity": {
                "valid": True,
                "modules_checked": python_hashes.module_count if python_hashes else 0,
                "modules_passed": python_hashes.module_count if python_hashes else 0,
                "modules_failed": 0,
                "total_hash_valid": True,
            } if python_hashes else None,
            "registry_key_status": "active" if key_fingerprint else "not_checked",
            "checks_passed": 3,
            "checks_total": 3,
            "diagnostics": "[MOCK] Using MockCIRISVerify",
            "errors": [],
        }

    @property
    def has_device_attestation_failed_support(self) -> bool:
        """Mock always supports device_attestation_failed."""
        return True

    def device_attestation_failed_sync(
        self,
        platform: str,
        error_code: int,
        error_message: Optional[str] = None,
    ) -> None:
        """Mock device_attestation_failed — no-op."""
        if platform not in ("android", "ios"):
            raise ValueError("platform must be 'android' or 'ios'")
        # No-op in mock

    async def device_attestation_failed(
        self,
        platform: str,
        error_code: int,
        error_message: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        """Async mock device_attestation_failed — no-op."""
        self.device_attestation_failed_sync(platform, error_code, error_message)

    def _default_disclosure(self, status: LicenseStatus, reason: str = "") -> str:
        """Generate default disclosure for mock."""
        return super()._default_disclosure(status, reason=reason)
