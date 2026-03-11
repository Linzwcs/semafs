# Reading & Querying

Retrieve and navigate your knowledge tree.

## Overview

SemaFS provides four read operations:

| Method | Returns | Use Case |
|--------|---------|----------|
| `read(path)` | `NodeView` | Single node with context |
| `list(path)` | `List[NodeView]` | Direct children |
| `view_tree(path, depth)` | `TreeView` | Recursive tree |
| `get_related(path)` | `RelatedNodes` | Navigation map |

## read() — Single Node

Get a single node with navigation context:

```python
node = await semafs.read("root.preferences.food")

if node:
    print(node.path)          # "root.preferences.food"
    print(node.content)       # "Food preferences summary..."
    print(node.breadcrumb)    # ("root", "preferences", "food")
    print(node.child_count)   # 3
    print(node.sibling_count) # 2
    print(node.is_category)   # True
```

### NodeView Properties

```python
class NodeView:
    node: TreeNode          # The actual node
    breadcrumb: Tuple[str]  # Path segments
    child_count: int        # Number of children
    sibling_count: int      # Number of siblings

    # Convenience properties
    @property
    def path(self) -> str: ...
    @property
    def content(self) -> str: ...
    @property
    def is_category(self) -> bool: ...
    @property
    def summary(self) -> str: ...  # First 100 chars
```

## list() — Direct Children

Get immediate children of a category:

```python
children = await semafs.list("root.preferences")

for child in children:
    print(f"{child.path}: {child.summary}")

# Output:
# root.preferences.food: Food preferences including coffee...
# root.preferences.work: Work habits and meeting styles...
# root.preferences.travel: Travel preferences...
```

### Options

```python
# Include archived nodes (for audit)
children = await semafs.list("root.work", include_archived=True)
```

## view_tree() — Recursive Tree

Get a tree structure with depth control:

```python
tree = await semafs.view_tree("root", max_depth=3)

print(tree.total_nodes)   # 42
print(tree.leaf_count)    # 28
print(len(tree.children)) # 5
```

### TreeView Structure

```python
class TreeView:
    node: TreeNode                # Current node
    children: Tuple[TreeView]     # Child trees (recursive)
    depth: int                    # Current depth

    @property
    def total_nodes(self) -> int: ...  # All descendants
    @property
    def leaf_count(self) -> int: ...   # LEAF descendants
```

### Traversing the Tree

```python
def print_tree(tree: TreeView, indent: int = 0):
    prefix = "  " * indent
    icon = "📁" if tree.node.node_type == NodeType.CATEGORY else "📄"
    print(f"{prefix}{icon} {tree.node.name}")

    for child in tree.children:
        print_tree(child, indent + 1)

tree = await semafs.view_tree("root", max_depth=3)
print_tree(tree)
```

Output:
```
📁 root
  📁 preferences
    📁 food
      📄 coffee
      📄 cuisine
    📁 work
      📄 meetings
  📁 projects
    📄 semafs
```

## get_related() — Navigation Map

Get surrounding nodes for navigation:

```python
related = await semafs.get_related("root.preferences.food")

print(related.parent.path)     # "root.preferences"
print([s.path for s in related.siblings])   # ["root.preferences.work", ...]
print([c.path for c in related.children])   # ["root.preferences.food.coffee", ...]
print([a.path for a in related.ancestors])  # ["root", "root.preferences"]
```

### RelatedNodes Structure

```python
class RelatedNodes:
    current: TreeNode              # The queried node
    parent: Optional[TreeNode]     # Parent node
    siblings: Tuple[TreeNode]      # Sibling nodes
    children: Tuple[TreeNode]      # Child nodes
    ancestors: Tuple[TreeNode]     # Path from root

    @property
    def navigation_summary(self) -> str: ...
```

## stats() — Knowledge Base Statistics

Get an overview of your knowledge base:

```python
stats = await semafs.stats()

print(stats.total_categories)  # 10
print(stats.total_leaves)      # 32
print(stats.total_nodes)       # 42
print(stats.max_depth)         # 4
print(stats.dirty_categories)  # 2
print(stats.top_categories)    # [("root.work", 15), ("root.food", 8), ...]
```

## Rendering Views

SemaFS includes renderers for different output formats:

### Text Renderer

```python
from semafs.renderer import TextRenderer

tree = await semafs.view_tree("root", max_depth=2)
output = TextRenderer.render_tree(tree)
print(output)
```

Output:
```
root
├── preferences
│   ├── food
│   └── work
└── projects
    └── semafs
```

### LLM Renderer

Optimized for LLM context (minimal tokens):

```python
from semafs.renderer import LLMRenderer

tree = await semafs.view_tree("root", max_depth=2)
context = LLMRenderer.render_tree(tree)
# Use in LLM prompt
```

### Markdown Renderer

For documentation export:

```python
from semafs.renderer import MarkdownRenderer

tree = await semafs.view_tree("root", max_depth=3)
markdown = MarkdownRenderer.render_tree(tree)

with open("knowledge.md", "w") as f:
    f.write(markdown)
```

## Query Patterns

### Find by Path Pattern

```python
# Get all food-related nodes
food_tree = await semafs.view_tree("root.food", max_depth=10)

def find_leaves(tree: TreeView) -> List[TreeNode]:
    leaves = []
    if tree.node.node_type == NodeType.LEAF:
        leaves.append(tree.node)
    for child in tree.children:
        leaves.extend(find_leaves(child))
    return leaves

all_food_leaves = find_leaves(food_tree)
```

### Search by Content

```python
# Simple content search
async def search(semafs, root_path: str, query: str) -> List[TreeNode]:
    tree = await semafs.view_tree(root_path, max_depth=10)
    results = []

    def search_tree(t: TreeView):
        if query.lower() in t.node.content.lower():
            results.append(t.node)
        for child in t.children:
            search_tree(child)

    search_tree(tree)
    return results

matches = await search(semafs, "root", "coffee")
```

### Navigate to Parent

```python
node = await semafs.read("root.preferences.food.coffee")
if node and len(node.breadcrumb) > 1:
    parent_path = ".".join(node.breadcrumb[:-1])
    parent = await semafs.read(parent_path)
```

## Performance Tips

### 1. Limit Tree Depth

```python
# Good: Limit depth for large trees
tree = await semafs.view_tree("root", max_depth=2)

# Avoid: Unlimited depth on large trees
tree = await semafs.view_tree("root", max_depth=100)
```

### 2. Use list() for Direct Children

```python
# Efficient: Only get immediate children
children = await semafs.list("root.work")

# Less efficient: Full tree just for children
tree = await semafs.view_tree("root.work", max_depth=1)
```

### 3. Parallel Reads

```python
import asyncio

paths = ["root.work", "root.food", "root.travel"]
nodes = await asyncio.gather(*[semafs.read(p) for p in paths])
```

## Next Steps

- [Maintenance](./maintenance) - How auto-organization works
- [Tree Operations](./operations) - Understanding merge/group/move
- [API Reference](/api/semafs) - Complete API documentation
