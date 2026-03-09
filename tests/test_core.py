from __future__ import annotations

import pytest
from semafs.core.enums import NodeStatus, NodeType
from semafs.core.exceptions import NodeTypeMismatchError
from semafs.core.node import NodePath, TreeNode
from semafs.core.ops import (MergeOp, PersistOp, RebalancePlan, UpdateContext)
from semafs.executor import Executor
from tests.memory_repo import InMemoryRepository, InMemoryUoWFactory
from semafs.uow import UnitOfWork


class TestNodePath:

    def test_root(self):
        assert str(NodePath.root()) == "root"
        assert NodePath("root").is_root

    def test_normalize(self):
        assert str(NodePath("  ROOT.Work.Item  ")) == "root.work.item"
        assert str(NodePath("a.b.c")) == "a.b.c"

    def test_parent(self):
        assert NodePath("root.work").parent == NodePath("root")
        assert NodePath("root").parent == NodePath("root")

    def test_child(self):
        assert str(NodePath("root").child("work")) == "root.work"
        assert str(NodePath("root.work").child("item")) == "root.work.item"

    def test_depth(self):
        assert NodePath("root").depth == 1
        assert NodePath("root.work").depth == 2

    def test_invalid_segment_raises(self):
        with pytest.raises(ValueError, match="非法路径段"):
            NodePath("root").child("")


# --- TreeNode ---
class TestTreeNode:

    def test_new_category(self):
        cat = TreeNode.new_category(
            path=NodePath("root.work"),
            content="工作",
            display_name="Work",
        )
        assert cat.node_type == NodeType.CATEGORY
        assert cat.path == "root.work"
        assert cat.content == "工作"

    def test_new_leaf(self):
        leaf = TreeNode.new_leaf(
            path=NodePath("root.work.item"),
            content="内容",
            payload={"source": "test"},
        )
        assert leaf.node_type == NodeType.LEAF
        assert leaf.status == NodeStatus.ACTIVE

    def test_new_fragment(self):
        frag = TreeNode.new_fragment(
            parent_path=NodePath("root"),
            content="碎片内容",
            payload={},
        )
        assert frag.node_type == NodeType.LEAF
        assert frag.status == NodeStatus.PENDING_REVIEW
        assert frag.name.startswith("_frag_")

    def test_archive_leaf(self):
        leaf = TreeNode.new_leaf(
            path=NodePath("root.x"),
            content="x",
        )
        leaf.archive()
        assert leaf.status == NodeStatus.ARCHIVED

    def test_archive_category_raises(self):
        cat = TreeNode.new_category(path=NodePath("root.x"), content="")
        with pytest.raises(NodeTypeMismatchError):
            cat.archive()

    def test_clear_dirty_category(self):
        cat = TreeNode.new_category(path=NodePath("root.x"), content="")
        cat.receive_fragment()
        assert cat.is_dirty
        cat.clear_dirty()
        assert not cat.is_dirty


# --- Executor ---
@pytest.fixture
def memory_factory():
    f = InMemoryUoWFactory()
    return f


@pytest.fixture
async def initialized_factory(memory_factory):
    await memory_factory.init()
    return memory_factory


@pytest.mark.asyncio
class TestExecutor:

    async def test_execute_persist_op(self, initialized_factory):
        """PersistOp: 将 PENDING 碎片转为 ACTIVE 叶子"""
        repo = initialized_factory.repo
        parent = TreeNode.new_category(
            path=NodePath("root.work"),
            content="",
            display_name="Work",
        )
        frag = TreeNode.new_fragment(
            parent_path=NodePath("root.work"),
            content="新内容",
            payload={"source": "test"},
        )
        await repo.stage(parent)
        await repo.stage(frag)
        await repo.commit()

        context = UpdateContext(
            parent=parent,
            active_nodes=(),
            pending_nodes=(frag, ),
        )
        plan = RebalancePlan(
            ops=(PersistOp(
                ids=(frag.id, ),
                name="leaf_test",
                content=frag.content,
                payload=dict(frag.payload),
                reasoning="测试",
            ), ),
            updated_content="",
            overall_reasoning="",
        )
        executor = Executor()
        async with initialized_factory.begin() as uow:
            await executor.execute(plan, context, uow)
            await uow.commit()

        children = await repo.list_children("root.work")
        active = [c for c in children if c.status == NodeStatus.ACTIVE]
        assert len(active) == 1
        assert active[0].content == "新内容"
        assert active[0].name == "leaf_test"

    async def test_execute_merge_op(self, initialized_factory):
        """MergeOp: 合并多个叶子为一个"""
        repo = initialized_factory.repo
        parent = TreeNode.new_category(
            path=NodePath("root.work"),
            content="",
        )
        leaf1 = TreeNode.new_leaf(
            path=NodePath("root.work.a"),
            content="A",
        )
        leaf2 = TreeNode.new_leaf(
            path=NodePath("root.work.b"),
            content="B",
        )
        for n in (parent, leaf1, leaf2):
            await repo.stage(n)
        await repo.commit()

        context = UpdateContext(
            parent=parent,
            active_nodes=(leaf1, leaf2),
            pending_nodes=(),
        )
        plan = RebalancePlan(
            ops=(MergeOp(
                ids=(leaf1.id, leaf2.id),
                content="A+B 合并",
                name="merged_ab",
                reasoning="测试合并",
            ), ),
            updated_content="",
        )
        executor = Executor()
        async with initialized_factory.begin() as uow:
            await executor.execute(plan, context, uow)
            await uow.commit()

        children = await repo.list_children(
            "root.work",
            statuses=[NodeStatus.ACTIVE],
        )
        assert len(children) == 1
        assert children[0].content == "A+B 合并"
        assert "_merged_from" in children[0].payload
