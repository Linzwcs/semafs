# Transaction Model

SemaFS 的事务模型基于 Unit of Work（UoW），强调“集中 staging + 原子提交”。

## Core Contracts

```python
class UnitOfWork(Protocol):
    reader: TxReader

    def register_new(self, node: Node) -> None: ...
    def register_dirty(self, node: Node) -> None: ...
    def register_removed(self, node_id: str) -> None: ...
    def register_rename(self, node_id: str, new_name: str) -> None: ...
    def register_move(self, node_id: str, new_parent_id: str) -> None: ...

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
```

## Single-Transaction Write

`write()` 的典型语义：

1. `uow_factory.begin()` 打开事务
2. staging：新叶子 + 相关父节点更新
3. `commit()` 一次提交
4. 提交后发布事件

这保证写入路径可预测、失败可回滚。

## Commit Internals (SQLite UoW)

当前实现会在一次 `commit()` 内完成：

1. 插入 `register_new`
2. 更新 `register_dirty`
3. 应用 `register_rename`
4. 应用 `register_move`
5. 应用 `register_removed`（归档）
6. 重算 `canonical_path`
7. 刷新 `node_paths` 投影

若任一步骤异常：整体 rollback。

## Transaction-aware Reads

`TxReader` 绑定到当前事务连接，供维护流程读取：

- `get_by_id/get_by_path`
- `resolve_path/canonical_path`
- `list_children/list_siblings/get_ancestors`
- `all_paths`

意义：决策快照与落库提交共享同一事务视图。

## Isolation Strategy

并发控制采用两层：

1. 应用层：`Keeper` 对同一 node reconcile 加锁
2. 存储层：SQLite `BEGIN IMMEDIATE` 序列化写事务

这样可以减少并发写冲突与部分提交状态。

## Failure & Recovery

- UoW context manager 在异常时触发 rollback
- 事务内失败不会泄露半成状态
- 事件发布位于事务提交之后，避免“事件成功但数据未落库”

## Why It Matters

对语义记忆系统来说，错误的“部分成功”比“显式失败”更危险。

SemaFS 通过 UoW 模型保证：

- 要么结构更新全部生效
- 要么系统保持原状并等待下一轮重试
