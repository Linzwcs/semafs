from __future__ import annotations
from typing import AsyncIterator, Protocol, runtime_checkable
from core.node import TreeNode
from .repo import NodeRepository


@runtime_checkable
class IUnitOfWork(Protocol):
    """工作单元协议。通常作为异步上下文管理器使用。"""

    # 挂载 Repo：用于在推演过程中查询当前状态
    repo: NodeRepository

    def register_new(self, node: TreeNode):
        """登记一个全新创建的节点，commit 时执行 INSERT。"""
        ...

    def register_dirty(self, node: TreeNode):
        """登记一个被修改过的节点，commit 时执行 UPDATE。"""
        ...

    def register_cascade_rename(self, old_path: str, new_path: str):
        """告诉底层数据库：把所有前缀为 old_path 的子孙节点，替换为 new_path"""
        ...

    async def commit(self) -> None:
        """
        将购物车里的所有变更一次性转化为数据库事务。
        成功后清空购物车。
        """
        ...

    async def rollback(self) -> None:
        """放弃所有内存推演，回滚数据库事务，清空购物车。"""
        ...


@runtime_checkable
class UoWFactory(Protocol):
    """
    工作单元工厂协议。

    这是应用层唯一依赖的后端抽象入口。
    任何后端（SQLite、PostgreSQL、内存）只需实现此协议。

    两个职责，严格分离：
    - repo:  NodeRepository，用于所有只读查询，独立于事务
    - begin: 异步上下文管理器，每次开启一个原子写事务

    用法：
        factory: UoWFactory = SQLiteUoWFactory("semafs.db")
        await factory.init()

        # 只读查询（不开事务）
        node = await factory.repo.get_by_path("root.work")

        # 原子写操作
        async with factory.begin() as uow:
            uow.register_new(new_node)
            uow.register_dirty(dirty_node)
            await uow.commit()   # 或异常时自动 rollback

    换后端只需换工厂实现，SemaFS / PlanExecutor 代码零改动。
    """

    repo: NodeRepository

    async def init(self) -> None:
        """初始化后端（建表、连接池等）。应用启动时调用一次。"""
        ...

    async def close(self) -> None:
        """关闭后端连接。应用退出时调用。"""
        ...

    def begin(self) -> AsyncIterator[IUnitOfWork]:
        """
        开启一个工作单元上下文（异步上下文管理器）。

        正常退出：调用方负责显式 commit()。
        异常退出：自动 rollback，数据库回到原始状态。
        """
        ...
