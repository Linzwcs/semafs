"""
Domain entities for SemaFS knowledge tree.

This module defines the core domain model:
- NodePath: Immutable value object for hierarchical path composition
- TreeNode: Mutable entity representing a node in the knowledge tree

Design Principles:
    1. NodePath is a frozen value object that handles path normalization
       and provides safe path manipulation methods.
    2. TreeNode is a rich domain entity with behavior methods for
       state transitions (archive, start_processing, etc.).
    3. Factory methods (new_category, new_leaf, new_fragment) enforce
       domain invariants at construction time.
"""
from __future__ import annotations
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from .enums import NodeStatus, NodeType
from .exceptions import NodeTypeMismatchError

# Regex pattern for valid path segments: lowercase alphanumeric + underscore
_VALID_SEGMENT = re.compile(r"^[a-z0-9_]+$")


def _new_id() -> str:
    """Generate a new UUID string for node identification."""
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    """Get current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class NodePath:
    """
    Immutable value object representing a hierarchical path in the knowledge tree.

    NodePath normalizes and validates path strings, ensuring consistent formatting
    across the application. Paths use dot-notation (e.g., "root.work.projects").

    Path Rules:
        - Only lowercase letters, numbers, underscores, and dots allowed
        - Dots serve as segment separators
        - Empty paths normalize to "root"
        - Leading/trailing dots are stripped

    Examples:
        >>> NodePath("Root.Work")
        NodePath('root.work')
        >>> NodePath("foo.bar").parent
        NodePath('foo')
        >>> NodePath("foo").child("bar")
        NodePath('foo.bar')

    Attributes:
        _raw: The normalized internal path string.
    """
    _raw: str

    def __init__(self, raw: str) -> None:
        """
        Initialize a NodePath from a raw string.

        Args:
            raw: Path string to normalize. Invalid characters are stripped,
                 and the result is lowercased.
        """
        # Clean: lowercase, keep only valid chars, strip dots from ends
        clean = re.sub(r"[^a-z0-9._]", "", raw.strip().lower()).strip(".")
        parts = [p for p in clean.split(".") if p]
        result = ".".join(parts) if parts else "root"
        object.__setattr__(self, "_raw", result)

    @property
    def is_root(self) -> bool:
        """Check if this path represents the root node."""
        return self._raw == "root"

    def is_direct_child_of(self, other: "NodePath") -> bool:
        """
        Check if this path is a direct child of another path.

        Args:
            other: The potential parent path.

        Returns:
            True if this path is exactly one level below other.
        """
        prefix = str(other) + "."
        if not self._raw.startswith(prefix):
            return False
        return "." not in self._raw[len(prefix):]

    def is_descendant_of(self, other: "NodePath") -> bool:
        """
        Check if this path is a descendant of another path.

        Args:
            other: The potential ancestor path.

        Returns:
            True if this path is below other (not equal).
        """
        if self == other:
            return False
        return self._raw.startswith(str(other) + ".")

    @property
    def parent(self) -> "NodePath":
        """
        Get the parent path.

        Returns:
            The parent NodePath, or self if this is root.
        """
        if self.is_root:
            return self
        return NodePath(self._raw.rsplit(".", 1)[0])

    @property
    def name(self) -> str:
        """
        Get the last segment of the path (node name).

        Returns:
            The final segment after the last dot.
        """
        return self._raw.rsplit(".", 1)[-1]

    @property
    def parent_path_str(self) -> str:
        """
        Get the parent path as a string for database storage.

        Returns:
            Empty string for root, otherwise the parent path string.
        """
        if self.is_root:
            return ""
        return str(self.parent)

    @property
    def depth(self) -> int:
        """
        Get the depth of this path in the tree.

        Returns:
            Number of segments (root = 1, root.foo = 2, etc.).
        """
        return len(self._raw.split("."))

    def child(self, segment: str) -> "NodePath":
        """
        Create a child path by appending a segment.

        Args:
            segment: The child segment name (will be normalized).

        Returns:
            A new NodePath representing the child.

        Raises:
            ValueError: If the segment normalizes to empty.
        """
        clean_seg = re.sub(r"[^a-z0-9_]", "",
                           segment.lower().replace(" ", "_")).strip("_")
        if not clean_seg:
            raise ValueError(f"Invalid path segment: '{segment}'")
        return NodePath(f"{self._raw}.{clean_seg}")

    def sibling(self, segment: str) -> "NodePath":
        """
        Create a sibling path (same parent, different name).

        Args:
            segment: The sibling segment name.

        Returns:
            A new NodePath representing the sibling.
        """
        if self.is_root:
            return self.child(segment)
        return self.parent.child(segment)

    def __str__(self) -> str:
        """Return the normalized path string."""
        return self._raw

    def __repr__(self) -> str:
        """Return a debug representation."""
        return f"NodePath({self._raw!r})"

    @classmethod
    def root(cls) -> "NodePath":
        """Factory method to create the root path."""
        return cls("root")

    @classmethod
    def from_parent_and_name(cls, parent_path: str, name: str) -> "NodePath":
        """
        Construct a NodePath from parent path and name components.

        This is the inverse of splitting a path into parent_path and name,
        commonly used when reconstructing paths from database rows.

        Args:
            parent_path: The parent path string (empty for root's children).
            name: The node name.

        Returns:
            A NodePath combining parent and name.
        """
        if not parent_path and name == "root":
            return cls.root()
        if not parent_path:
            return cls(name)
        return cls(f"{parent_path}.{name}")


@dataclass
class TreeNode:
    """
    A mutable entity representing a node in the semantic knowledge tree.

    TreeNode is the central domain object that holds both data and behavior.
    It supports two types (CATEGORY and LEAF) and four lifecycle states
    (ACTIVE, PENDING_REVIEW, PROCESSING, ARCHIVED).

    Key Design Decisions:
        - Mutable: State changes (archive, bump_version) modify in-place
        - Rich domain behavior: Methods like receive_fragment(), archive()
          encapsulate business rules
        - Version tracking: Enables optimistic concurrency control
        - Factory methods: new_category(), new_leaf(), new_fragment() enforce
          invariants at construction

    Attributes:
        parent_path: Path to the parent node (empty string for root).
        name: Node name (last segment of the full path).
        node_type: CATEGORY or LEAF.
        content: Text content (summary for categories, full content for leaves).
        display_name: Human-readable name (optional, for UI display).
        name_editable: Whether LLM can rename this node.
        payload: Arbitrary metadata dict (JSON-serializable).
        tags: List of string tags for classification.
        status: Lifecycle status (ACTIVE, PENDING_REVIEW, PROCESSING, ARCHIVED).
        is_dirty: Flag indicating category needs maintenance.
        version: Monotonically increasing version for optimistic locking.
        access_count: Number of times this node has been accessed.
        created_at: UTC timestamp of creation.
        updated_at: UTC timestamp of last modification.
        last_accessed_at: UTC timestamp of last access.
        id: UUID string identifier.
    """
    parent_path: str
    name: str
    node_type: NodeType
    content: str = ""
    display_name: Optional[str] = None
    name_editable: bool = True
    payload: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    status: NodeStatus = field(default=NodeStatus.ACTIVE)
    is_dirty: bool = False
    version: int = 1
    access_count: int = 0
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    last_accessed_at: datetime = field(default_factory=_utcnow)
    # Internal field to track original status during PROCESSING
    _original_status: Optional[NodeStatus] = field(default=None,
                                                   repr=False,
                                                   init=False)
    id: str = field(default_factory=_new_id)

    def __post_init__(self) -> None:
        """Validate invariants after initialization."""
        if self.node_type == NodeType.CATEGORY and not self.name:
            raise ValueError("CATEGORY nodes must have a name")
        if self.node_type == NodeType.LEAF and not self.payload:
            self.payload = {"_auto": True}

    @property
    def node_path(self) -> NodePath:
        """Get the full path as a NodePath object."""
        return NodePath.from_parent_and_name(self.parent_path, self.name)

    @property
    def path(self) -> str:
        """Get the full path as a string."""
        return str(self.node_path)

    @property
    def depth(self) -> int:
        """Get the depth of this node in the tree."""
        return self.node_path.depth

    def bump_version(self) -> None:
        """Increment version and update timestamp (called after any mutation)."""
        self.version += 1
        self.updated_at = _utcnow()

    def touch(self) -> None:
        """Record an access to this node."""
        self.access_count += 1
        self.last_accessed_at = _utcnow()

    def receive_fragment(self) -> None:
        """
        Mark this category as dirty when a new fragment is written to it.

        Called by SemaFS.write() to signal that this category needs
        maintenance. Only valid for CATEGORY nodes.

        Raises:
            NodeTypeMismatchError: If called on a LEAF node.
        """
        self._assert_category()
        if not self.is_dirty:
            self.is_dirty = True
            self.bump_version()

    def apply_plan_result(self,
                          content: str = None,
                          name: Optional[str] = None) -> Optional[str]:
        """
        Apply the results of a RebalancePlan execution.

        Called by the Executor after successfully executing a plan.
        Updates content and optionally renames the category.

        Args:
            content: New content/summary for this category.
            name: New name (if rename is needed and name_editable is True).

        Returns:
            The old path string if renamed, None otherwise.
            Caller uses this to trigger cascade_rename.

        Raises:
            NodeTypeMismatchError: If called on a LEAF node.
        """
        self._assert_category()
        if content is not None:
            self.content = content
        old_path_str = None
        if name is not None and self.name_editable and name != self.name:
            old_path_str = self.path
            self.name = name
        self.is_dirty = False
        self.payload.pop("_force_llm", None)
        self.bump_version()
        return old_path_str

    def request_semantic_rethink(self) -> None:
        """
        Force LLM reorganization on next maintenance cycle.

        Called when significant changes warrant deep semantic analysis,
        such as after a GROUP operation creates a new category.

        Raises:
            NodeTypeMismatchError: If called on a LEAF node.
        """
        self._assert_category()
        self.is_dirty = True
        self.payload["_force_llm"] = True
        self.bump_version()

    @classmethod
    def new_category(cls,
                     path: NodePath,
                     content: str = "",
                     display_name: Optional[str] = None,
                     name_editable: bool = True,
                     status: NodeStatus = NodeStatus.ACTIVE) -> "TreeNode":
        """
        Factory method to create a new CATEGORY node.

        Args:
            path: Full path for the category.
            content: Summary/description content.
            display_name: Human-readable name for UI.
            name_editable: Whether LLM can rename this category.
            status: Initial status (default ACTIVE).

        Returns:
            A new TreeNode configured as a CATEGORY.
        """
        return cls(parent_path=path.parent_path_str,
                   name=path.name,
                   node_type=NodeType.CATEGORY,
                   content=content,
                   display_name=display_name,
                   name_editable=name_editable,
                   payload={},
                   status=status)

    @classmethod
    def new_leaf(cls,
                 path: NodePath,
                 content: str,
                 payload: Optional[dict] = None,
                 tags: Optional[list] = None,
                 status: NodeStatus = NodeStatus.ACTIVE) -> "TreeNode":
        """
        Factory method to create a new LEAF node.

        Args:
            path: Full path for the leaf.
            content: Full content of the knowledge fragment.
            payload: Metadata dict (will be JSON-serialized).
            tags: List of classification tags.
            status: Initial status (default ACTIVE).

        Returns:
            A new TreeNode configured as a LEAF.
        """
        return cls(parent_path=path.parent_path_str,
                   name=path.name,
                   node_type=NodeType.LEAF,
                   content=content,
                   payload=payload or {"_leaf": True},
                   tags=tags or [],
                   status=status)

    @classmethod
    def new_fragment(cls,
                     parent_path: NodePath,
                     content: str,
                     payload: Optional[dict] = None) -> "TreeNode":
        """
        Factory method to create a new pending fragment.

        Fragments are LEAF nodes with PENDING_REVIEW status, created
        by SemaFS.write() and later processed by maintain().

        Args:
            parent_path: Path to the parent category.
            content: Content of the fragment.
            payload: Optional metadata.

        Returns:
            A new TreeNode configured as a pending fragment.
        """
        frag_id = uuid.uuid4().hex[:8]
        real_payload = dict(payload or {})
        real_payload["_created_at"] = _utcnow().isoformat()
        return cls(parent_path=str(parent_path),
                   name=f"_frag_{frag_id}",
                   node_type=NodeType.LEAF,
                   content=content,
                   payload=real_payload,
                   status=NodeStatus.PENDING_REVIEW,
                   name_editable=False)

    def to_dict(self) -> dict:
        """
        Serialize the node to a dictionary for API responses.

        Returns:
            Dict representation suitable for JSON serialization.
        """
        return {
            "id": self.id,
            "path": self.path,
            "node_type": self.node_type.value,
            "status": self.status.value,
            "name": self.display_name or self.name,
            "name_editable": self.name_editable,
            "content": self.content,
            "payload": self.payload,
            "tags": self.tags,
            "is_dirty": self.is_dirty,
            "version": self.version,
            "access_count": self.access_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

    def start_processing(self) -> None:
        """
        Transition to PROCESSING state, saving original status.

        Called at the start of maintenance to lock the node.
        Original status is preserved for rollback on failure.
        """
        if self.status in (NodeStatus.ARCHIVED, NodeStatus.PROCESSING):
            return
        self._original_status = self.status
        self.status = NodeStatus.PROCESSING
        self.bump_version()

    def finish_processing(self) -> None:
        """
        Transition from PROCESSING to ACTIVE on success.

        Called when maintenance completes successfully.
        """
        if self.status != NodeStatus.PROCESSING:
            return
        self.status = NodeStatus.ACTIVE
        self._original_status = None
        self.bump_version()

    def fail_processing(self) -> None:
        """
        Rollback from PROCESSING to original status on failure.

        Called when maintenance fails to restore the node to
        its pre-processing state.

        If _original_status is None (corrupted state), defaults to
        PENDING_REVIEW for fragments or ACTIVE for other nodes.
        """
        if self.status != NodeStatus.PROCESSING:
            return

        if self._original_status:
            # Normal case: restore to saved original status
            self.status = self._original_status
            self._original_status = None
        else:
            # Fallback case: _original_status is None (shouldn't happen, but handle gracefully)
            # Use PENDING_REVIEW for safety - will be reprocessed on next maintain
            self.status = NodeStatus.PENDING_REVIEW
            logger.warning(
                "Node %s had PROCESSING status but no _original_status, "
                "defaulting to PENDING_REVIEW for safety",
                self.path
            )

        self.bump_version()

    def archive(self) -> None:
        """
        Soft-delete this leaf by setting status to ARCHIVED.

        Called by MERGE and GROUP operations when the original
        leaf is superseded by a new node.

        Raises:
            NodeTypeMismatchError: If called on a CATEGORY node.
        """
        self._assert_leaf()
        if self.status == NodeStatus.ARCHIVED:
            return
        self.status = NodeStatus.ARCHIVED
        self._original_status = None
        self.bump_version()

    def clear_dirty(self) -> None:
        """
        Clear the dirty flag after maintenance completes.

        Only valid for CATEGORY nodes.

        Raises:
            NodeTypeMismatchError: If called on a LEAF node.
        """
        self._assert_category()
        self.is_dirty = False
        self.bump_version()

    def _assert_category(self) -> None:
        """Raise if this node is not a CATEGORY."""
        if self.node_type != NodeType.CATEGORY:
            raise NodeTypeMismatchError(self.path, "CATEGORY",
                                        self.node_type.value)

    def _assert_leaf(self) -> None:
        """Raise if this node is not a LEAF."""
        if self.node_type != NodeType.LEAF:
            raise NodeTypeMismatchError(self.path, "LEAF",
                                        self.node_type.value)

    def __repr__(self) -> str:
        """Return a debug representation."""
        return f"<TreeNode {self.node_type.value} path={self.path!r} status={self.status.value} id={self.id[:8]}>"
