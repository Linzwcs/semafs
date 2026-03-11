# SemaFS API

The main facade for interacting with the semantic filesystem.

## Class Definition

```python
class SemaFS:
    def __init__(
        self,
        uow_factory: UoWFactory,
        strategy: Strategy,
        executor: Optional[Executor] = None,
        max_children: int = 10,
        db_name: str = "default"
    ):
        """
        Initialize SemaFS instance.

        Args:
            uow_factory: Factory for creating transactions
            strategy: Strategy for reorganization decisions
            executor: Plan executor (default: creates new Executor)
            max_children: Threshold for triggering maintenance
            db_name: Identifier for logging
        """
```

## Write Operations

### write()

Write a knowledge fragment to the filesystem.

```python
async def write(
    self,
    path: str,
    content: str,
    payload: Optional[Dict[str, Any]] = None
) -> str:
    """
    Write a fragment to the specified path.

    Args:
        path: Target category path (e.g., "root.work.meetings")
        content: Knowledge content to store
        payload: Optional metadata dictionary

    Returns:
        Fragment ID (UUID string)

    Raises:
        InvalidPathError: If path format is invalid

    Example:
        >>> frag_id = await semafs.write(
        ...     "root.work",
        ...     "Completed sprint planning",
        ...     {"source": "meeting"}
        ... )
    """
```

**Path Resolution**: Finds the deepest existing CATEGORY in the path.

**Fragment Creation**: Creates a PENDING_REVIEW node named `_frag_{random}`.

**Side Effect**: Marks parent category as dirty.

## Read Operations

### read()

Read a single node with navigation context.

```python
async def read(self, path: str) -> Optional[NodeView]:
    """
    Read a node by path.

    Args:
        path: Full path to the node

    Returns:
        NodeView with context, or None if not found

    Example:
        >>> node = await semafs.read("root.work")
        >>> print(node.content)
        >>> print(node.child_count)
    """
```

### list()

List direct children of a category.

```python
async def list(
    self,
    path: str,
    include_archived: bool = False
) -> List[NodeView]:
    """
    List children of a category.

    Args:
        path: Parent category path
        include_archived: Include ARCHIVED nodes

    Returns:
        List of NodeView objects, sorted by path

    Example:
        >>> children = await semafs.list("root.work")
        >>> for child in children:
        ...     print(child.path)
    """
```

### view_tree()

Get recursive tree structure.

```python
async def view_tree(
    self,
    path: str,
    max_depth: int = 10
) -> Optional[TreeView]:
    """
    Get tree view starting from path.

    Args:
        path: Root path for the tree
        max_depth: Maximum recursion depth

    Returns:
        TreeView with recursive children, or None if not found

    Example:
        >>> tree = await semafs.view_tree("root", max_depth=3)
        >>> print(tree.total_nodes)
        >>> print(tree.leaf_count)
    """
```

### get_related()

Get navigation context around a node.

```python
async def get_related(self, path: str) -> Optional[RelatedNodes]:
    """
    Get related nodes for navigation.

    Args:
        path: Target node path

    Returns:
        RelatedNodes with parent, siblings, children, ancestors

    Example:
        >>> related = await semafs.get_related("root.work")
        >>> print(related.parent.path)
        >>> print([s.path for s in related.siblings])
    """
```

### stats()

Get knowledge base statistics.

```python
async def stats(self) -> StatsView:
    """
    Get overall statistics.

    Returns:
        StatsView with counts and metrics

    Example:
        >>> stats = await semafs.stats()
        >>> print(f"Total nodes: {stats.total_nodes}")
        >>> print(f"Pending maintenance: {stats.dirty_categories}")
    """
```

## Maintenance Operations

### maintain()

Process all dirty categories.

```python
async def maintain(self) -> int:
    """
    Run maintenance on all dirty categories.

    Returns:
        Number of categories processed

    Processing Order:
        Deepest categories first (leaf-to-root)

    Example:
        >>> processed = await semafs.maintain()
        >>> print(f"Organized {processed} categories")
    """
```

**Strategy Invocation**: Calls `strategy.create_plan()` for each dirty category.

**Atomic Execution**: Each category is processed in its own transaction.

**Error Handling**: Failed categories are logged but don't stop processing.

## Complete Example

```python
import asyncio
from semafs import SemaFS
from semafs.storage.sqlite import SQLiteUoWFactory
from semafs.strategies.hybrid import HybridStrategy
from semafs.infra.llm.openai import OpenAIAdapter
from openai import AsyncOpenAI

async def main():
    # Setup
    factory = SQLiteUoWFactory("knowledge.db")
    await factory.init()

    client = AsyncOpenAI()
    adapter = OpenAIAdapter(client, model="gpt-4o-mini")
    strategy = HybridStrategy(adapter, max_nodes=8)

    semafs = SemaFS(factory, strategy, max_children=10)

    # Write
    await semafs.write("root.work", "Sprint planning completed")
    await semafs.write("root.work", "API documentation updated")

    # Maintain
    processed = await semafs.maintain()
    print(f"Processed: {processed}")

    # Read
    tree = await semafs.view_tree("root", max_depth=3)
    stats = await semafs.stats()

    print(f"Total nodes: {stats.total_nodes}")
    print(f"Categories: {stats.total_categories}")
    print(f"Leaves: {stats.total_leaves}")

    # Cleanup
    await factory.close()

asyncio.run(main())
```

## See Also

- [TreeNode](/api/node) - Node class reference
- [Views](/api/views) - View objects reference
- [Strategy](/api/strategy) - Strategy protocol
