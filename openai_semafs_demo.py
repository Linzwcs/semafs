from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import sys
from pathlib import Path
from semafs.core.enums import NodeStatus
from semafs.core.node import NodePath, TreeNode
from semafs.semafs import SemaFS
from semafs.storage.sqlite.factory import SQLiteUoWFactory
from data.test_zh import PREFERENCE_FRAGMENTS, TEST_CATEGORIES

_project_root = Path('./')


async def ensure_categories(factory: SQLiteUoWFactory) -> None:
    for parent_path, name in TEST_CATEGORIES:
        if parent_path == "" and name == "root":
            continue
        full = f"{parent_path}.{name}" if parent_path else name
        existing = await factory.repo.get_by_path(full)
        if not existing:
            async with factory.begin() as uow:
                cat = TreeNode.new_category(
                    path=NodePath(full),
                    content="",
                    display_name=name,
                    name_editable=False,
                )
                uow.register_new(cat)
                await uow.commit()
            print(f"  Created category: {full}")


async def seed_fragments(semafs: SemaFS, fragments: list[tuple[str,
                                                               str]]) -> int:
    count = 0
    for path, content in fragments:
        await semafs.write(path, content, {"source": "run_seed"})
        count += 1
        print(f"  📥 [{path}] {content[:40]}...")
    return count


async def seed_with_maintain(
    semafs: SemaFS,
    fragments: list[tuple[str, str]],
    stream: bool = False,
    delay_min: float = 0.2,
    delay_max: float = 1.0,
    max_rounds: int = 20,
) -> int:
    data = list(fragments)
    if stream:
        random.shuffle(data)
    count = 0
    for path, content in data:
        await semafs.write(path, content, {"source": "run_seed"})
        count += 1
        print(f"  📥 [{count}/{len(data)}] {path}: {content[:40]}...")
        if stream:
            await asyncio.sleep(random.uniform(delay_min, delay_max))

        for _ in range(max_rounds):
            processed = await semafs.maintain()
            if processed == 0:
                break

    return count


def _get_db_path(name: str, override: str | None = None) -> Path:
    if override:
        return Path(override)
    return _project_root / "tests" / "output" / f"semafs_{name}.db"


async def run_openai(
    db_path: str | None = None,
    stream: bool = False,
    data_size: int = 64,
    max_children: int = 4,
    base_url: str | None = None,
) -> None:
    """OpenAI mode: uses real LLM for organization."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        print("Please install: pip install openai")
        sys.exit(1)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Please set environment variable OPENAI_API_KEY")
        sys.exit(1)

    path = _get_db_path("openai_demo", db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"\nDatabase: {path}")

    from semafs.infra.llm.openai import OpenAIAdapter
    from semafs.strategies.hybrid import HybridStrategy

    resolved_base_url = base_url or os.getenv("OPENAI_BASE_URL",
                                              "http://35.220.164.252:3888/v1")
    client = AsyncOpenAI(api_key=api_key,
                         base_url=resolved_base_url,
                         timeout=120.0)
    adapter = OpenAIAdapter(client, model="gpt-4o-mini")
    strategy = HybridStrategy(adapter, max_children=max_children)

    factory = SQLiteUoWFactory(path)
    await factory.init()
    try:
        semafs = SemaFS(uow_factory=factory,
                        strategy=strategy,
                        max_children=max_children)

        print("\n1. Creating category directories...")
        await ensure_categories(factory)

        fragments = PREFERENCE_FRAGMENTS[:data_size]
        print(
            f"\n2. Writing {len(fragments)} fragments and maintaining (LLM may be slow)..."
        )
        n = await seed_with_maintain(semafs, fragments, stream=stream)
        print(f"  Wrote {n} fragments")
        print("\n3. Reading results...")
        for cat_path in ["root.work", "root.personal"]:
            views = await semafs.list(cat_path)
            active = [v for v in views if v.node.status == NodeStatus.ACTIVE]
            print(f"  [{cat_path}]: {len(active)} items")
        print("\nDone.\n")
    finally:
        await factory.close()


def main():
    parser = argparse.ArgumentParser(description="SemaFS test data builder")
    parser.add_argument("--openai", action="store_true", help="Use OpenAI API")
    parser.add_argument("--db", default=None, help="Database path")
    parser.add_argument("--stream",
                        action="store_true",
                        help="Stream writes (shuffle + random delay)")
    parser.add_argument(
        "--data-size",
        type=int,
        default=64,
        metavar="N",
        help="Number of fragments to use from test data (default: 64)")
    parser.add_argument(
        "--max-children",
        type=int,
        default=4,
        metavar="N",
        help="Max children threshold for LLM reorganization (default: 4)")
    parser.add_argument(
        "--base-url",
        default=None,
        help=
        "OpenAI API base URL (default: OPENAI_BASE_URL env or built-in default)"
    )
    parser.add_argument("--export",
                        action="store_true",
                        help="Export database to Markdown view")
    parser.add_argument("-o",
                        "--output",
                        default=None,
                        help="Output file path for export")
    parser.add_argument("-v",
                        "--verbose",
                        action="store_true",
                        help="Verbose logging")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(message)s")

    if args.export:
        from semafs.export import export_to_markdown
        db_path = Path(args.db) if args.db else _get_db_path(
            "openai_demo", None)
        if not db_path.exists():
            db_path = _get_db_path("demo", None)
        if not db_path.exists():
            print(f"Error: database not found: {db_path}", file=sys.stderr)
            sys.exit(1)
        out_path = Path(args.output) if args.output else None
        md = asyncio.run(export_to_markdown(db_path, out_path))
        if not out_path:
            print(md)
        return

    if args.openai:
        asyncio.run(
            run_openai(
                db_path=args.db,
                stream=args.stream,
                data_size=args.data_size,
                max_children=args.max_children,
                base_url=args.base_url,
            ))
    else:
        raise ValueError("Invalid argument, only support --openai")


if __name__ == "__main__":
    main()
