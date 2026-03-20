# Reading & Querying

Retrieve and navigate memory with the latest read APIs.

## Read Surface

| Method | Returns | Purpose |
|---|---|---|
| `read(path)` | `NodeView \| None` | Single node + navigation context |
| `list(path)` | `list[NodeView]` | Direct children |
| `tree(path, max_depth)` | `TreeView \| None` | Recursive tree view |
| `related(path)` | `RelatedNodes \| None` | Parent/siblings/children/ancestors |
| `stats()` | `StatsView` | Global statistics |

## `read(path)`

```python
view = await semafs.read("root.preferences")
if view:
    print(view.path)
    print(view.breadcrumb)
    print(view.child_count)
```

## `list(path)`

```python
children = await semafs.list("root")
for child in children:
    print(child.path, child.summary)
```

## `tree(path, max_depth)`

```python
tree = await semafs.tree("root", max_depth=3)
if tree:
    print(tree.total_nodes)
    print(tree.leaf_count)
```

## `related(path)`

```python
rel = await semafs.related("root.preferences")
if rel:
    print("current:", rel.current.path)
    print("siblings:", [n.path for n in rel.siblings])
    print("children:", [n.path for n in rel.children])
```

## `stats()`

```python
stats = await semafs.stats()
print(stats.total_nodes)
print(stats.total_categories)
print(stats.total_leaves)
print(stats.max_depth)
print(stats.dirty_categories)
print(stats.top_categories)
```

## Rendering

```python
from semafs.renderer import TextRenderer, JSONRenderer

view = await semafs.read("root")
if view:
    print(TextRenderer.render_node(view))

tr = await semafs.tree("root", max_depth=2)
if tr:
    print(JSONRenderer.render_tree(tr))
```

## Current vs Old API

Use now:

- `tree(...)`
- `related(...)`

Do not use old names:

- `view_tree(...)`
- `get_related(...)`

## Next Steps

- [Writing Memories](./writing) - Append new fragments
- [Maintenance](./maintenance) - Keep structure healthy
- [API Reference](/api/semafs) - Full method signatures
