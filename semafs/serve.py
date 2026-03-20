"""SemaFS MCP server entrypoint.

Provides:
- FastMCP app factory for SemaFS operations
- `python -m semafs.serve` runnable MCP stdio server
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .algo import (
    DefaultPolicy,
    HybridStrategy,
    LLMSummarizer,
    LLMRecursivePlacer,
    PlacementConfig,
)
from .infra.bus import InMemoryBus
from .infra.storage.sqlite.store import SQLiteStore
from .infra.storage.sqlite.uow import SQLiteUoWFactory
from .renderer import JSONRenderer
from .semafs import SemaFS


@dataclass(frozen=True)
class Runtime:
    semafs: SemaFS
    store: SQLiteStore


@dataclass(frozen=True)
class ServerConfig:
    db: str = "data/semafs_real_llm.db"
    provider: str = "openai"
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    placement_max_depth: int = 4
    placement_min_confidence: float = 0.55


def _build_adapter(config: ServerConfig):
    if config.provider == "openai":
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI provider requires dependency: pip install 'semafs[openai]'"
            ) from exc
        api_key = config.api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for provider=openai")

        client_kwargs: dict[str, str] = {"api_key": api_key}
        if config.base_url:
            client_kwargs["base_url"] = config.base_url

        client = AsyncOpenAI(**client_kwargs)
        from .infra.llm.openai import OpenAIAdapter

        return OpenAIAdapter(client, model=config.model or "gpt-4o-mini")

    if config.provider == "anthropic":
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise RuntimeError(
                "Anthropic provider requires dependency: pip install 'semafs[anthropic]'"
            ) from exc
        api_key = config.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for provider=anthropic")

        client = AsyncAnthropic(api_key=api_key)
        from .infra.llm.anthropic import AnthropicAdapter

        return AnthropicAdapter(
            client,
            model=config.model or "claude-haiku-4-5-20251001",
        )

    raise RuntimeError("Unsupported provider. Choose one of: openai, anthropic.")


async def build_runtime(config: ServerConfig) -> Runtime:
    db_path = Path(config.db)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    store = SQLiteStore(str(db_path))
    factory = SQLiteUoWFactory(store)
    await factory.init()

    adapter = _build_adapter(config)
    semafs = SemaFS(
        store=store,
        uow_factory=factory,
        bus=InMemoryBus(),
        strategy=HybridStrategy(adapter),
        placer=LLMRecursivePlacer(
            store=store,
            adapter=adapter,
            config=PlacementConfig(
                max_depth=config.placement_max_depth,
                min_confidence=config.placement_min_confidence,
            ),
        ),
        summarizer=LLMSummarizer(adapter),
        policy=DefaultPolicy(),
    )
    return Runtime(semafs=semafs, store=store)


def create_mcp_server(config: ServerConfig):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "Missing MCP dependency. Install with: pip install 'semafs[mcp]'"
        ) from exc

    mcp = FastMCP("SemaFS")
    runtime: Runtime | None = None
    runtime_lock = asyncio.Lock()

    async def get_runtime() -> Runtime:
        nonlocal runtime
        if runtime is not None:
            return runtime
        async with runtime_lock:
            if runtime is None:
                runtime = await build_runtime(config)
        return runtime

    @mcp.tool()
    async def write(
        content: str,
        hint: str | None = None,
        payload_json: str | None = None,
        sweep: bool = False,
        sweep_limit: int | None = None,
    ) -> dict:
        """Write a content fragment into SemaFS and optionally run one sweep."""
        rt = await get_runtime()
        payload = None
        if payload_json:
            payload = json.loads(payload_json)

        leaf_id = await rt.semafs.write(content=content, hint=hint, payload=payload)
        result = {"leaf_id": leaf_id}
        if sweep:
            result["sweep_changed"] = await rt.semafs.sweep(limit=sweep_limit)
        return result

    @mcp.tool()
    async def read(path: str) -> dict:
        """Read one node by canonical path."""
        rt = await get_runtime()
        view = await rt.semafs.read(path)
        if not view:
            return {"found": False, "path": path}
        return {"found": True, "node": json.loads(JSONRenderer.render_node(view))}

    @mcp.tool()
    async def list(path: str) -> dict:
        """List direct children under a canonical path."""
        rt = await get_runtime()
        views = await rt.semafs.list(path)
        return {
            "path": path,
            "total": len(views),
            "items": [json.loads(JSONRenderer.render_node(v)) for v in views],
        }

    @mcp.tool()
    async def tree(path: str = "root", max_depth: int = 3) -> dict:
        """Return a recursive tree snapshot from a path."""
        rt = await get_runtime()
        tree_view = await rt.semafs.tree(path=path, max_depth=max_depth)
        if not tree_view:
            return {"found": False, "path": path}
        return {"found": True, "tree": json.loads(JSONRenderer.render_tree(tree_view))}

    @mcp.tool()
    async def stats() -> dict:
        """Return SemaFS aggregate statistics."""
        rt = await get_runtime()
        stats_view = await rt.semafs.stats()
        return json.loads(JSONRenderer.render_stats(stats_view))

    @mcp.tool()
    async def sweep(limit: int | None = None) -> dict:
        """Run one maintenance sweep and return changed category count."""
        rt = await get_runtime()
        changed = await rt.semafs.sweep(limit=limit)
        return {"changed": changed}

    return mcp


def run_server(
    db: str = "data/semafs_real_llm.db",
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    placement_max_depth: int = 4,
    placement_min_confidence: float = 0.55,
) -> None:
    """Run MCP server over stdio."""
    mcp = create_mcp_server(
        ServerConfig(
            db=db,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            placement_max_depth=placement_max_depth,
            placement_min_confidence=placement_min_confidence,
        )
    )
    mcp.run(transport="stdio")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run SemaFS MCP server")
    parser.add_argument("--db", default="data/semafs_real_llm.db", help="SQLite database path")
    parser.add_argument(
        "--provider",
        choices=("openai", "anthropic"),
        required=True,
        help="LLM provider",
    )
    parser.add_argument("--model", default=None, help="Model name for selected provider")
    parser.add_argument("--api-key", default=None, help="Provider API key (optional, env fallback)")
    parser.add_argument("--base-url", default=None, help="OpenAI-compatible base URL")
    parser.add_argument("--placement-max-depth", type=int, default=4, help="Recursive placement max depth")
    parser.add_argument(
        "--placement-min-confidence",
        type=float,
        default=0.55,
        help="Recursive placement minimum confidence",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        run_server(
            db=args.db,
            provider=args.provider,
            model=args.model,
            api_key=args.api_key,
            base_url=args.base_url,
            placement_max_depth=args.placement_max_depth,
            placement_min_confidence=args.placement_min_confidence,
        )
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"Error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
