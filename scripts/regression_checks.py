"""Targeted regression checks for path cascade and plan guard rules."""

from __future__ import annotations

import asyncio
import os
import tempfile
from contextlib import asynccontextmanager

from semafs.core.capacity import Budget
from semafs.core.node import Node
from semafs.core.ops import GroupOp, MoveOp, Plan, RenameOp
from semafs.core.raw import RawMerge, RawGroup, RawPlan
from semafs.core.snapshot import Snapshot
from semafs.core.summary import (
    build_category_meta,
    normalize_category_meta,
    render_category_summary,
)
from semafs.engine.guard import PlanGuard, GuardRejectCode
from semafs.engine.keeper import Keeper
from semafs.engine.resolver import Resolver
from semafs.infra.storage.sqlite.store import SQLiteStore
from semafs.infra.storage.sqlite.uow import SQLiteUnitOfWork
from semafs.semafs import SemaFS
from semafs.infra.bus import InMemoryBus
from semafs.algo.place import HintPlacer
from semafs.algo.propagate import DefaultPolicy
from semafs.algo.rebalance.sanitize import parse_raw_ops
from semafs.infra.llm import prompt as prompt_module
from semafs.algo.summarize import RuleSummarizer


class _UoWFactory:
    def __init__(self, store: SQLiteStore):
        self.store = store

    @asynccontextmanager
    async def begin(self):
        uow = SQLiteUnitOfWork(self.store._get_conn())  # noqa: SLF001
        try:
            yield uow
        except Exception:
            await uow.rollback()
            raise


class _FactoryForFS(_UoWFactory):
    async def init(self) -> None:
        await self.store.resolve_path("root")


class _NoopStrategy:
    async def draft(self, snapshot: Snapshot) -> RawPlan | None:
        return None


async def _rename_and_move_cascade_check() -> None:
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()
    store = SQLiteStore(db.name)
    uow_factory = _UoWFactory(store)
    try:
        await store.resolve_path("root")
        root = await store.get_by_path("root")
        if not root:
            raise AssertionError("missing root")

        async with uow_factory.begin() as uow:
            parent = Node.create_category(root.id, "root", "work", "work")
            sibling = Node.create_category(root.id, "root", "personal", "p")
            uow.register_new(parent)
            uow.register_new(sibling)
            await uow.commit()

        parent = await store.get_by_path("root.work")
        sibling = await store.get_by_path("root.personal")
        if not parent or not sibling:
            raise AssertionError("missing first-level categories")

        async with uow_factory.begin() as uow:
            child = Node.create_category(
                parent.id,
                "root.work",
                "projects",
                "p",
            )
            uow.register_new(child)
            await uow.commit()

        child = await store.get_by_path("root.work.projects")
        if not child:
            raise AssertionError("missing child category")

        async with uow_factory.begin() as uow:
            leaf = Node.create_leaf(
                parent_id=child.id,
                parent_path=child.path.value,
                name="leaf_abc123",
                content="hello",
            )
            uow.register_new(leaf)
            await uow.commit()

        leaf = await store.get_by_path("root.work.projects.leaf_abc123")
        if not leaf:
            raise AssertionError("missing test leaf")

        async with uow_factory.begin() as uow:
            uow.register_rename(parent.id, "development")
            await uow.commit()

        renamed_leaf = await store.get_by_id(leaf.id)
        if not renamed_leaf:
            raise AssertionError("leaf disappeared after rename")
        assert (
            renamed_leaf.path.value
            == "root.development.projects.leaf_abc123"
        )

        renamed_parent = await store.get_by_path("root.development")
        if not renamed_parent:
            raise AssertionError("missing renamed parent")

        async with uow_factory.begin() as uow:
            uow.register_move(child.id, sibling.id)
            await uow.commit()

        moved_leaf = await store.get_by_id(leaf.id)
        if not moved_leaf:
            raise AssertionError("leaf disappeared after move")
        assert moved_leaf.path.value == "root.personal.projects.leaf_abc123"
    finally:
        store.close()
        os.unlink(db.name)


def _plan_guard_check() -> None:
    target = Node.create_root()
    category = Node.create_category(target.id, "root", "work", "work")
    leaf = Node.create_leaf(
        parent_id=target.id,
        parent_path="root",
        name="leaf_deadbe",
        content="c",
    )
    snapshot = Snapshot(
        target=target,
        leaves=(leaf,),
        subcategories=(category,),
        pending=(),
        siblings=(),
        ancestors=(),
        budget=Budget(soft=4, hard=6),
        used_paths=frozenset(
            {"root", "root.work", "root.leaf_deadbe"}
        ),
    )
    plan = Plan(
        ops=(
            GroupOp(
                source_ids=(leaf.id,),
                category_path="root.new_records",
                category_summary="x",
                category_keywords=(),
            ),
            MoveOp(leaf_id=leaf.id, target_path="root.misc"),
            RenameOp(node_id=leaf.id, new_name="semantic_name"),
        )
    )
    filtered, report = PlanGuard().filter_ops_for_snapshot(
        plan,
        snapshot,
    )
    assert len(filtered.ops) == 0
    assert report.total_rejects == 3
    assert report.counts_by_code().get("INVALID_GROUP_PATH", 0) == 1
    assert report.counts_by_code().get("GENERIC_MOVE_TARGET", 0) == 1
    assert report.counts_by_code().get("INVALID_RENAME_NAME", 0) == 1


def _resolver_merge_name_check() -> None:
    target = Node.create_root()
    leaf_a = Node.create_leaf(
        parent_id=target.id,
        parent_path="root",
        name="leaf_a",
        content="a",
    )
    leaf_b = Node.create_leaf(
        parent_id=target.id,
        parent_path="root",
        name="leaf_b",
        content="b",
    )
    snapshot = Snapshot(
        target=target,
        leaves=(leaf_a, leaf_b),
        subcategories=(),
        pending=(),
        siblings=(),
        ancestors=(),
        budget=Budget(soft=4, hard=6),
        used_paths=frozenset({"root", "root.leaf_a", "root.leaf_b"}),
    )
    raw = RawPlan(
        ops=(
            RawMerge(
                source_ids=(leaf_a.id, leaf_b.id),
                new_content="merged",
                new_name="",
                evidence=("shared_topic",),
            ),
        )
    )
    resolver = Resolver()
    name1 = resolver.compile(raw, snapshot).ops[0].new_name
    name2 = resolver.compile(raw, snapshot).ops[0].new_name
    assert name1.startswith("leaf_")
    assert name2.startswith("leaf_")
    assert name1 != "leaf_da39a3"
    assert name2 != "leaf_da39a3"
    assert name1 != name2


def _resolver_group_compile_check() -> None:
    target = Node.create_root()
    leaf_a = Node.create_leaf(
        parent_id=target.id,
        parent_path="root",
        name="leaf_a",
        content="a",
    )
    leaf_b = Node.create_leaf(
        parent_id=target.id,
        parent_path="root",
        name="leaf_b",
        content="b",
    )
    snapshot = Snapshot(
        target=target,
        leaves=(leaf_a, leaf_b),
        subcategories=(),
        pending=(),
        siblings=(),
        ancestors=(),
        budget=Budget(soft=4, hard=6),
        used_paths=frozenset({"root", "root.leaf_a", "root.leaf_b"}),
    )
    raw = RawPlan(
        ops=(
            RawGroup(
                source_ids=(leaf_a.id, leaf_b.id),
                category_name="planning",
                category_summary="planning topics",
                category_keywords=("planning", "project"),
            ),
        )
    )
    plan = Resolver().compile(raw, snapshot)
    assert len(plan.ops) == 1
    group = plan.ops[0]
    assert isinstance(group, GroupOp)
    assert group.category_keywords == ("planning", "project")


def _summary_format_check() -> None:
    meta = build_category_meta(
        raw_summary="This category stores planning notes.",
        leaf_texts=("project scope and timeline",),
        child_names=("execution", "review"),
    )
    meta = normalize_category_meta(meta)
    summary = render_category_summary(meta)
    assert set(meta.keys()) == {"keywords", "summary", "ext"}
    assert isinstance(meta["keywords"], list)
    assert isinstance(meta["summary"], str)
    assert isinstance(meta["ext"], dict)
    assert summary == meta["summary"]


def _keyword_dual_path_check() -> None:
    llm_meta = build_category_meta(
        raw_summary="Focus on planning workflows.",
        keywords=("planning", "workflow"),
    )
    assert llm_meta["ext"].get("keyword_source") == "llm"
    no_keyword_meta = build_category_meta(
        raw_summary="Focus on planning workflows.",
    )
    assert no_keyword_meta["ext"].get("keyword_source") == "none"
    assert isinstance(no_keyword_meta.get("keywords"), list)


def _hybrid_sanitize_check() -> None:
    target = Node.create_root()
    leaf_a = Node.create_leaf(
        parent_id=target.id,
        parent_path="root",
        name="leaf_a",
        content="project timeline and milestones",
    )
    leaf_b = Node.create_leaf(
        parent_id=target.id,
        parent_path="root",
        name="leaf_b",
        content="project budget and cost tracking",
    )
    snapshot = Snapshot(
        target=target,
        leaves=(leaf_a, leaf_b),
        subcategories=(),
        pending=(),
        siblings=(),
        ancestors=(),
        budget=Budget(soft=4, hard=6),
        used_paths=frozenset({"root", "root.leaf_a", "root.leaf_b"}),
    )
    raw_ops = [
        {
            "op_type": "MERGE",
            "ids": [leaf_a.id[:8], leaf_b.id[:8]],
            "name": "leaf_merged",
            "content": "merged leaf content",
            "evidence": ["project"],
        },
        {
            "op_type": "GROUP",
            "ids": [leaf_a.id[:8], leaf_b.id[:8]],
            "name": "planning",
            "content": "",
        },
        {
            "op_type": "MERGE",
            "ids": [leaf_a.id[:8], leaf_b.id[:8]],
            "name": "leaf_invalid",
            "content": "x",
            "evidence": [],
        },
    ]
    parsed = parse_raw_ops(raw_ops, snapshot)
    assert len(parsed) == 2
    assert parsed[1].category_summary.strip() != ""
    assert 2 <= len(parsed[1].category_keywords) <= 4


def _prompt_contract_check() -> None:
    schema = prompt_module._TREE_OPS_SCHEMA[  # noqa: SLF001
        "input_schema"
    ]["properties"]
    summary_schema = prompt_module._SUMMARY_SCHEMA[  # noqa: SLF001
        "input_schema"
    ]["properties"]

    assert prompt_module.KEYWORD_MIN_ITEMS == 2
    assert prompt_module.KEYWORD_MAX_ITEMS == 6
    assert prompt_module.SUMMARY_MAX_CHARS == 500
    assert (
        schema["updated_keywords"]["minItems"]
        == prompt_module.KEYWORD_MIN_ITEMS
    )
    assert (
        schema["updated_keywords"]["maxItems"]
        == prompt_module.KEYWORD_MAX_ITEMS
    )
    assert (
        summary_schema["keywords"]["minItems"]
        == prompt_module.KEYWORD_MIN_ITEMS
    )
    assert (
        summary_schema["keywords"]["maxItems"]
        == prompt_module.KEYWORD_MAX_ITEMS
    )
    op_properties = schema["ops"]["items"]["properties"]
    assert "keywords" in op_properties
    assert (
        op_properties["keywords"]["minItems"]
        == prompt_module.KEYWORD_MIN_ITEMS
    )
    assert (
        op_properties["keywords"]["maxItems"]
        == prompt_module.KEYWORD_MAX_ITEMS
    )
    assert "updated_summary" in schema
    assert "updated_content" not in schema


def _guard_reason_code_check() -> None:
    assert GuardRejectCode.INVALID_UPDATED_NAME.value == "INVALID_UPDATED_NAME"
    raw = RawPlan(
        ops=(
            RawMerge(
                source_ids=("a", "b"),
                new_content="merged",
                new_name="leaf_x",
                evidence=(),
            ),
        )
    )
    _, raw_report = PlanGuard().validate_raw_plan(raw)
    assert raw_report.total_rejects == 1
    assert raw_report.counts_by_code().get("RAW_MERGE_NO_EVIDENCE", 0) == 1
    assert (
        PlanGuard()._sanitize_summary(  # noqa: SLF001
            "op_type: MERGE and overall_reasoning"
        )
        is None
    )


def _guard_metrics_aggregate_check() -> None:
    raw = RawPlan(
        ops=(
            RawMerge(
                source_ids=("a", "b"),
                new_content="merged",
                new_name="leaf_x",
                evidence=(),
            ),
        )
    )
    _, report_a = PlanGuard().validate_raw_plan(raw)
    _, report_b = PlanGuard().validate_plan(Plan(ops=()))
    total, counts = Keeper._guard_metrics(  # noqa: SLF001
        reports=(report_a, report_b)
    )
    assert total == 1
    assert counts.get("RAW_MERGE_NO_EVIDENCE", 0) == 1


async def _meta_boundary_check() -> None:
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()
    store = SQLiteStore(db.name)
    try:
        await store.resolve_path("root")
        root = await store.get_by_path("root")
        if not root:
            raise AssertionError("missing root")
        broken = Node.create_category(
            parent_id=root.id,
            parent_path="root",
            name="work",
            summary="legacy summary",
            category_meta={"keywords": "oops", "summary": "", "ext": "x"},
        )
        await store.save(broken)
        loaded = await store.get_by_path("root.work")
        if not loaded:
            raise AssertionError("missing saved category")
        assert isinstance(loaded.category_meta.get("keywords"), list)
        assert isinstance(loaded.category_meta.get("ext"), dict)
        assert loaded.summary == loaded.category_meta.get("summary")
    finally:
        store.close()
        os.unlink(db.name)


async def _path_lookup_check() -> None:
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()
    store = SQLiteStore(db.name)
    factory = _FactoryForFS(store)
    await factory.init()
    fs = SemaFS(
        store=store,
        uow_factory=factory,
        bus=InMemoryBus(),
        strategy=_NoopStrategy(),
        placer=HintPlacer(),
        summarizer=RuleSummarizer(),
        policy=DefaultPolicy(),
    )
    try:
        root = await store.get_by_path("root")
        if not root:
            raise AssertionError("missing root")
        async with factory.begin() as uow:
            cat = Node.create_category(
                root.id,
                "root",
                "planning",
                "planning notes",
                category_meta={
                    "keywords": ["planning"],
                    "summary": "planning summary",
                    "ext": {},
                },
            )
            uow.register_new(cat)
            await uow.commit()
        by_path = await fs.read("root.planning")
        assert by_path is not None
        listed = await fs.list("root")
        assert any(item.path == "root.planning" for item in listed)
        stats = await fs.stats()
        assert stats.total_categories >= 2
        assert stats.total_leaves == 0
        assert stats.max_depth >= 1
        assert any(path == "root" for path, _ in stats.top_categories)
    finally:
        store.close()
        os.unlink(db.name)


async def _skeleton_lock_and_summary_check() -> None:
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()
    store = SQLiteStore(db.name)
    factory = _FactoryForFS(store)
    await factory.init()
    fs = SemaFS(
        store=store,
        uow_factory=factory,
        bus=InMemoryBus(),
        strategy=_NoopStrategy(),
        placer=HintPlacer(),
        summarizer=RuleSummarizer(),
        policy=DefaultPolicy(),
    )
    try:
        changed = await fs.apply_skeleton({"root": {"work": {}}})
        assert changed == 1
        work = await store.get_by_path("root.work")
        if not work:
            raise AssertionError("missing skeleton category root.work")
        assert work.skeleton is True
        assert work.name_editable is False

        snapshot = Snapshot(
            target=Node.create_root(),
            leaves=(),
            subcategories=(work,),
            pending=(),
            siblings=(),
            ancestors=(),
            budget=Budget(soft=4, hard=6),
            used_paths=frozenset({"root", "root.work"}),
        )
        plan = Plan(ops=(RenameOp(node_id=work.id, new_name="renamed"),))
        filtered, report = PlanGuard().filter_ops_for_snapshot(plan, snapshot)
        assert len(filtered.ops) == 0
        assert (
            report.counts_by_code().get(
                GuardRejectCode.SKELETON_RENAME_BLOCKED.value,
                0,
            )
            == 1
        )

        before_summary = work.summary or ""
        await fs.write(content="weekly planning notes", hint="root.work")
        await fs.sweep(limit=10)
        updated = await store.get_by_path("root.work")
        if not updated:
            raise AssertionError("skeleton category disappeared")
        assert updated.name == "work"
        assert "weekly planning notes" in (updated.summary or "")
        assert updated.summary != before_summary
    finally:
        store.close()
        os.unlink(db.name)


async def main() -> None:
    await _rename_and_move_cascade_check()
    _plan_guard_check()
    _resolver_merge_name_check()
    _resolver_group_compile_check()
    _summary_format_check()
    _keyword_dual_path_check()
    _hybrid_sanitize_check()
    _prompt_contract_check()
    _guard_reason_code_check()
    _guard_metrics_aggregate_check()
    await _meta_boundary_check()
    await _path_lookup_check()
    await _skeleton_lock_and_summary_check()
    print("OK: regression checks passed")


if __name__ == "__main__":
    asyncio.run(main())
