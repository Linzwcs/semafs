# TreeNode API

The core domain entity representing a node in the knowledge tree.

## Class Definition

```python
@dataclass
class TreeNode:
    id: str                    # UUID
    parent_path: str           # Parent's full path
    name: str                  # Node name (last path segment)
    node_type: NodeType        # CATEGORY or LEAF
    content: str               # Summary or full content
    status: NodeStatus         # ACTIVE, PENDING_REVIEW, etc.
    payload: Dict[str, Any]    # Arbitrary metadata
    tags: List[str]            # Classification tags
    is_dirty: bool             # Needs maintenance?
    version: int               # Optimistic locking
    created_at: datetime
    updated_at: datetime
```

## Factory Methods

### new_category()

Create a new CATEGORY node.

```python
@classmethod
def new_category(
    cls,
    parent_path: str,
    name: str,
    content: str = "",
    display_name: Optional[str] = None,
    payload: Optional[Dict] = None
) -> "TreeNode":
    """
    Create a category node.

    Args:
        parent_path: Parent's full path (empty for root children)
        name: Category name
        content: Summary content
        display_name: Optional UI display name
        payload: Optional metadata

    Example:
        >>> category = TreeNode.new_category(
        ...     parent_path="root",
        ...     name="work",
        ...     content="Work-related knowledge"
        ... )
    """
```

### new_leaf()

Create a new LEAF node.

```python
@classmethod
def new_leaf(
    cls,
    parent_path: str,
    name: str,
    content: str,
    display_name: Optional[str] = None,
    payload: Optional[Dict] = None
) -> "TreeNode":
    """
    Create a leaf node.

    Args:
        parent_path: Parent's full path
        name: Leaf name
        content: Full knowledge content
        display_name: Optional UI display name
        payload: Optional metadata

    Example:
        >>> leaf = TreeNode.new_leaf(
        ...     parent_path="root.work",
        ...     name="meeting_notes",
        ...     content="Sprint planning completed..."
        ... )
    """
```

### new_fragment()

Create a PENDING_REVIEW fragment.

```python
@classmethod
def new_fragment(
    cls,
    parent_path: str,
    content: str,
    payload: Optional[Dict] = None
) -> "TreeNode":
    """
    Create a pending fragment.

    Auto-generates name: _frag_{random_hex}
    Status: PENDING_REVIEW

    Args:
        parent_path: Parent category path
        content: Fragment content
        payload: Optional metadata

    Example:
        >>> frag = TreeNode.new_fragment(
        ...     parent_path="root.work",
        ...     content="New insight from meeting"
        ... )
    """
```

## Properties

### path

Full path of the node.

```python
@property
def path(self) -> str:
    """Full dot-separated path."""
    # root.work.meetings
```

### node_path

NodePath value object.

```python
@property
def node_path(self) -> NodePath:
    """NodePath instance for path operations."""
```

## Status Transitions

### start_processing()

Begin maintenance processing.

```python
def start_processing(self) -> None:
    """
    Transition to PROCESSING status.

    Saves original status for rollback.
    Only valid from PENDING_REVIEW or ACTIVE.
    """
```

### finish_processing()

Complete successful processing.

```python
def finish_processing(self) -> None:
    """
    Transition from PROCESSING to ACTIVE.

    Clears saved original status.
    """
```

### fail_processing()

Handle processing failure.

```python
def fail_processing(self) -> None:
    """
    Restore original status on failure.

    PROCESSING → original_status
    """
```

### archive()

Soft-delete the node.

```python
def archive(self) -> None:
    """
    Transition to ARCHIVED status.

    Archived nodes are retained for audit.
    """
```

## Category Operations

### receive_fragment()

Mark category as dirty when fragment added.

```python
def receive_fragment(self) -> None:
    """
    Called when a fragment is written to this category.

    Sets is_dirty = True
    """
```

### apply_plan_result()

Apply reorganization results.

```python
def apply_plan_result(
    self,
    updated_content: str,
    updated_name: Optional[str] = None
) -> Optional[str]:
    """
    Apply maintenance results to category.

    Args:
        updated_content: New summary content
        updated_name: Optional new name

    Returns:
        Old path if renamed, None otherwise
    """
```

### request_semantic_rethink()

Force LLM analysis on next maintenance.

```python
def request_semantic_rethink(self) -> None:
    """
    Force LLM analysis regardless of thresholds.

    Sets internal _force_llm flag.
    Used for semantic floating.
    """
```

## NodePath Value Object

```python
@dataclass(frozen=True)
class NodePath:
    raw: str  # Normalized path string

    @property
    def parent(self) -> "NodePath":
        """Parent path (root returns self)."""

    @property
    def name(self) -> str:
        """Last segment of path."""

    @property
    def depth(self) -> int:
        """Number of segments."""

    def child(self, segment: str) -> "NodePath":
        """Create child path."""

    def sibling(self, segment: str) -> "NodePath":
        """Create sibling path."""

    def is_descendant_of(self, other: "NodePath") -> bool:
        """Check if this is a descendant of other."""

    def is_direct_child_of(self, other: "NodePath") -> bool:
        """Check if this is a direct child of other."""

    @classmethod
    def from_parent_and_name(
        cls,
        parent_path: str,
        name: str
    ) -> "NodePath":
        """Create from parent path and name."""
```

## Enumerations

### NodeType

```python
class NodeType(str, Enum):
    CATEGORY = "CATEGORY"  # Organizational container
    LEAF = "LEAF"          # Terminal knowledge node
```

### NodeStatus

```python
class NodeStatus(str, Enum):
    ACTIVE = "ACTIVE"                  # Stable, queryable
    PENDING_REVIEW = "PENDING_REVIEW"  # Awaiting maintenance
    PROCESSING = "PROCESSING"          # Being reorganized
    ARCHIVED = "ARCHIVED"              # Soft-deleted
```

## Example Usage

```python
from semafs.core.node import TreeNode, NodePath
from semafs.core.enums import NodeType, NodeStatus

# Create nodes
category = TreeNode.new_category("root", "work", "Work knowledge")
leaf = TreeNode.new_leaf("root.work", "notes", "Meeting notes...")
fragment = TreeNode.new_fragment("root.work", "New insight")

# Check properties
print(category.path)       # "root.work"
print(leaf.node_type)      # NodeType.LEAF
print(fragment.status)     # NodeStatus.PENDING_REVIEW

# Path operations
path = NodePath("root.work.meetings")
print(path.parent.raw)     # "root.work"
print(path.name)           # "meetings"
print(path.depth)          # 3

# Status transitions
fragment.start_processing()
# ... processing ...
fragment.finish_processing()
print(fragment.status)     # NodeStatus.ACTIVE
```

## See Also

- [Operations](/api/operations) - Tree operations
- [Views](/api/views) - View objects
- [SemaFS](/api/semafs) - Main facade
