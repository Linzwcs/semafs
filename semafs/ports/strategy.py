from __future__ import annotations
from typing import Optional, Protocol, runtime_checkable
from ..core.ops import RebalancePlan, UpdateContext


@runtime_checkable
class Strategy(Protocol):
    """
    整理策略大脑。

    接收当前目录的状态快照，返回整理计划。
    返回 None 表示不需要整理（数量在阈值内，LLM 认为无需变更）。
    """

    async def create_plan(self, context: UpdateContext,
                          max_children: int) -> Optional[RebalancePlan]:
        """
        核心决策接口。

        实现策略可以：
        1. 纯规则：数量少时不调 LLM，直接返回 PersistOp 计划
        2. 纯 LLM：所有情况都调 LLM
        3. 混合：数量超阈值才调 LLM，否则用规则降级
        """
        ...

    def create_fallback_plan(self, context: UpdateContext,
                             max_children: int) -> RebalancePlan:
        """
        LLM 调用失败时的保底规则计划。
        必须是同步方法，保证在 LLM 超时 / 网络错误时能快速降级。
        不能返回 None。
        """
        ...
