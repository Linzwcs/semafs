# Operations API

Tree reorganization operations and plans.

## Operation Types

### MergeOp

Combine multiple leaves into one.

```python
@dataclass(frozen=True)
class MergeOp:
    ids: FrozenSet[str]    # Node IDs to merge (≥2)
    content: str           # Synthesized content
    reasoning: str         # Explanation

    op_type: OpType = OpType.MERGE

    def __post_init__(self):
        if len(self.ids) < 2:
            raise ValueError("MergeOp requires at least 2 nodes")
```

**Behavior**:
- Archives all source nodes
- Creates new LEAF with merged content
- Preserves metadata from sources

### GroupOp

Create category and move leaves into it.

```python
@dataclass(frozen=True)
class GroupOp:
    ids: FrozenSet[str]    # Node IDs to group (≥2)
    name: str              # New category name (dots = hierarchy)
    content: str           # Category summary
    reasoning: str

    op_type: OpType = OpType.GROUP

    def __post_init__(self):
        if len(self.ids) < 2:
            raise ValueError("GroupOp requires at least 2 nodes")
        if not self.name:
            raise ValueError("GroupOp requires a name")
```

**Behavior**:
- Creates category (and parents if dotted name)
- Archives source nodes
- Creates copies under new category

### MoveOp

Relocate leaf to existing category.

```python
@dataclass(frozen=True)
class MoveOp:
    id: str               # Single node ID
    target_path: str      # Must be existing CATEGORY
    reasoning: str

    op_type: OpType = OpType.MOVE
```

**Behavior**:
- Archives source node
- Creates copy at target location
- Target must exist (no path fabrication)

### PersistOp

Convert fragment to active leaf.

```python
@dataclass(frozen=True)
class PersistOp:
    id: str               # Fragment ID
    reasoning: str

    op_type: OpType = OpType.PERSIST
```

**Behavior**:
- Archives original fragment
- Creates ACTIVE leaf with same content

## RebalancePlan

Container for operations with metadata.

```python
@dataclass(frozen=True)
class RebalancePlan:
    ops: Tuple[Op, ...]              # Ordered operations
    updated_content: str             # New parent summary
    updated_name: Optional[str]      # Optional new parent name
    overall_reasoning: str           # Strategy explanation
    should_dirty_parent: bool        # Trigger semantic floating?
    is_llm_plan: bool               # LLM or rule-based?

    @property
    def is_empty(self) -> bool:
        """True if no structural changes."""
        return len(self.ops) == 0

    @property
    def ops_summary(self) -> str:
        """Human-readable summary like 'MERGE×2 | GROUP×1'."""
```

### Creating Plans

```python
from semafs.core.ops import RebalancePlan, MergeOp, GroupOp

plan = RebalancePlan(
    ops=(
        MergeOp(
            ids=frozenset({"abc", "def"}),
            content="Merged content",
            reasoning="Similar topics"
        ),
        GroupOp(
            ids=frozenset({"ghi", "jkl"}),
            name="tech.frontend",
            content="Frontend notes",
            reasoning="All frontend related"
        ),
    ),
    updated_content="Updated category summary",
    updated_name=None,
    overall_reasoning="Reorganized for clarity",
    should_dirty_parent=True,
    is_llm_plan=True
)

print(plan.ops_summary)  # "MERGE×1 | GROUP×1"
print(plan.is_empty)     # False
```

## UpdateContext

Snapshot of category state for strategy decisions.

```python
@dataclass(frozen=True)
class UpdateContext:
    parent: TreeNode              # Category being maintained
    active_nodes: Tuple[TreeNode] # ACTIVE children
    pending_nodes: Tuple[TreeNode] # PENDING_REVIEW fragments
    sibling_categories: Tuple[TreeNode]  # Sibling CATEGORYs
    ancestor_categories: Tuple[TreeNode] # Ancestor chain

    @property
    def inbox(self) -> Tuple[TreeNode]:
        """Alias for pending_nodes."""
        return self.pending_nodes

    @property
    def children(self) -> Tuple[TreeNode]:
        """Alias for active_nodes."""
        return self.active_nodes

    @property
    def all_nodes(self) -> Tuple[TreeNode]:
        """All children (active + pending)."""
        return self.active_nodes + self.pending_nodes

    @property
    def sibling_category_names(self) -> List[str]:
        """Names of sibling categories."""
        return [n.name for n in self.sibling_categories]

    @property
    def ancestor_path_chain(self) -> List[str]:
        """Paths from root to parent."""
        return [n.path for n in self.ancestor_categories]
```

### Context Usage

```python
# In Strategy.create_plan():
def create_plan(context: UpdateContext, max_children: int):
    # Check if maintenance needed
    if not context.pending_nodes and len(context.active_nodes) < max_children:
        return None

    # Analyze context
    total = len(context.all_nodes)
    siblings = context.sibling_category_names  # For naming conflicts

    # Create plan...
```

## OpType Enumeration

```python
class OpType(str, Enum):
    MERGE = "MERGE"
    GROUP = "GROUP"
    MOVE = "MOVE"
    PERSIST = "PERSIST"
```

## Example: Custom Plan Creation

```python
from semafs.core.ops import (
    RebalancePlan, MergeOp, GroupOp, MoveOp, PersistOp, UpdateContext
)

def create_custom_plan(context: UpdateContext) -> RebalancePlan:
    ops = []

    # Persist simple fragments
    for node in context.pending_nodes:
        if len(node.content) < 100:  # Short content
            ops.append(PersistOp(
                id=node.id,
                reasoning="Short fragment, persist as-is"
            ))

    # Group remaining by keyword
    tech_ids = frozenset(
        n.id for n in context.pending_nodes
        if "code" in n.content.lower()
    )
    if len(tech_ids) >= 2:
        ops.append(GroupOp(
            ids=tech_ids,
            name="tech",
            content="Technical notes",
            reasoning="Contains code-related content"
        ))

    return RebalancePlan(
        ops=tuple(ops),
        updated_content=context.parent.content,
        overall_reasoning="Custom organization logic",
        should_dirty_parent=False,
        is_llm_plan=False
    )
```

## See Also

- [TreeNode](/api/node) - Node class reference
- [Strategy](/api/strategy) - Strategy protocol
- [Tree Operations Guide](/guide/operations) - Detailed operation guide
