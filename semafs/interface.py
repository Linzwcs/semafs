from __future__ import annotations
from typing import Protocol, runtime_checkable
from typing import List, Optional
from .models.nodes import TreeNode
from .models.ops import NodeUpdateOp, NodeUpdateContext
from .models.enums import NodeStatus


@runtime_checkable
class TreeRepository(Protocol):

    async def init(self) -> None:
        """初始化连接和表结构（应用启动时调用一次）。"""

    async def close(self) -> None:
        """关闭连接。"""

    # ---------------- 基础读写 (面向外部调用) ----------------
    async def get_node(self, path: str) -> Optional[TreeNode]:
        """获取单个节点（不区分状态）"""

    async def list_children(
        self,
        path: str,
        statuses: Optional[List[NodeStatus]] = None,
    ) -> List[TreeNode]:
        """如果不传 statuses，默认返回 [ACTIVE, PENDING_REVIEW, PROCESSING]"""

    async def add_node(self, node: TreeNode) -> str:
        """
        添加/更新节点。
        【约定】：底层实现需要自动识别副作用。例如新增 PENDING_REVIEW 节点时，自动将父目录标记为 is_dirty=True。
        """

    # ---------------- 内部维护 (面向 Maintainer) ----------------
    async def list_dirty_categories(self) -> List[TreeNode]:
        """获取需要重组的脏目录"""

    async def list_all_categories(self) -> List[TreeNode]:
        """获取所有 category 节点（不含 ARCHIVED），用于子节点数量检查。"""

    async def lock_and_get_context(
        self,
        path: str,
    ) -> Optional[NodeUpdateContext]:
        """
        原子操作：获取锁，并抓取当前目录的上下文（所有子节点）。
        将事务锁与数据快照获取合并，防止并发数据穿透。
        """

    async def execute(self, op: NodeUpdateOp):
        """
        核心执行器（重构重点）：
        直接接收 LLM 输出的逻辑意图 (NodeUpdateOp)。
        底层存储引擎负责将 Merge/Split/Move 翻译为具体的 DB Transaction：
        - 插入新节点
        - 将 source_ids 对应的节点标记为 ARCHIVED
        - 将父节点 is_dirty 设为 False 并 bump_version
        """


@runtime_checkable
class NodeUpdateStrategy(Protocol):
    """节点更新的智能决策大脑。"""

    async def create_update_op(
            self, context: NodeUpdateContext) -> Optional[NodeUpdateOp]:
        """
        核心大脑：根据当前目录的状态决定下一步动作。
        
        策略内部逻辑示例：
        1. 检查 context.inbox 和 context.children 的总数。
        2. 如果数量较少，不满足 Rebalance 阈值：只需返回一个仅包含 `updated_summary` 的轻量级 NodeUpdateOp（可以基于规则生成摘要，不调 LLM）。
        3. 如果数量超过阈值：触发 LLM，返回包含 Merge/Split/Move 的重量级 NodeUpdateOp。
        4. 如果完全无需修改：返回 None。
        """

    def create_fallback_op(self, context: NodeUpdateContext) -> NodeUpdateOp:
        """LLM 失败或超时时的保底纯规则计划（比如简单的字符串拼接降级）"""


@runtime_checkable
class DistributedLock(Protocol):
    """分布式并发控制契约，确保同一路径的 Rebalance 互斥。"""

    async def acquire(self, key: str, ttl_seconds: int = 60) -> bool:
        """尝试获取锁，返回是否成功。"""

    async def release(self, key: str) -> None:
        """释放指定的锁。"""
