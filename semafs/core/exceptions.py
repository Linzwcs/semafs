"""
Exception hierarchy for SemaFS.

This module defines a structured exception hierarchy that enables precise
error handling throughout the application. All exceptions inherit from
SemaFSError, allowing callers to catch all SemaFS-related errors with
a single except clause when needed.

Exception Categories:
    - Path/Node errors: InvalidPathError, NodeNotFoundError, NodeTypeMismatchError
    - Concurrency errors: VersionConflictError, LockAcquisitionError
    - Execution errors: PlanExecutionError, LLMAdapterError
"""
from __future__ import annotations


class SemaFSError(Exception):
    """
    Base exception for all SemaFS errors.

    All custom exceptions in SemaFS inherit from this class, enabling
    unified error handling when needed.

    Example:
        try:
            await semafs.write(path, content, payload)
        except SemaFSError as e:
            logger.error(f"SemaFS operation failed: {e}")
    """


class InvalidPathError(SemaFSError):
    """
    Raised when a path string is malformed or contains invalid characters.

    Valid paths must:
    - Contain only lowercase letters, numbers, underscores, and dots
    - Use dots as segment separators
    - Not start or end with dots

    Attributes:
        path: The invalid path that caused the error.
    """

    def __init__(self, path: str, reason: str = "") -> None:
        msg = f"Invalid path: '{path}'"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)
        self.path = path


class NodeNotFoundError(SemaFSError):
    """
    Raised when attempting to access a node that doesn't exist.

    This error typically occurs when:
    - Reading a non-existent path
    - Writing to a category that doesn't exist
    - Moving a node to a non-existent target

    Attributes:
        path: The path that was not found.
    """

    def __init__(self, path: str) -> None:
        super().__init__(f"Node not found: '{path}'")
        self.path = path


class NodeTypeMismatchError(SemaFSError):
    """
    Raised when an operation is attempted on the wrong node type.

    For example, trying to list children of a LEAF node, or trying
    to merge CATEGORY nodes (only LEAFs can be merged).

    Attributes:
        path: The path of the node with the wrong type.
    """

    def __init__(self, path: str, expected: str, actual: str) -> None:
        super().__init__(
            f"Node type mismatch at '{path}': expected {expected}, got {actual}"
        )
        self.path = path


class VersionConflictError(SemaFSError):
    """
    Raised when optimistic locking detects a concurrent modification.

    SemaFS uses optimistic concurrency control via version numbers.
    This error indicates that the node was modified by another operation
    between read and write, and the current operation should be retried.

    Attributes:
        node_id: The ID of the conflicting node.
        expected: The version number that was expected.
        actual: The current version number in the database.
    """

    def __init__(self, node_id: str, expected: int, actual: int) -> None:
        super().__init__(
            f"Version conflict for node_id={node_id}: "
            f"expected version {expected}, found {actual}"
        )
        self.node_id = node_id
        self.expected = expected
        self.actual = actual


class PlanExecutionError(SemaFSError):
    """
    Raised when the Executor fails to execute a RebalancePlan.

    This error carries information about which operation failed,
    allowing the caller to decide whether to rollback or retry.
    Note that the UnitOfWork controls transaction boundaries,
    so this exception alone doesn't trigger any rollback.

    Attributes:
        op_index: The index of the failed operation in the plan (-1 if unknown).
    """

    def __init__(self, reason: str, op_index: int = -1) -> None:
        super().__init__(f"Plan execution failed (op #{op_index}): {reason}")
        self.op_index = op_index


class LLMAdapterError(SemaFSError):
    """
    Raised when an LLM API call fails.

    This can occur due to:
    - Network errors or timeouts
    - API rate limiting
    - Invalid response format
    - Tool call not returned

    The HybridStrategy will catch this and fall back to rule-based
    reorganization when this error occurs.
    """


class LockAcquisitionError(SemaFSError):
    """
    Raised when a maintenance lock cannot be acquired.

    This indicates that another maintain() call is already processing
    the same category. The current operation should skip this category
    and try again later.

    Attributes:
        path: The path that couldn't be locked.
    """

    def __init__(self, path: str) -> None:
        super().__init__(f"Lock acquisition failed for '{path}', skipping")
        self.path = path
