"""SemaFS unified CLI.

Primary goals:
- Stable command entry (`semafs ...`)
- First-class MCP server command (`semafs serve`)
- Minimal operational commands for local workflows
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

from .algo import (
    DefaultPolicy,
    HybridStrategy,
    LLMPlanReviewer,
    LLMSummarizer,
    LLMRecursivePlacer,
    PlacementConfig,
)
from .infra.bus import InMemoryBus
from .infra.storage.sqlite.store import SQLiteStore
from .infra.storage.sqlite.uow import SQLiteUoWFactory
from .logging_utils import configure_logging
from .renderer import JSONRenderer, TextRenderer
from .semafs import SemaFS
from .view import view as viewer_main

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Runtime:
    semafs: SemaFS
    store: SQLiteStore


def _build_adapter(args: argparse.Namespace):
    if args.provider == "openai":
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI provider requires dependency: pip install 'semafs[openai]'"
            ) from exc
        api_key = args.api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for provider=openai")
        client_kwargs = {"api_key": api_key}
        if args.base_url:
            client_kwargs["base_url"] = args.base_url
        client = AsyncOpenAI(**client_kwargs)
        from .infra.llm.openai import OpenAIAdapter

        return OpenAIAdapter(client, model=args.model or "gpt-4o-mini")

    if args.provider == "anthropic":
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise RuntimeError(
                "Anthropic provider requires dependency: pip install 'semafs[anthropic]'"
            ) from exc
        api_key = args.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is required for provider=anthropic")
        client = AsyncAnthropic(api_key=api_key)
        from .infra.llm.anthropic import AnthropicAdapter

        return AnthropicAdapter(
            client,
            model=args.model or "claude-haiku-4-5-20251001",
        )

    raise RuntimeError(
        "Unsupported provider. Choose one of: openai, anthropic."
    )


async def build_runtime(args: argparse.Namespace) -> Runtime:
    store = SQLiteStore(args.db)
    factory = SQLiteUoWFactory(store)
    await factory.init()

    bus = InMemoryBus()
    policy = DefaultPolicy()

    adapter = _build_adapter(args)
    placer = LLMRecursivePlacer(
        store=store,
        adapter=adapter,
        config=PlacementConfig(
            max_depth=args.placement_max_depth,
            min_confidence=args.placement_min_confidence,
        ),
    )
    strategy = HybridStrategy(adapter)
    summarizer = LLMSummarizer(adapter)

    semafs = SemaFS(
        store=store,
        uow_factory=factory,
        bus=bus,
        strategy=strategy,
        placer=placer,
        summarizer=summarizer,
        policy=policy,
        plan_reviewer=LLMPlanReviewer(adapter),
    )
    return Runtime(semafs=semafs, store=store)


async def _cmd_write(args: argparse.Namespace) -> int:
    runtime = await build_runtime(args)
    payload = None
    if args.payload:
        payload = json.loads(args.payload)
    leaf_id = await runtime.semafs.write(
        content=args.content,
        hint=args.hint,
        payload=payload,
    )
    leaf = await runtime.store.get_by_id(leaf_id)
    written_at = None
    event_at = None
    if leaf and isinstance(leaf.payload, dict):
        ts = leaf.payload.get("_timestamps", {})
        if isinstance(ts, dict):
            written_at = ts.get("written_at")
            event_at = ts.get("event_at")
    logger.info(
        "write.result=%s",
        json.dumps(
            {
                "leaf_id": leaf_id,
                "written_at": written_at,
                "event_at": event_at,
            },
            ensure_ascii=False,
        ),
    )
    if args.sweep:
        changed = await runtime.semafs.sweep(limit=args.sweep_limit)
        logger.info("sweep.changed=%s", changed)
    return 0


async def _cmd_read(args: argparse.Namespace) -> int:
    runtime = await build_runtime(args)
    view = await runtime.semafs.read(args.path)
    if not view:
        logger.warning("read.not_found path=%s", args.path)
        return 1
    if args.output == "json":
        logger.info("%s", JSONRenderer.render_node(view))
    else:
        logger.info("%s", TextRenderer.render_node(view))
    return 0


async def _cmd_list(args: argparse.Namespace) -> int:
    runtime = await build_runtime(args)
    views = await runtime.semafs.list(args.path)
    if args.output == "json":
        logger.info(
            "%s",
            json.dumps([v.path for v in views], ensure_ascii=False, indent=2),
        )
    else:
        for view in views:
            logger.info("%s", view.path)
    return 0


async def _cmd_tree(args: argparse.Namespace) -> int:
    runtime = await build_runtime(args)
    tree = await runtime.semafs.tree(path=args.path, max_depth=args.max_depth)
    if not tree:
        logger.warning("tree.not_found path=%s", args.path)
        return 1
    if args.output == "json":
        logger.info("%s", JSONRenderer.render_tree(tree))
    else:
        logger.info(
            "%s",
            TextRenderer.render_tree(tree, show_content=args.show_content),
        )
    return 0


async def _cmd_stats(args: argparse.Namespace) -> int:
    runtime = await build_runtime(args)
    stats = await runtime.semafs.stats()
    if args.output == "json":
        logger.info("%s", JSONRenderer.render_stats(stats))
    else:
        logger.info("%s", TextRenderer.render_stats(stats))
    return 0


async def _cmd_sweep(args: argparse.Namespace) -> int:
    runtime = await build_runtime(args)
    changed = await runtime.semafs.sweep(limit=args.limit)
    logger.info("sweep.changed=%s", changed)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SemaFS command line interface")
    parser.add_argument(
        "--log-level",
        default=None,
        help="Log level (env fallback: SEMAFS_LOG_LEVEL)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_runtime_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--db",
                       default="data/semafs_real_llm.db",
                       help="SQLite database path")
        p.add_argument(
            "--provider",
            choices=("openai", "anthropic"),
            required=True,
            help="LLM provider",
        )
        p.add_argument("--model",
                       default=None,
                       help="Model name for selected provider")
        p.add_argument("--api-key",
                       default=None,
                       help="Provider API key (optional, env fallback)")
        p.add_argument("--base-url",
                       default=None,
                       help="OpenAI-compatible base URL")
        p.add_argument("--placement-max-depth",
                       type=int,
                       default=4,
                       help="Recursive placement max depth")
        p.add_argument(
            "--placement-min-confidence",
            type=float,
            default=0.55,
            help="Recursive placement minimum confidence",
        )

    # serve
    p_serve = sub.add_parser("serve", help="Run MCP server over HTTP or stdio")
    add_runtime_common(p_serve)
    p_serve.add_argument(
        "--transport",
        choices=("http", "streamable-http", "stdio", "sse"),
        default="http",
        help="MCP transport mode",
    )
    p_serve.add_argument("--host", default="127.0.0.1", help="Bind host for HTTP/SSE")
    p_serve.add_argument("--port", type=int, default=8000, help="Bind port for HTTP/SSE")
    p_serve.add_argument(
        "--path",
        default="/mcp",
        help="Streamable HTTP endpoint path",
    )

    # view
    p_view = sub.add_parser("view", help="Run viewer server")
    p_view.add_argument("--db",
                        default="data/semafs_real_llm.db",
                        help="SQLite database path")
    p_view.add_argument("--host", default="127.0.0.1", help="Server host")
    p_view.add_argument("--port", type=int, default=8080, help="Server port")
    p_view.add_argument("--reload",
                        action="store_true",
                        help="Enable autoreload")

    # write
    p_write = sub.add_parser("write", help="Write one content fragment")
    add_runtime_common(p_write)
    p_write.add_argument("content", help="Fragment content")
    p_write.add_argument("--hint",
                         default=None,
                         help="Optional placement start path")
    p_write.add_argument("--payload", default=None, help="JSON payload string")
    p_write.add_argument("--sweep",
                         action="store_true",
                         help="Run one sweep after write")
    p_write.add_argument("--sweep-limit",
                         type=int,
                         default=None,
                         help="Sweep category limit")

    # read/list/tree/stats/sweep
    p_read = sub.add_parser("read", help="Read one node by canonical path")
    add_runtime_common(p_read)
    p_read.add_argument("path", help="Canonical path (e.g. root.work)")
    p_read.add_argument("--output", choices=("text", "json"), default="text")

    p_list = sub.add_parser("list", help="List direct children by path")
    add_runtime_common(p_list)
    p_list.add_argument("path", help="Canonical path")
    p_list.add_argument("--output", choices=("text", "json"), default="text")

    p_tree = sub.add_parser("tree", help="Render tree by path")
    add_runtime_common(p_tree)
    p_tree.add_argument("path",
                        nargs="?",
                        default="root",
                        help="Canonical path")
    p_tree.add_argument("--max-depth",
                        type=int,
                        default=3,
                        help="Maximum tree depth")
    p_tree.add_argument("--show-content",
                        action="store_true",
                        help="Show leaf content preview")
    p_tree.add_argument("--output", choices=("text", "json"), default="text")

    p_stats = sub.add_parser("stats", help="Show knowledge base statistics")
    add_runtime_common(p_stats)
    p_stats.add_argument("--output", choices=("text", "json"), default="text")

    p_sweep = sub.add_parser("sweep", help="Run one maintenance sweep")
    add_runtime_common(p_sweep)
    p_sweep.add_argument("--limit",
                         type=int,
                         default=None,
                         help="Max categories to process")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level, force=True)

    if args.command == "serve":
        try:
            from .serve import run_server

            run_server(
                db=args.db,
                provider=args.provider,
                model=args.model,
                api_key=args.api_key,
                base_url=args.base_url,
                placement_max_depth=args.placement_max_depth,
                placement_min_confidence=args.placement_min_confidence,
                transport=args.transport,
                host=args.host,
                port=args.port,
                path=args.path,
            )
        except Exception as exc:  # pragma: no cover - CLI error path
            logger.error("Error: %s", exc)
            return 1
        return 0

    if args.command == "view":
        return viewer_main([
            "--db",
            args.db,
            "--host",
            args.host,
            "--port",
            str(args.port),
            *(["--reload"] if args.reload else []),
        ])

    try:
        if args.command == "write":
            return asyncio.run(_cmd_write(args))
        if args.command == "read":
            return asyncio.run(_cmd_read(args))
        if args.command == "list":
            return asyncio.run(_cmd_list(args))
        if args.command == "tree":
            return asyncio.run(_cmd_tree(args))
        if args.command == "stats":
            return asyncio.run(_cmd_stats(args))
        if args.command == "sweep":
            return asyncio.run(_cmd_sweep(args))
    except Exception as exc:  # pragma: no cover - CLI error path
        logger.error("Error: %s", exc)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
