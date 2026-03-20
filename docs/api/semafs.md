# SemaFS API

`SemaFS` 是对外主入口，负责写入、维护、读取与骨架初始化。

## Constructor

```python
SemaFS(
    store: NodeStore,
    uow_factory: UoWFactory,
    bus: Bus,
    strategy: Strategy,
    placer: Placer,
    summarizer: Summarizer,
    policy: Policy,
    budget: Budget = Budget(),
    terminal_config: TerminalConfig = TerminalConfig(),
)
```

## Write & Maintenance

### `write()`

```python
async def write(
    content: str,
    hint: str | None = None,
    payload: dict | None = None,
) -> str
```

- 写入新片段并返回叶子节点 `id`。
- `hint` 是写入入口路径，最终落点由 `placer` 决定。

### `sweep()`

```python
async def sweep(limit: int | None = None) -> int
```

- 扫描并处理超载分类，返回本轮处理分类数。

### `apply_skeleton()`

```python
async def apply_skeleton(
    skeleton: dict | list[str] | tuple[str, ...] | str,
    *,
    source: str = "manual",
) -> int
```

- 批量创建/标记骨架分类。
- 骨架分类会被设置为 `skeleton=True` 且 `name_editable=False`。
- 返回新增/更新的节点数。

## Read APIs

### `read(path)`

```python
async def read(path: str) -> NodeView | None
```

### `list(path)`

```python
async def list(path: str) -> list[NodeView]
```

### `tree(path="root", max_depth=3)`

```python
async def tree(path: str = "root", max_depth: int = 3) -> TreeView | None
```

### `related(path)`

```python
async def related(path: str) -> RelatedNodes | None
```

### `stats()`

```python
async def stats() -> StatsView
```

返回统计项包括：

- `total_categories`
- `total_leaves`
- `max_depth`
- `dirty_categories`
- `top_categories`

## Notes

- 当前主维护入口是 `sweep()`（没有 `maintain()`）。
- 当前树读取入口是 `tree()`（没有 `view_tree()`）。
- 当前邻接读取入口是 `related()`（没有 `get_related()`）。
