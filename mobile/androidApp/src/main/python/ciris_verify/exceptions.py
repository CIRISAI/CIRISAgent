"""Exception types for CIRISVerify Python bindings."""


class CIRISVerifyError(Exception):
    """Base exception for all CIRISVerify errors."""
    pass


class BinaryNotFoundError(CIRISVerifyError):
    """CIRISVerify binary not found at expected path."""
    def __init__(self, path: str):
        self.path = path
        super().__init__(f"CIRISVerify binary not found at: {path}")


class BinaryTamperedError(CIRISVerifyError):
    """CIRISVerify binary integrity check failed.

    This is a CRITICAL security error. The binary may have been
    modified by an attacker. All operations should be halted.
    """
    def __init__(self, message: str = "Binary integrity check failed"):
        super().__init__(message)


class VerificationFailedError(CIRISVerifyError):
    """License verification failed."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Verification failed ({status_code}): {message}")


class TimeoutError(CIRISVerifyError):
    """Operation timed out."""
    def __init__(self, operation: str, timeout_seconds: float):
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        super().__init__(f"Operation '{operation}' timed out after {timeout_seconds}s")


class CommunicationError(CIRISVerifyError):
    """Error communicating with CIRISVerify binary."""
    def __init__(self, message: str, cause: Exception = None):
        self.cause = cause
        super().__init__(message)


class AttestationInProgressError(CIRISVerifyError):
    """Key operation blocked because attestation is currently running.

    This error is returned when key operations (has_key, get_public_key,
    sign, import_key) are called while attestation is in progress.

    The caller should wait ~500ms and retry. Example:

        import time
        from ciris_verify import CIRISVerify, AttestationInProgressError

        verifier = CIRISVerify()
        max_retries = 5

        for attempt in range(max_retries):
            try:
                has_key = verifier.has_key_sync()
                break
            except AttestationInProgressError:
                if attempt < max_retries - 1:
                    time.sleep(0.5)
                else:
                    raise
    """
    def __init__(self, operation: str = "key operation"):
        self.operation = operation
        super().__init__(
            f"Attestation in progress - {operation} blocked. Retry after ~500ms."
        )
