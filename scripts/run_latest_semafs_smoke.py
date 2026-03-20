"""Smoke run script for latest semafs package."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from semafs import SemaFS
from semafs.algo.place import HintPlacer
from semafs.algo.propagate import DefaultPolicy
from semafs.core.capacity import Budget
from semafs.core.raw import RawPlan
from semafs.core.snapshot import Snapshot
from semafs.infra.bus import InMemoryBus
from semafs.infra.storage.sqlite.store import SQLiteStore
from semafs.infra.storage.sqlite.uow import SQLiteUnitOfWork
from semafs.algo.summarize import RuleSummarizer


class SQLiteUoWFactory:
    """Minimal UoW factory for smoke testing."""

    def __init__(self, store: SQLiteStore):
        self.store = store

    async def init(self) -> None:
        # Touch root to ensure schema + root bootstrap are done.
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
    """Minimal strategy used by smoke script."""

    async def draft(self, snapshot: Snapshot) -> RawPlan | None:
        return None


async def run_smoke(db_path: Path) -> None:
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
        budget=Budget(soft=4, hard=6),
    )

    inputs = [
        "User preference: likes structured long-term note systems.",
        "Tech stack: Python plus SQLite, prioritizes explainable design.",
        "Maintenance policy: local rebalance, upward summary only.",
        "Write semantics: path as entry, internal identity by node id.",
    ]

    print("== 写入阶段 ==")
    leaf_ids: list[str] = []
    for text in inputs:
        leaf_id = await fs.write(content=text, hint="root")
        leaf_ids.append(leaf_id)
        print(f"- write ok: {leaf_id}")

    print("\n== 维护阶段 ==")
    processed = await fs.sweep(limit=10)
    print(f"- sweep processed: {processed}")

    print("\n== 读取验证 ==")
    root_view = await fs.read("root")
    if not root_view:
        raise RuntimeError("root view not found")
    print(f"- root child_count: {root_view.child_count}")
    print(f"- root summary: {root_view.node.summary}")

    children = await fs.list("root")
    print("- root children:")
    for child in children:
        stage = child.node.stage.value
        print(f"  - {child.path} [{child.node.node_type.value}/{stage}]")

    tree = await fs.tree("root", max_depth=2)
    if tree:
        print(f"- tree total_nodes(depth<=2): {tree.total_nodes}")
    else:
        print("- tree unavailable")

    root_id = await store.resolve_path("root")
    if root_id:
        resolved_path = await store.canonical_path(root_id)
        print(f"- root id->path projection: {root_id} -> {resolved_path}")
    print(f"- db file: {db_path}")

    store.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run latest semafs smoke test"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="data/semafs_v2_1_4_smoke.db",
        help="SQLite db file path",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(run_smoke(Path(args.db).resolve()))


if __name__ == "__main__":
    main()
