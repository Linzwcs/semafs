# SemaFS Facade API

`SemaFS` is the main asynchronous facade, defined in `semafs/semafs.py`.

## 1. Constructor

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

Dependency roles:

- storage: `store`, `uow_factory`
- eventing: `bus`
- decision stack: `strategy`, `placer`, `summarizer`, `policy`
- limits/config: `budget`, `terminal_config`

## 2. Methods

### 2.1 `write(content, hint=None, payload=None) -> str`

- stages pending leaf in transaction
- commits transaction
- publishes `Placed` event
- returns leaf id

### 2.2 `read(path) -> NodeView | None`

Returns one node with breadcrumb and local counters.

### 2.3 `list(path) -> list[NodeView]`

Returns direct children views (sorted by path).

### 2.4 `tree(path='root', max_depth=3) -> TreeView | None`

Returns recursive tree snapshot.

### 2.5 `related(path) -> RelatedNodes | None`

Returns parent/sibling/child/ancestor neighborhood.

### 2.6 `stats() -> StatsView`

Returns aggregate topology and maintenance indicators.

### 2.7 `sweep(limit=None) -> int`

Runs overload scan + reconcile; returns processed category count.

### 2.8 `apply_skeleton(skeleton, source='manual') -> int`

Creates/updates skeleton categories and locks names.

Supported inputs:

- string path
- list/tuple of paths
- nested dictionary tree

## 3. Error Surface

Common failure categories:

- invalid path format
- missing target category
- skeleton conflicts with existing leaf path
- provider/runtime errors from adapters
