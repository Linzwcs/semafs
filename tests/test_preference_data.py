from __future__ import annotations

import random

import pytest
from semafs.core.enums import NodeStatus, NodeType
from semafs.core.node import NodePath, TreeNode
from semafs.core.ops import RebalancePlan, UpdateContext
from semafs.ports.strategy import Strategy
from semafs.semafs import SemaFS
from tests.fixtures import PREFERENCE_FRAGMENTS, TEST_CATEGORIES
from tests.memory_repo import InMemoryUoWFactory
from tests.test_semafs import MockStrategy


async def ensure_categories(factory: InMemoryUoWFactory) -> None:
    """确保测试所需的分类目录存在（参考 semafs-v0 run.py）。"""
    repo = factory.repo
    for parent_path, name in TEST_CATEGORIES:
        if parent_path == "" and name == "root":
            continue
        full = f"{parent_path}.{name}" if parent_path else name
        existing = await repo.get_by_path(full)
        if not existing:
            path = NodePath(full)
            cat = TreeNode.new_category(
                path=path,
                content="",
                display_name=name,
            )
            await repo.stage(cat)
            await repo.commit()


async def seed_fragments(semafs: SemaFS, fragments: list[tuple[str,
                                                               str]]) -> int:
    """批量写入偏好类记忆碎片，返回写入数量。"""
    count = 0
    for path, content in fragments:
        await semafs.write(path, content, {"source": "test_preference"})
        count += 1
    return count


async def seed_with_maintain(
    semafs: SemaFS,
    fragments: list[tuple[str, str]],
    max_rounds: int = 20,
) -> int:
    """边写入边 maintain：逐条写入，每条后执行 maintain 直到无脏目录。"""
    count = 0
    for path, content in fragments:
        await semafs.write(path, content, {"source": "test_preference"})
        count += 1
        for _ in range(max_rounds):
            processed = await semafs.maintain()
            if processed == 0:
                break
    return count


@pytest.fixture
async def semafs_with_categories():
    """带预建分类的 SemaFS（work, personal, learning, ideas）"""
    factory = InMemoryUoWFactory()
    await factory.init()
    await ensure_categories(factory)
    strategy = MockStrategy()
    fs = SemaFS(uow_factory=factory, strategy=strategy, max_children=10)
    return fs, factory, strategy


@pytest.mark.asyncio
class TestPreferenceData:
    """使用真实偏好数据的测试"""

    async def test_seed_fragments_batch(self, semafs_with_categories):
        """批量写入 PREFERENCE_FRAGMENTS，验证全部写入成功"""
        fs, factory, _ = semafs_with_categories
        n = await seed_fragments(fs, PREFERENCE_FRAGMENTS)
        assert n == len(PREFERENCE_FRAGMENTS)

        # 验证各分类下都有碎片（PENDING 或已整理为 ACTIVE）
        for path, content in PREFERENCE_FRAGMENTS[:4]:
            resolved = path.split(".")[-1] if "." in path else path
            parent = "root." + resolved if resolved != "root" else "root"
            nodes = await fs.list(parent)
            assert len(nodes) >= 1, f"{parent} 应有至少 1 个节点"
            contents = [c.node.content for c in nodes]
            assert content in contents, f"内容应存在: {content[:30]}..."

    async def test_seed_with_maintain(self, semafs_with_categories):
        """边写入边 maintain，验证整理后结构正确"""
        fs, factory, strategy = semafs_with_categories
        # 从各分类各取 2 条（work 0-63, personal 64-127, learning 128-191）
        subset = (PREFERENCE_FRAGMENTS[0:2] + PREFERENCE_FRAGMENTS[64:66] +
                  PREFERENCE_FRAGMENTS[128:130])
        n = await seed_with_maintain(fs, subset)
        assert n == len(subset)

        # 验证 root.work、root.personal、root.learning 有整理后的 ACTIVE 节点
        for cat_name in ["work", "personal", "learning"]:
            path = f"root.{cat_name}"
            nodes = await fs.list(path)
            active = [c for c in nodes if c.node.status == NodeStatus.ACTIVE]
            assert len(active) >= 1, f"{path} 应有至少 1 个 ACTIVE 节点"

    async def test_preference_content_preserved(self, semafs_with_categories):
        """验证偏好内容在写入和整理后完整保留"""
        fs, factory, _ = semafs_with_categories
        # 选几条有代表性的偏好
        samples = [
            ("root.work", "工作时段偏好 9:00-18:00，午休 12:00-13:30"),
            ("root.personal", "咖啡偏好：美式或手冲，不加糖"),
            ("root.learning", "学新框架时先跑通官方 tutorial 再深入"),
        ]
        for path, content in samples:
            await fs.write(path, content, {"source": "test"})
        await fs.maintain()

        for path, expected_content in samples:
            nodes = await fs.list(path)
            contents = [c.node.content for c in nodes]
            assert expected_content in contents, f"路径 {path} 应保留内容: {expected_content[:40]}..."

    async def test_streamed_order_independent(self, semafs_with_categories):
        """打乱顺序写入，验证结果与顺序无关（语义整理应稳定）"""
        fs, factory, _ = semafs_with_categories
        shuffled = list(PREFERENCE_FRAGMENTS[:8])
        random.shuffle(shuffled)
        await seed_with_maintain(fs, shuffled)

        # 验证所有内容都存在
        all_contents = {c for _, c in shuffled}
        for path, content in shuffled:
            parent = path
            nodes = await fs.list(parent)
            found = any(c.node.content == content for c in nodes)
            assert found, f"打乱后内容应存在: {content[:40]}..."
