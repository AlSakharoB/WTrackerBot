class AppError(Exception):
    """Base exception for expected application errors."""


class NotFoundError(AppError):
    """Requested entity does not exist or is not available to the user."""


class DuplicateError(AppError):
    """Entity conflicts with an existing unique value."""


class ValidationError(AppError):
    """Input does not satisfy domain constraints."""


class PermissionDeniedError(AppError):
    """Current user cannot perform the requested action."""
