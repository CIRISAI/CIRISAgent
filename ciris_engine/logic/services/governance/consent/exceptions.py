"""
Consent Service Exceptions - FAIL FAST, FAIL LOUD.

Custom exceptions for consent management operations.
Philosophy: No fake data, no silent failures, explicit errors.
"""


class ConsentNotFoundError(Exception):
    """
    Raised when consent status doesn't exist - FAIL FAST.

    This error indicates that a user has no consent record in the system.
    This is expected for users who haven't interacted yet.

    Usage:
        - Never suppress this error
        - Always propagate to caller
        - Let caller decide how to handle (create default or fail)
    """

    pass


class ConsentValidationError(Exception):
    """
    Raised when consent request is invalid - FAIL LOUD.

    This error indicates that a consent request violates business rules:
    - Missing required fields (user_id, categories for PARTNERED)
    - Invalid stream type
    - Invalid category types
    - Gaming behavior detected

    Usage:
        - Return to user with clear error message
        - Log for monitoring
        - Include reason in exception message
    """

    pass


class ConsentExpiredError(Exception):
    """
    Raised when accessing expired TEMPORARY consent.

    This error indicates that a TEMPORARY consent has exceeded its 14-day duration
    and is no longer valid. The consent record exists but is expired.

    Usage:
        - Treat as ConsentNotFoundError for most purposes
        - Trigger cleanup of expired record
        - User must re-grant consent to continue
    """

    pass


class PartnershipPendingError(Exception):
    """
    Raised when user tries to create duplicate partnership request.

    This error indicates that a user already has a pending partnership request
    that is awaiting agent approval. Only one pending request allowed per user.

    Usage:
        - Return to user with status of existing request
        - Include task_id for tracking
        - Direct user to check partnership status endpoint
    """

    pass


class DecayInProgressError(Exception):
    """
    Raised when attempting operations on user undergoing decay protocol.

    This error indicates that a user has initiated the 90-day decay protocol
    and their data is being anonymized. Most consent operations are blocked
    during decay.

    Usage:
        - Return to user with decay status
        - Include completion date
        - Only allow decay status queries and cancellation (if permitted)
    """

    pass


class DSARAutomationError(Exception):
    """
    Raised when automated DSAR processing fails.

    This error indicates that a Data Subject Access Request could not be
    processed automatically. Requires manual intervention.

    Usage:
        - Log for admin review
        - Create DSAR ticket for manual processing
        - Return to user with estimated manual processing time
    """

    pass
