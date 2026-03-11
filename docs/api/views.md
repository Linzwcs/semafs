# Views API

Structured read results with navigation context.

## NodeView

Single node with navigation context.

```python
@dataclass(frozen=True)
class NodeView:
    node: TreeNode              # The actual node
    breadcrumb: Tuple[str, ...]  # Path segments
    child_count: int            # Number of children
    sibling_count: int          # Number of siblings

    @property
    def path(self) -> str:
        """Node's full path."""
        return self.node.path

    @property
    def content(self) -> str:
        """Node's content."""
        return self.node.content

    @property
    def is_category(self) -> bool:
        """True if CATEGORY node."""
        return self.node.node_type == NodeType.CATEGORY

    @property
    def summary(self) -> str:
        """First 100 characters of content."""
        return self.content[:100] + "..." if len(self.content) > 100 else self.content
```

### Usage

```python
node = await semafs.read("root.work.meetings")

print(node.path)          # "root.work.meetings"
print(node.breadcrumb)    # ("root", "work", "meetings")
print(node.child_count)   # 5
print(node.sibling_count) # 3
print(node.is_category)   # True
print(node.summary)       # "Meeting notes and..."
```

## TreeView

Recursive tree structure.

```python
@dataclass(frozen=True)
class TreeView:
    node: TreeNode                  # Current node
    children: Tuple["TreeView", ...]  # Child trees
    depth: int                      # Current depth in tree

    @property
    def path(self) -> str:
        """Node's full path."""
        return self.node.path

    @property
    def total_nodes(self) -> int:
        """Total nodes in subtree (including self)."""
        return 1 + sum(c.total_nodes for c in self.children)

    @property
    def leaf_count(self) -> int:
        """Number of LEAF nodes in subtree."""
        if self.node.node_type == NodeType.LEAF:
            return 1
        return sum(c.leaf_count for c in self.children)
```

### Usage

```python
tree = await semafs.view_tree("root", max_depth=3)

print(tree.path)          # "root"
print(tree.depth)         # 0
print(len(tree.children)) # 5
print(tree.total_nodes)   # 42
print(tree.leaf_count)    # 28

# Traverse
for child in tree.children:
    print(f"{child.path}: {child.total_nodes} nodes")
```

### Recursive Traversal

```python
def print_tree(tree: TreeView, indent: int = 0):
    prefix = "  " * indent
    icon = "📁" if tree.node.node_type == NodeType.CATEGORY else "📄"
    print(f"{prefix}{icon} {tree.node.name}: {tree.node.content[:50]}...")

    for child in tree.children:
        print_tree(child, indent + 1)

tree = await semafs.view_tree("root", max_depth=3)
print_tree(tree)
```

## RelatedNodes

Navigation map around a node.

```python
@dataclass(frozen=True)
class RelatedNodes:
    current: TreeNode                  # The queried node
    parent: Optional[TreeNode]         # Parent node (None for root)
    siblings: Tuple[TreeNode, ...]     # Sibling nodes
    children: Tuple[TreeNode, ...]     # Child nodes
    ancestors: Tuple[TreeNode, ...]    # Path from root

    @property
    def navigation_summary(self) -> str:
        """Formatted navigation info."""
        parts = []
        if self.parent:
            parts.append(f"Parent: {self.parent.path}")
        parts.append(f"Siblings: {len(self.siblings)}")
        parts.append(f"Children: {len(self.children)}")
        return " | ".join(parts)
```

### Usage

```python
related = await semafs.get_related("root.work.meetings")

# Navigation
if related.parent:
    print(f"Go up: {related.parent.path}")

print("Siblings:")
for s in related.siblings:
    print(f"  - {s.path}")

print("Children:")
for c in related.children:
    print(f"  - {c.path}")

print("Breadcrumb:")
for a in related.ancestors:
    print(f"  {a.path}")
```

## StatsView

Knowledge base statistics.

```python
@dataclass(frozen=True)
class StatsView:
    total_categories: int
    total_leaves: int
    max_depth: int
    dirty_categories: int
    top_categories: List[Tuple[str, int]]  # (path, child_count)

    @property
    def total_nodes(self) -> int:
        """Total nodes (categories + leaves)."""
        return self.total_categories + self.total_leaves

    @property
    def summary(self) -> str:
        """Formatted summary string."""
        return (
            f"Nodes: {self.total_nodes} "
            f"({self.total_categories} categories, {self.total_leaves} leaves) | "
            f"Max depth: {self.max_depth} | "
            f"Pending: {self.dirty_categories}"
        )
```

### Usage

```python
stats = await semafs.stats()

print(f"Total nodes: {stats.total_nodes}")
print(f"Categories: {stats.total_categories}")
print(f"Leaves: {stats.total_leaves}")
print(f"Max depth: {stats.max_depth}")
print(f"Pending maintenance: {stats.dirty_categories}")

print("\nTop categories by size:")
for path, count in stats.top_categories:
    print(f"  {path}: {count} children")

print(f"\n{stats.summary}")
```

## Renderers

Convert views to different formats.

### TextRenderer

Terminal-friendly output.

```python
from semafs.renderer import TextRenderer

# Render tree
tree = await semafs.view_tree("root", max_depth=2)
output = TextRenderer.render_tree(tree)
print(output)
# root
# ├── work
# │   ├── meetings
# │   └── projects
# └── personal
#     └── notes

# Render node
node = await semafs.read("root.work")
output = TextRenderer.render_node(node)
print(output)
```

### MarkdownRenderer

Document export format.

```python
from semafs.renderer import MarkdownRenderer

tree = await semafs.view_tree("root", max_depth=5)
markdown = MarkdownRenderer.render_tree(tree)

with open("knowledge.md", "w") as f:
    f.write(markdown)
```

### LLMRenderer

Token-optimized format for LLM context.

```python
from semafs.renderer import LLMRenderer

tree = await semafs.view_tree("root", max_depth=2)
context = LLMRenderer.render_tree(tree)
# Minimal format, good for LLM prompts
```

### JSONRenderer

Structured data for APIs.

```python
from semafs.renderer import JSONRenderer
import json

tree = await semafs.view_tree("root", max_depth=2)
data = JSONRenderer.render_tree(tree)
json_str = json.dumps(data, indent=2)
```

## See Also

- [SemaFS](/api/semafs) - Main facade API
- [TreeNode](/api/node) - Node class
- [Reading Guide](/guide/reading) - Usage patterns
