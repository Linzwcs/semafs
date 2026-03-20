# Node API

`Node` 是 SemaFS 的核心领域实体，表示树中的分类或叶子节点。

## Node Dataclass

```python
@dataclass(frozen=True)
class Node:
    id: str
    parent_id: str | None
    name: str
    canonical_path: str
    node_type: NodeType
    content: str | None
    summary: str | None
    category_meta: dict
    payload: dict
    tags: tuple[str, ...]
    stage: NodeStage
    skeleton: bool
    name_editable: bool
```

## Enumerations

### `NodeType`

```python
class NodeType(Enum):
    CATEGORY = "category"
    LEAF = "leaf"
```

### `NodeStage`

```python
class NodeStage(Enum):
    ACTIVE = "active"
    PENDING = "pending"
    COLD = "cold"
    ARCHIVED = "archived"
```

## NodePath

```python
@dataclass(frozen=True)
class NodePath:
    value: str
```

关键属性：

- `parent`
- `parent_str`
- `name`
- `depth`
- `child(name)`

## Factory Methods

### `Node.create_root()`

创建根分类节点（`root`）。

### `Node.create_category(...)`

创建分类节点。

### `Node.create_leaf(...)`

创建叶子节点。

## Immutable Update Methods

`Node` 是 frozen dataclass，更新通过返回新副本：

- `with_summary(summary)`
- `with_category_meta(meta)`
- `with_name(name)`
- `with_name_editable(editable)`
- `with_skeleton(skeleton)`
- `with_parent(parent_id, parent_path)`
- `with_path_projection(canonical_path)`
- `with_stage(stage)`
- `with_payload(payload)`

## Validation Rules

- 路径必须符合 `root(.segment)*`
- 名称字符受限并会标准化
- `LEAF` 必须有 `content`
- `CATEGORY` 必须有 `summary`
- `LEAF` 不允许 `category_meta`
- `skeleton` 节点必须 `name_editable=False`

## See Also

- [Views](/api/views)
- [Operations](/api/operations)
- [Data Model](/design/data-model)
