from __future__ import annotations

from typing import Optional
from unittest.mock import AsyncMock

import pytest
from semafs.core.enums import NodeStatus, NodeType
from semafs.core.ops import RebalancePlan, UpdateContext
from semafs.ports.strategy import Strategy
from semafs.semafs import SemaFS
from tests.memory_repo import InMemoryUoWFactory


class MockStrategy(Strategy):

    def __init__(self, plan: Optional[RebalancePlan] = None):
        self._plan = plan  # 若指定则返回此计划，否则用 fallback
        self.create_plan_calls = []

    async def create_plan(self, context: UpdateContext,
                          max_children: int) -> Optional[RebalancePlan]:
        self.create_plan_calls.append((context, max_children))
        if self._plan is not None:
            return self._plan
        return self.create_fallback_plan(context, max_children)

    def create_fallback_plan(self, context: UpdateContext,
                             max_children: int) -> RebalancePlan:
        from semafs.core.ops import PersistOp

        ops = []
        for node in context.pending_nodes:
            ops.append(
                PersistOp(
                    ids=(node.id, ),
                    name=f"leaf_{node.id[:8]}",
                    content=node.content,
                    payload=dict(node.payload),
                    reasoning="fallback",
                ))
        return RebalancePlan(
            ops=tuple(ops),
            updated_content=context.parent.content or "",
            overall_reasoning="fallback",
            is_llm_plan=False,
        )


@pytest.fixture
async def semafs_with_mock():
    """带 Mock 策略的 SemaFS，使用内存存储"""
    factory = InMemoryUoWFactory()
    await factory.init()
    strategy = MockStrategy()
    fs = SemaFS(uow_factory=factory, strategy=strategy, max_children=10)
    return fs, factory, strategy


@pytest.mark.asyncio
class TestSemaFS:

    async def test_write_and_read(self, semafs_with_mock):
        """写入碎片后能读取"""
        fs, factory, _ = semafs_with_mock
        frag_id = await fs.write("root", "测试内容", {"source": "test"})
        assert frag_id

        nodes = await fs.list("root")
        assert len(nodes) >= 1
        pending = [
            n for n in nodes if n.node.status == NodeStatus.PENDING_REVIEW
        ]
        assert len(pending) == 1
        assert pending[0].node.content == "测试内容"

    async def test_write_resolves_category(self, semafs_with_mock):
        """写入时自动解析到最近存在的 category"""
        fs, factory, _ = semafs_with_mock
        # 先创建 root.work
        from semafs.core.node import NodePath, TreeNode

        repo = factory.repo
        work = TreeNode.new_category(
            path=NodePath("root.work"),
            content="",
            display_name="Work",
        )
        await repo.stage(work)
        await repo.commit()

        # 写入 root.work.item 会解析到 root.work
        frag_id = await fs.write("root.work.item", "内容", {})
        assert frag_id
        nodes = await fs.list("root.work")
        assert len(nodes) >= 1

    async def test_maintain_with_fallback(self, semafs_with_mock):
        """maintain 使用 fallback 策略整理碎片"""
        fs, factory, strategy = semafs_with_mock
        await fs.write("root", "碎片1", {})
        await fs.write("root", "碎片2", {})

        processed = await fs.maintain()
        assert processed >= 1
        assert len(strategy.create_plan_calls) >= 1

        nodes = await fs.list("root")
        active = [n for n in nodes if n.node.status == NodeStatus.ACTIVE]
        assert len(active) >= 2
