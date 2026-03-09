#!/usr/bin/env python3
"""
SemaFS 运行入口：使用测试偏好数据构建数据库。

支持两种模式：
1. Mock 模式（默认）：使用 RuleOnlyStrategy，无需 API Key
2. OpenAI 模式：设置 OPENAI_API_KEY 后使用 HybridLLMStrategy + GPT

用法：
    python -m semafs.run                    # Mock 模式，构建数据库
    python -m semafs.run --openai           # OpenAI 模式（需 API Key）
    python -m semafs.run --db ./mydb.db     # 指定数据库路径
    python -m semafs.run --stream           # 流式写入：打乱顺序 + 随机间隔
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import sys
from pathlib import Path
from time import sleep

# 确保项目根在 path 中
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from semafs.core.enums import NodeStatus
from semafs.core.node import NodePath, TreeNode
from semafs.semafs import SemaFS
from semafs.storage.sqlite.factory import SQLiteUoWFactory
from semafs.strategies.rule import RuleOnlyStrategy
from semafs.tests.fixtures import PREFERENCE_FRAGMENTS, TEST_CATEGORIES


async def ensure_categories(factory: SQLiteUoWFactory) -> None:
    """确保测试所需的分类目录存在。"""
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
            print(f"  创建分类: {full}")


async def seed_fragments(semafs: SemaFS, fragments: list[tuple[str,
                                                               str]]) -> int:
    """批量写入偏好类记忆碎片。"""
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
    """边写入边 maintain，直到无脏目录。"""
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


async def run_mock(db_path: str | None = None, stream: bool = False) -> None:
    """Mock 模式：使用 RuleOnlyStrategy 构建数据库。"""
    path = _get_db_path("demo", db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n数据库: {path}")

    factory = SQLiteUoWFactory(path)
    await factory.init()
    try:
        strategy = RuleOnlyStrategy()
        semafs = SemaFS(uow_factory=factory,
                        strategy=strategy,
                        max_children=10)

        print("\n1️⃣ 创建分类目录...")
        await ensure_categories(factory)

        print("\n2️⃣ 写入偏好数据并整理" + ("（流式）" if stream else "") + "...")
        n = await seed_with_maintain(semafs,
                                     PREFERENCE_FRAGMENTS,
                                     stream=stream)
        print(f"  共写入 {n} 条碎片")

        print("\n3️⃣ 读取结果...")
        for cat_path in ["root.work", "root.personal", "root.learning"]:
            nodes = await semafs.read(cat_path)
            active = [c for c in nodes if c.status == NodeStatus.ACTIVE]
            print(f"  [{cat_path}]: {len(active)} 条")
            for c in active[:2]:
                print(f"    - {c.content[:50]}...")

        print("\n✅ 数据库构建完成\n")
    finally:
        await factory.close()


async def run_openai(db_path: str | None = None, stream: bool = False) -> None:
    """OpenAI 模式：使用真实 LLM 整理。"""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        print("请安装: pip install openai")
        sys.exit(1)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("请设置环境变量 OPENAI_API_KEY")
        sys.exit(1)

    path = _get_db_path("openai_demo", db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n数据库: {path}")

    from semafs.infra.llm.openai import OpenAIAdapter
    from semafs.strategies.hybrid import HybridLLMStrategy

    client = AsyncOpenAI(api_key=api_key,
                         base_url="http://35.220.164.252:3888/v1",
                         timeout=120.0)
    adapter = OpenAIAdapter(client, model="gpt-4o-mini")
    strategy = HybridLLMStrategy(adapter, max_nodes=8)

    factory = SQLiteUoWFactory(path)
    await factory.init()
    try:
        semafs = SemaFS(uow_factory=factory, strategy=strategy, max_children=8)

        print("\n1️⃣ 创建分类目录...")
        await ensure_categories(factory)

        print("\n2️⃣ 写入偏好数据并整理（LLM 决策可能较慢）...")
        n = await seed_with_maintain(semafs,
                                     PREFERENCE_FRAGMENTS,
                                     stream=stream)
        print(f"  共写入 {n} 条碎片")

        print("\n3️⃣ 读取结果...")
        for cat_path in ["root.work", "root.personal"]:
            nodes = await semafs.read(cat_path)
            active = [c for c in nodes if c.status == NodeStatus.ACTIVE]
            print(f"  [{cat_path}]: {len(active)} 条")

        print("\n✅ 数据库构建完成\n")
    finally:
        await factory.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="SemaFS 测试数据构建")
    parser.add_argument("--openai", action="store_true", help="使用 OpenAI API")
    parser.add_argument("--db", default=None, help="数据库路径")
    parser.add_argument("--stream", action="store_true", help="流式写入（打乱+随机间隔）")
    parser.add_argument("--export", action="store_true", help="导出数据库到 Markdown 视图")
    parser.add_argument("-o", "--output", default=None, help="导出时的输出文件路径")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(message)s")

    if args.export:
        from semafs.export import export_to_markdown
        db_path = Path(args.db) if args.db else _get_db_path("openai_demo", None)
        if not db_path.exists():
            db_path = _get_db_path("demo", None)
        if not db_path.exists():
            print(f"错误: 数据库不存在: {db_path}", file=sys.stderr)
            sys.exit(1)
        out_path = Path(args.output) if args.output else None
        md = asyncio.run(export_to_markdown(db_path, out_path))
        if not out_path:
            print(md)
        return

    if args.openai:
        asyncio.run(run_openai(db_path=args.db, stream=args.stream))
    else:
        asyncio.run(run_mock(db_path=args.db, stream=args.stream))
    sleep(100)


if __name__ == "__main__":
    main()
