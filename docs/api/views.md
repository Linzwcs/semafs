# Views API

View 层是读接口的结构化返回类型。

## NodeView

```python
@dataclass(frozen=True)
class NodeView:
    node: Node
    breadcrumb: tuple[str, ...]
    child_count: int
    sibling_count: int
```

属性：

- `path`
- `is_category`
- `summary`

## TreeView

```python
@dataclass(frozen=True)
class TreeView:
    node: Node
    children: tuple[TreeView, ...] = ()
    depth: int = 0
```

属性：

- `path`
- `total_nodes`
- `leaf_count`

## RelatedNodes

```python
@dataclass(frozen=True)
class RelatedNodes:
    current: NodeView
    parent: NodeView | None = None
    siblings: tuple[NodeView, ...] = ()
    children: tuple[NodeView, ...] = ()
    ancestors: tuple[NodeView, ...] = ()
```

属性：

- `navigation_summary`

## StatsView

```python
@dataclass(frozen=True)
class StatsView:
    total_categories: int
    total_leaves: int
    max_depth: int
    dirty_categories: int
    top_categories: tuple[tuple[str, int], ...]
```

属性：

- `total_nodes`
- `summary`

## Renderers

- `TextRenderer`
- `LLMRenderer`
- `MarkdownRenderer`
- `JSONRenderer`

示例：

```python
view = await semafs.read("root")
if view:
    print(TextRenderer.render_node(view))

tree = await semafs.tree("root", max_depth=2)
if tree:
    print(LLMRenderer.render_tree(tree))
```

## See Also

- [SemaFS](/api/semafs)
- [Reading Guide](/guide/reading)
