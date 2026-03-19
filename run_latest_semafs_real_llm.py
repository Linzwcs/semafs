"""Run latest semafs with real dataset and real LLM."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path

from data.test_zh import PREFERENCE_FRAGMENTS
from semafs import SemaFS
from semafs.algo.place import LLMRecursivePlacer, PlacementConfig
from semafs.algo.propagate import DefaultPolicy
from semafs.algo.rebalance import HybridStrategy
from semafs.core.capacity import Budget
from semafs.core.node import Node
from semafs.core.snapshot import Snapshot
from semafs.ports.llm import LLMAdapter
from semafs.infra.bus import InMemoryBus
from semafs.infra.storage.sqlite.store import SQLiteStore
from semafs.infra.storage.sqlite.uow import SQLiteUnitOfWork, SQLiteUoWFactory
from semafs.algo.summarize import LLMSummarizer


class CountingAdapter:
    """Count LLM invocations for observability."""

    def __init__(self, inner: LLMAdapter):
        self._inner = inner
        self.calls = 0
        self.placement_calls = 0
        self.summary_calls = 0

    async def call(self, snapshot):
        self.calls += 1
        return await self._inner.call(snapshot)

    async def call_placement(self, **kwargs):
        self.placement_calls += 1
        return await self._inner.call_placement(**kwargs)

    async def call_summary(self, snapshot):
        self.summary_calls += 1
        return await self._inner.call_summary(snapshot)


async def ensure_category_path(
    store: SQLiteStore,
    uow_factory: SQLiteUoWFactory,
    full_path: str,
) -> None:
    """Ensure category path exists, creating missing segments."""
    if full_path == "root":
        return

    parts = full_path.split(".")
    current_path = "root"
    current_id = await store.resolve_path("root")
    if not current_id:
        raise RuntimeError("root not found")

    for seg in parts[1:]:
        next_path = f"{current_path}.{seg}"
        next_id = await store.resolve_path(next_path)
        if next_id:
            current_path = next_path
            current_id = next_id
            continue

        async with uow_factory.begin() as uow:
            cat = Node.create_category(
                parent_id=current_id,
                parent_path=current_path,
                name=seg,
                summary=f"Category {seg}",
            )
            uow.register_new(cat)
            await uow.commit()

        current_path = next_path
        current_id = await store.resolve_path(next_path)
        if not current_id:
            raise RuntimeError(f"failed to create category: {next_path}")


def normalize_hint_path(path: str) -> str:
    """Normalize external path into canonical root-prefixed path."""
    if path == "root":
        return path
    if path.startswith("root."):
        return path
    return f"root.{path}"


async def build_adapter(args) -> CountingAdapter:
    if args.provider == "openai":
        from openai import AsyncOpenAI
        from semafs.infra.llm.openai import OpenAIAdapter

        client = AsyncOpenAI(
            api_key=args.api_key,
            base_url=args.base_url,
            timeout=180.0,
        )
        return CountingAdapter(OpenAIAdapter(client=client, model=args.model))

    from anthropic import AsyncAnthropic
    from semafs.infra.llm.anthropic import AnthropicAdapter

    client = AsyncAnthropic(
        api_key=args.api_key,
        base_url=args.base_url,
        timeout=180.0,
    )
    return CountingAdapter(AnthropicAdapter(client=client, model=args.model))


async def run(args) -> None:
    db_path = Path(args.db).resolve()
    if args.reset and db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    store = SQLiteStore(str(db_path))
    uow_factory = SQLiteUoWFactory(store)
    await uow_factory.init()

    counted_adapter = await build_adapter(args)
    strategy = HybridStrategy(adapter=counted_adapter)
    placer = LLMRecursivePlacer(
        store=store,
        adapter=counted_adapter,
        config=PlacementConfig(
            max_depth=args.place_max_depth,
            min_confidence=args.place_min_confidence,
        ),
    )

    fs = SemaFS(
        store=store,
        uow_factory=uow_factory,
        bus=InMemoryBus(),
        strategy=strategy,
        placer=placer,
        summarizer=LLMSummarizer(counted_adapter),
        policy=DefaultPolicy(),
        budget=Budget(soft=args.soft, hard=args.hard),
    )

    fragments = PREFERENCE_FRAGMENTS[:args.data_size]
    normalized_fragments = [(normalize_hint_path(target_path), content)
                            for target_path, content in fragments]
    for target_path, _ in normalized_fragments:
        await ensure_category_path(store, uow_factory, target_path)

    print("== Writing Real Fragments ==")
    for idx, (target_path, content) in enumerate(
            normalized_fragments,
            start=1,
    ):
        if args.preview_routes > 0 and idx <= args.preview_routes:
            route = await placer.place(content, start_path="root")
            joined = " -> ".join(step.current_path for step in route.steps)
            print(f"[route {idx}] target={route.target_path} "
                  f"steps={joined or 'root'}")
        hint_value = None if args.ignore_hint else target_path
        leaf_id = await fs.write(content=content, hint=hint_value)
        used = hint_value if hint_value else "(routed)"
        print(f"[{idx}/{len(fragments)}] {used} -> {leaf_id[:8]}")

    swept = await fs.sweep(limit=args.sweep_limit)
    print("\n== Result ==")
    print(f"provider={args.provider}")
    print(f"model={args.model}")
    print(f"db={db_path}")
    print(f"fragments={len(fragments)}")
    print(f"llm_calls={counted_adapter.calls}")
    print(f"placement_calls={counted_adapter.placement_calls}")
    print(f"sweep_processed={swept}")

    for p in (
            "root",
            "root.work",
            "root.personal",
            "root.learning",
            "root.ideas",
    ):
        view = await fs.read(p)
        if not view:
            continue
        print(f"- {p}: children={view.child_count}")

    store.close()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Simulate latest semafs with real data + real LLM")
    parser.add_argument(
        "--provider",
        choices=["openai", "anthropic"],
        default="openai",
    )
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--db", default="data/semafs_real_llm.db")
    parser.add_argument("--data-size", type=int, default=24)
    parser.add_argument("--soft", type=int, default=4)
    parser.add_argument("--hard", type=int, default=6)
    parser.add_argument("--sweep-limit", type=int, default=50)
    parser.add_argument("--ignore-hint", action="store_true")
    parser.add_argument("--preview-routes", type=int, default=0)
    parser.add_argument("--place-max-depth", type=int, default=4)
    parser.add_argument("--place-min-confidence", type=float, default=0.55)
    parser.add_argument("--reset", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.api_key:
        env_name = ("OPENAI_API_KEY"
                    if args.provider == "openai" else "ANTHROPIC_API_KEY")
        args.api_key = os.getenv(env_name)
    if not args.api_key:
        raise SystemExit("Missing API key: pass --api-key or set env var "
                         "OPENAI_API_KEY / ANTHROPIC_API_KEY")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
