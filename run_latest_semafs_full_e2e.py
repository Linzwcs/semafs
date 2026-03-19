"""Full end-to-end usage test for latest semafs package."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
import sys

from semafs import SemaFS
from semafs.algo.place import HintPlacer
from semafs.algo.propagate import DefaultPolicy
from semafs.core.capacity import Budget
from semafs.infra.bus import InMemoryBus
from semafs.core.raw import RawPlan
from semafs.core.snapshot import Snapshot
from semafs.infra.storage.sqlite.store import SQLiteStore
from semafs.infra.storage.sqlite.uow import SQLiteUnitOfWork
from semafs.algo.summarize import RuleSummarizer


class SQLiteUoWFactory:
    """Minimal UoW factory for script testing."""

    def __init__(self, store: SQLiteStore):
        self.store = store

    async def init(self) -> None:
        await self.store.resolve_path("root")

    @asynccontextmanager
    async def begin(self):
        uow = SQLiteUnitOfWork(self.store._get_conn())  # noqa: SLF001
        try:
            yield uow
        except Exception:
            await uow.rollback()
            raise


class NoopStrategy:
    """Minimal strategy used by e2e script."""

    async def draft(self, snapshot: Snapshot) -> RawPlan | None:
        return None


@dataclass
class Report:
    total: int = 0
    passed: int = 0
    failed: int = 0

    def check(self, cond: bool, msg: str) -> None:
        self.total += 1
        if cond:
            self.passed += 1
            print(f"[PASS] {msg}")
        else:
            self.failed += 1
            print(f"[FAIL] {msg}")


async def run_full_test(db_path: Path) -> int:
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    store = SQLiteStore(str(db_path))
    uow_factory = SQLiteUoWFactory(store)
    await uow_factory.init()

    fs = SemaFS(
        store=store,
        uow_factory=uow_factory,
        bus=InMemoryBus(),
        strategy=NoopStrategy(),
        placer=HintPlacer(),
        summarizer=RuleSummarizer(),
        policy=DefaultPolicy(),
        budget=Budget(soft=3, hard=5),
    )

    report = Report()

    print("== Phase 1: Bootstrap ==")
    root = await fs.read("root")
    report.check(root is not None, "root should be readable")
    root_id = await store.resolve_path("root")
    report.check(root_id is not None, "root path should resolve to id")

    print("\n== Phase 2: Mixed-language Writes ==")
    inputs = [
        "用户偏好：喜欢结构化笔记系统，关注长期知识管理。",
        "技术栈：Python + SQLite，强调可解释和可维护。",
        "维护策略：局部重排，向上只做摘要传播。",
        "写入语义：path 只作为入口，内部统一 node_id。",
        "新增想法：支持多策略路由与离线重组。",
        "新增想法：希望可视化查看重组轨迹。",
    ]
    leaf_ids: list[str] = []
    for text in inputs:
        leaf_id = await fs.write(content=text, hint="root")
        leaf_ids.append(leaf_id)
    report.check(len(leaf_ids) == len(inputs), "all writes return leaf_id")

    children = await fs.list("root")
    report.check(len(children) > 0, "root should have children after writes")
    all_names_safe = all(
        child.node.name.replace("_", "").isalnum()
        and child.node.name.isascii()
        for child in children
    )
    report.check(
        all_names_safe,
        "generated leaf/category names should be ASCII path-safe",
    )

    print("\n== Phase 3: Event-driven Maintenance Result ==")
    # Write() publishes Placed events; pulse+keeper should process pending.
    root_children = await store.list_children(root_id) if root_id else []
    has_pending = any(node.stage.value == "pending" for node in root_children)
    report.check(
        not has_pending,
        "children under root should be persisted to active",
    )
    has_active = any(node.stage.value == "active" for node in root_children)
    report.check(
        has_active,
        "children under root should be activated after reconcile",
    )

    root_view = await fs.read("root")
    report.check(
        bool(root_view and root_view.node.summary),
        "root summary should be generated/updated",
    )

    print("\n== Phase 4: Read APIs ==")
    tree = await fs.tree("root", max_depth=3)
    report.check(
        tree is not None and tree.total_nodes >= 2,
        "tree API should work",
    )
    report.check(
        tree is not None and tree.leaf_count >= 1,
        "tree leaf_count valid",
    )

    if children:
        related = await fs.related(children[0].path)
        report.check(related is not None, "related API should return context")
    else:
        report.check(False, "related API test skipped due empty children")

    print("\n== Phase 5: Rename Cascade Consistency ==")
    # Pick a category child under root and rename it via UoW primitive.
    category_children = (
        [
            n for n in (await store.list_children(root_id))
            if n.node_type.value == "category"
        ]
        if root_id
        else []
    )
    if category_children:
        cat = category_children[0]
        old_prefix = cat.path.value
        old_paths = await store.all_paths()
        old_descendants = sorted(
            p for p in old_paths
            if p == old_prefix or p.startswith(old_prefix + ".")
        )
        async with uow_factory.begin() as uow:
            uow.register_rename(cat.id, "renamed_bucket")
            await uow.commit()

        new_path = await store.canonical_path(cat.id)
        report.check(
            new_path == "root.renamed_bucket",
            "renamed category should get canonical path under root",
        )
        new_paths = await store.all_paths()
        moved_descendants = [
            p for p in new_paths
            if p == "root.renamed_bucket"
            or p.startswith("root.renamed_bucket.")
        ]
        report.check(
            len(moved_descendants) == len(old_descendants),
            "descendant path count should remain same after rename cascade",
        )
        old_descendant_survivors = [
            p for p in old_descendants if p in new_paths
        ]
        report.check(
            len(old_descendant_survivors) == 0,
            "original old-subtree paths should disappear after rename",
        )
    else:
        report.check(
            False,
            "rename cascade skipped: no category child was created",
        )

    print("\n== Phase 6: Explicit Sweep ==")
    swept = await fs.sweep(limit=10)
    report.check(swept >= 0, "sweep should run without exception")

    print("\n== Summary ==")
    print(
        f"passed={report.passed}, failed={report.failed}, total={report.total}"
    )
    print(f"db={db_path}")

    store.close()
    return 1 if report.failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run full e2e test against latest semafs package"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="data/semafs_v2_1_4_full_e2e.db",
        help="SQLite db file path",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    code = asyncio.run(run_full_test(Path(args.db).resolve()))
    sys.exit(code)


if __name__ == "__main__":
    main()
