"""Domain exceptions."""


class SemaFSError(Exception):
    """Base exception for all SemaFS errors."""
    pass


class NodeNotFoundError(SemaFSError):
    """Raised when a node cannot be found."""
    pass


class InvalidPathError(SemaFSError):
    """Raised when a path is invalid."""
    pass


class InvalidOperationError(SemaFSError):
    """Raised when an operation is invalid."""
    pass


class CapacityExceededError(SemaFSError):
    """Raised when capacity limits are exceeded."""
    pass
