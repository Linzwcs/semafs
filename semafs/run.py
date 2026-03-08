#!/usr/bin/env python3
"""
SemaFS 完整运行示例：使用 LLM 策略进行记忆整理。

支持两种模式：
1. Mock 模式（默认）：无需 API Key，使用 MockLLMAdapter 模拟 LLM 决策
2. OpenAI 模式：设置 OPENAI_API_KEY 环境变量后使用真实 GPT 模型

用法：
    python -m semafs.run                    # Mock 模式
    python -m semafs.run --openai           # OpenAI 模式（需 API Key）
    python -m semafs.run --openai --model gpt-4o  # 指定模型
    python -m semafs.run --stream           # 流式写入：shuffle + 随机间隔，模拟真实场景
    python -m semafs.run --verbose          # 显示插入路径和每个 op 的数据库更新
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from semafs.semafs import SemaFS
from tests.fixtures import PREFERENCE_FRAGMENTS
from semafs.infra.strategies.llm import (
    LLMStrategy,
    MockLLMAdapter,
    OpenAIAdapter,
)
from semafs.models.enums import NodeType
from semafs.models.nodes import TreeNode

try:
    from semafs.infra.repositories.sqlite import SQLiteTreeRepository
except ImportError:
    SQLiteTreeRepository = None  # type: ignore

# ── 测试数据 ─────────────────────────────────────────────────

# 预创建的分类目录（CATEGORY 节点）
TEST_CATEGORIES = [
    ("", "root"),
    ("root", "work"),
    ("root", "personal"),
    ("root", "learning"),
    ("root", "ideas"),
]


async def ensure_categories(repo) -> None:
    """确保测试所需的分类目录存在。path=parent_path.name。"""
    for parent_path, name in TEST_CATEGORIES:
        full = f"{parent_path}.{name}" if parent_path else name
        if parent_path == "" and name == "root":
            continue  # root 由 _ensure_root 创建
        existing = await repo.get_node(full)
        if not existing:
            node = TreeNode(
                parent_path=parent_path,
                name=name,
                node_type=NodeType.CATEGORY,
                content="",
            )
            await repo.add_node(node)
            print(f"  创建分类: {full} ({name})")


async def seed_fragments(semafs: SemaFS) -> int:
    """批量写入偏好类记忆碎片，返回写入数量。"""
    count = 0
    for path, content in PREFERENCE_FRAGMENTS:
        await semafs.write(path, content, {"source": "run_seed"})
        count += 1
        print(f"  📥 写入 [{path}]: {content[:40]}...")
    return count


async def seed_fragments_streamed(
    semafs: SemaFS,
    fragments: list[tuple[str, str]],
    source: str = "stream_seed",
    delay_min: float = 2,
    delay_max: float = 8,
) -> int:
    """流式写入：shuffle 后逐条写入，每条之间随机间隔，模拟真实用户输入。"""
    shuffled = list(fragments)
    random.shuffle(shuffled)
    count = 0
    for path, content in shuffled:
        await semafs.write(path, content, {"source": source})
        count += 1
        print(f"  📥 [{count}/{len(shuffled)}] {path}: {content[:40]}...")
        delay = random.uniform(delay_min, delay_max)
        await asyncio.sleep(delay)
    return count


async def seed_with_maintain(
    semafs: SemaFS,
    fragments: list[tuple[str, str]],
    source: str = "seed",
    stream: bool = False,
    delay_min: float = 0.2,
    delay_max: float = 1.5,
    max_maintain_rounds: int = 20,
) -> int:
    """边 add 边 maintain：逐条写入，每条后执行 maintain 直到无脏目录。"""
    shuffled = list(fragments)
    if stream:
        random.shuffle(shuffled)
    count = 0
    total_maintained = 0
    for path, content in shuffled:
        await semafs.write(path, content, {"source": source})
        count += 1
        print(f"  📥 [{count}/{len(shuffled)}] {path}: {content[:40]}...")
        if stream:
            await asyncio.sleep(random.uniform(delay_min, delay_max))
        # 边 add 边 maintain
        for _ in range(max_maintain_rounds):
            processed = await semafs.maintain()
            if processed == 0:
                break
            total_maintained += processed
            print(f"     🔄 维护 {processed} 个目录，累计 {total_maintained}")
    return count


def _get_db_path(name: str, override: str | None = None) -> Path:
    """默认数据库路径：tests/output/semafs_{name}.db，可通过 override 覆盖"""
    if override:
        return Path(override)
    return Path(__file__).resolve(
    ).parent.parent / "tests" / "output" / f"semafs_{name}.db"


async def run_mock_demo(stream: bool = False,
                        db_path: str | None = None) -> None:
    """使用 Mock LLM 运行完整流程（无需 API）。"""
    if SQLiteTreeRepository is None:
        print("❌ 请安装: pip install aiosqlite")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("SemaFS 运行示例 - Mock LLM 模式（无需 API Key）")
    print("=" * 60)
    path = _get_db_path("demo", db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  数据库: {path}")
    repo = SQLiteTreeRepository(path)
    await repo.init()
    try:
        adapter = MockLLMAdapter()
        strategy = LLMStrategy(adapter, max_leaf_nodes=1)  # 1 个即触发 LLM
        semafs = SemaFS(repo, strategy, db_name="demo")

        print("\n1️⃣ 创建分类目录...")
        await ensure_categories(repo)

        print("\n2️⃣ 边写入边维护" + ("（流式 + 随机间隔）" if stream else "") + "...")
        n = await seed_with_maintain(
            semafs,
            list(PREFERENCE_FRAGMENTS),
            source="run_seed",
            stream=stream,
        )
        print(f"  共写入 {n} 条碎片")

        print("\n3️⃣ 读取 root.work 内容（整理后）...")
        children = await semafs.read("root.work")
        for c in (children or [])[:5]:
            print(f"  {c.path}: {c.content[:60]}...")
        if len(children or []) > 5:
            print(f"  ... 共 {len(children)} 条")

        print("\n✅ Mock 模式演示完成\n")
    finally:
        await repo.close()


async def _run_openai_core(model: str = "gpt-4o-mini",
                           stream: bool = False,
                           db_path: str | None = None):
    """OpenAI 模式核心流程，返回 (repo, semafs)。"""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        print("请安装: pip install openai")
        sys.exit(1)
    if SQLiteTreeRepository is None:
        print("❌ 请安装: pip install aiosqlite")
        sys.exit(1)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("请设置环境变量 OPENAI_API_KEY")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"SemaFS 运行示例 - OpenAI 模式 (model={model})")
    print("=" * 60)
    path = _get_db_path("openai_demo", db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  数据库: {path}")

    # LLM 调用可能较慢，设置 120s 超时避免提前中断；可通过 OPENAI_BASE_URL 覆盖默认 API 地址
    base_url = os.getenv("OPENAI_BASE_URL")
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url if base_url else "http://35.220.164.252:3888/v1",
        timeout=120.0,
    )
    adapter = OpenAIAdapter(client, model=model)
    strategy = LLMStrategy(adapter, max_leaf_nodes=10, max_category_nodes=4)
    repo = SQLiteTreeRepository(path)
    await repo.init()
    try:
        semafs = SemaFS(repo, strategy, db_name="openai_demo")

        print("\n1️⃣ 创建分类目录...")
        await ensure_categories(repo)
        random.shuffle(PREFERENCE_FRAGMENTS)
        print("\n2️⃣ 边写入边维护" + ("（流式 + 随机间隔，模拟真实场景）" if stream else "") +
              "...")
        print("   ⏳ LLM 决策可能较慢，请勿中断...")
        n = await seed_with_maintain(
            semafs,
            PREFERENCE_FRAGMENTS,
            source="openai_seed",
            stream=stream,
            max_maintain_rounds=20,
            delay_min=1,
            delay_max=2,
        )
        print(f"  共写入 {n} 条碎片")

        print("\n3️⃣ 读取整理结果...")
        for cat_path in ["root.work", "root.personal"]:
            children = await semafs.read(cat_path)
            print(f"  [{cat_path}]: {len(children or [])} 条")
            for c in (children or [])[:3]:
                print(f"    - {c.content[:50]}...")

        return repo, semafs
    finally:
        pass


async def run_openai_demo(model: str = "gpt-4o-mini",
                          stream: bool = False,
                          db_path: str | None = None) -> None:
    """使用真实 OpenAI API 运行。"""
    repo, _ = await _run_openai_core(model, stream=stream, db_path=db_path)
    await repo.close()
    print("\n✅ OpenAI 模式演示完成\n")


async def run_openai_with_export(
    model: str = "gpt-4o-mini",
    vault_dir: Path | None = None,
    stream: bool = False,
    db_path: str | None = None,
) -> None:
    """使用真实 LLM 运行并导出 Markdown。"""
    repo, _ = await _run_openai_core(model, stream=stream, db_path=db_path)
    try:
        out = vault_dir or Path(__file__).resolve(
        ).parent.parent / "tests" / "output" / "vault_openai"
        out.mkdir(parents=True, exist_ok=True)

        from semafs.exporter import MarkdownExporter

        exporter = MarkdownExporter(repo, out, only_active=False)
        count = await exporter.export(root_path="root")
        print(f"\n4️⃣ 导出 Markdown: {count} 个文件 -> {out}")
        print("\n✅ OpenAI 模式 + 导出完成\n")
    finally:
        await repo.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="SemaFS 运行示例")
    parser.add_argument(
        "--openai",
        action="store_true",
        help="使用 OpenAI API（需 OPENAI_API_KEY）",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="OpenAI 模型名（默认 gpt-4o-mini）",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="显示插入路径和每个 op 对数据库的更新",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="整理后导出 Markdown 到 tests/output/vault_openai/",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="流式写入：shuffle 数据 + 随机间隔，模拟真实用户输入",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="SQLite 数据库路径（默认 tests/output/semafs_{demo|openai_demo}.db）",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(message)s",
        )
        logging.getLogger("semafs").setLevel(logging.DEBUG)
        logging.getLogger("semafs.infra.repositories.executor").setLevel(
            logging.DEBUG)

    stream = args.stream
    db_path = args.db
    if args.openai:
        if args.export:
            asyncio.run(
                run_openai_with_export(model=args.model,
                                       stream=stream,
                                       db_path=db_path))
        else:
            asyncio.run(
                run_openai_demo(model=args.model,
                                stream=stream,
                                db_path=db_path))
    else:
        asyncio.run(run_mock_demo(stream=stream, db_path=db_path))


if __name__ == "__main__":
    main()
