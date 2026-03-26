"""
SemaFS MCP server entrypoint.

Provides:
- FastMCP app factory for SemaFS operations
- `python -m semafs.serve` runnable MCP server (HTTP or stdio)
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
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
from .renderer import JSONRenderer
from .semafs import SemaFS
from .core.node import Node, NodePath


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


logger = logging.getLogger(__name__)


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
            raise RuntimeError(
                "OPENAI_API_KEY is required for provider=openai")

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
            raise RuntimeError(
                "ANTHROPIC_API_KEY is required for provider=anthropic")

        client = AsyncAnthropic(api_key=api_key)
        from .infra.llm.anthropic import AnthropicAdapter

        return AnthropicAdapter(
            client,
            model=config.model or "claude-haiku-4-5-20251001",
        )

    raise RuntimeError(
        "Unsupported provider. Choose one of: openai, anthropic.")


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
        plan_reviewer=LLMPlanReviewer(adapter),
    )
    return Runtime(semafs=semafs, store=store)


def create_mcp_server(config: ServerConfig):
    try:
        from fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "Missing FastMCP dependency. Install with: pip install 'semafs[mcp]'"
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

        leaf_id = await rt.semafs.write(content=content,
                                        hint=hint,
                                        payload=payload)
        leaf = await rt.store.get_by_id(leaf_id)
        timestamps = {}
        if leaf and isinstance(leaf.payload, dict):
            raw_ts = leaf.payload.get("_timestamps", {})
            if isinstance(raw_ts, dict):
                timestamps = {k: v for k, v in raw_ts.items() if v}
        result = {"leaf_id": leaf_id, "timestamps": timestamps}
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
        return {
            "found": True,
            "node": json.loads(JSONRenderer.render_node(view))
        }

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
        return {
            "found": True,
            "tree": json.loads(JSONRenderer.render_tree(tree_view))
        }

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

    @mcp.tool()
    async def create_skeleton_child(
        parent_path: str,
        name: str,
        source: str = "manual",
    ) -> dict:
        """
        Create (or lock) one skeleton child category under a parent path.

        Skeleton categories are name-locked (name_editable=false).
        """
        rt = await get_runtime()

        parent = NodePath(parent_path).value
        child_name = Node.normalize_name(name, fallback_prefix="category")
        child_path = NodePath.from_parent_and_name(parent, child_name).value

        before = await rt.semafs.read(child_path)
        changed = await rt.semafs.apply_skeleton(child_path, source=source)
        after = await rt.semafs.read(child_path)

        if not after:
            raise RuntimeError(
                f"Failed to create or read skeleton node: {child_path}")

        return {
            "path": child_path,
            "created": before is None,
            "changed": changed,
            "skeleton": bool(after.node.skeleton),
            "name_editable": bool(after.node.name_editable),
            "node": json.loads(JSONRenderer.render_node(after)),
        }

    return mcp


@contextmanager
def _temporary_env(updates: dict[str, str]):
    original: dict[str, str | None] = {}
    for key, value in updates.items():
        original[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        yield
    finally:
        for key, previous in original.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


def _configure_fastmcp_settings(
    mcp: object,
    *,
    host: str,
    port: int,
    http_path: str,
) -> None:
    settings = getattr(mcp, "settings", None)
    if settings is None:
        return

    desired = {
        "host": host,
        "port": port,
        "path": http_path,
        "streamable_http_path": http_path,
        "mount_path": http_path,
    }
    for attr, value in desired.items():
        if not hasattr(settings, attr):
            continue
        try:
            setattr(settings, attr, value)
        except Exception:
            continue


def _run_via_run(
    mcp: object,
    *,
    transport: str,
    host: str | None = None,
    port: int | None = None,
    http_path: str | None = None,
) -> None:
    run_fn = getattr(mcp, "run")
    params = inspect.signature(run_fn).parameters
    has_var_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD
                         for p in params.values())

    def accepts(name: str) -> bool:
        return has_var_kwargs or name in params

    kwargs: dict[str, object] = {}
    if accepts("transport"):
        kwargs["transport"] = transport

    if host is not None and accepts("host"):
        kwargs["host"] = host
    if port is not None and accepts("port"):
        kwargs["port"] = port
    if http_path is not None:
        if accepts("path"):
            kwargs["path"] = http_path
        elif accepts("streamable_http_path"):
            kwargs["streamable_http_path"] = http_path
        elif accepts("mount_path"):
            kwargs["mount_path"] = http_path

    if kwargs:
        run_fn(**kwargs)
        return

    # Older FastMCP APIs may only expose positional transport.
    run_fn(transport)


def _run_http_transport(
    mcp: object,
    *,
    host: str,
    port: int,
    http_path: str,
) -> None:
    _configure_fastmcp_settings(mcp, host=host, port=port, http_path=http_path)

    env_updates = {
        "FASTMCP_HOST": host,
        "FASTMCP_PORT": str(port),
        "FASTMCP_PATH": http_path,
        "FASTMCP_HTTP_PATH": http_path,
        "FASTMCP_STREAMABLE_HTTP_PATH": http_path,
    }
    last_error: Exception | None = None
    with _temporary_env(env_updates):
        for transport in ("http", "streamable-http"):
            try:
                _run_via_run(
                    mcp,
                    transport=transport,
                    host=host,
                    port=port,
                    http_path=http_path,
                )
                return
            except ValueError as exc:
                # Different versions recognize different transport tokens.
                message = str(exc).lower()
                if ("unknown transport" in message
                        or "unsupported transport" in message):
                    last_error = exc
                    continue
                raise
            except TypeError as exc:
                # Compatibility path for versions that reject keyword args.
                message = str(exc).lower()
                if "unexpected keyword argument" in message:
                    last_error = exc
                    continue
                raise

    if last_error:
        raise RuntimeError("FastMCP HTTP startup failed for this version. "
                           "Try upgrading fastmcp.") from last_error
    raise RuntimeError("FastMCP HTTP startup failed.")


def _run_sse_transport(mcp: object, *, host: str, port: int) -> None:
    _configure_fastmcp_settings(mcp, host=host, port=port, http_path="/sse")
    env_updates = {
        "FASTMCP_HOST": host,
        "FASTMCP_PORT": str(port),
    }
    with _temporary_env(env_updates):
        _run_via_run(mcp, transport="sse", host=host, port=port)


def run_server(
    db: str = "data/semafs_real_llm.db",
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    placement_max_depth: int = 4,
    placement_min_confidence: float = 0.55,
    transport: str = "http",
    host: str = "127.0.0.1",
    port: int = 8000,
    path: str = "/mcp",
) -> None:
    """Run MCP server over streamable HTTP (default) or stdio."""
    db_path = Path(db).expanduser()
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    db_path = db_path.resolve()

    transport_raw = transport.strip().lower()
    if transport_raw in {"http", "streamable-http", "streamable_http"}:
        resolved_transport = "http"
    elif transport_raw in {"stdio", "sse"}:
        resolved_transport = transport_raw
    else:
        raise RuntimeError(f"Unsupported transport: {transport}. "
                           "Choose one of: http, streamable-http, stdio, sse.")

    http_path = "/" + path.strip().lstrip("/")
    if http_path == "/":
        http_path = "/mcp"

    logger.info(
        "SemaFS MCP server starting (transport=%s)",
        resolved_transport,
    )
    logger.info("Database: %s", db_path)
    logger.info("Provider: %s", provider)
    if model:
        logger.info("Model: %s", model)
    if resolved_transport == "stdio":
        logger.info("No HTTP port is opened in stdio mode.")
        logger.info(
            "Need web UI? Run: semafs view --db %s --host 127.0.0.1 --port 8080",
            db_path,
        )
    elif resolved_transport == "http":
        logger.info(
            "MCP endpoint: http://%s:%s%s",
            host,
            port,
            http_path,
        )
    else:
        logger.info(
            "MCP SSE endpoint: http://%s:%s/sse",
            host,
            port,
        )

    mcp = create_mcp_server(
        ServerConfig(
            db=str(db_path),
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            placement_max_depth=placement_max_depth,
            placement_min_confidence=placement_min_confidence,
        ))
    if resolved_transport == "http":
        _run_http_transport(mcp, host=host, port=port, http_path=http_path)
        return

    if resolved_transport == "sse":
        _run_sse_transport(mcp, host=host, port=port)
        return

    _run_via_run(mcp, transport=resolved_transport)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run SemaFS MCP server")
    parser.add_argument("--db",
                        default="data/semafs_real_llm.db",
                        help="SQLite database path")
    parser.add_argument(
        "--provider",
        choices=("openai", "anthropic"),
        required=True,
        help="LLM provider",
    )
    parser.add_argument("--model",
                        default=None,
                        help="Model name for selected provider")
    parser.add_argument("--api-key",
                        default=None,
                        help="Provider API key (optional, env fallback)")
    parser.add_argument("--base-url",
                        default=None,
                        help="OpenAI-compatible base URL")
    parser.add_argument("--placement-max-depth",
                        type=int,
                        default=4,
                        help="Recursive placement max depth")
    parser.add_argument(
        "--placement-min-confidence",
        type=float,
        default=0.55,
        help="Recursive placement minimum confidence",
    )
    parser.add_argument(
        "--transport",
        choices=("http", "streamable-http", "stdio", "sse"),
        default="http",
        help="MCP transport mode",
    )
    parser.add_argument("--host",
                        default="127.0.0.1",
                        help="Bind host for HTTP/SSE")
    parser.add_argument("--port",
                        type=int,
                        default=8000,
                        help="Bind port for HTTP/SSE")
    parser.add_argument(
        "--path",
        default="/mcp",
        help="Streamable HTTP endpoint path",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="Log level (env fallback: SEMAFS_LOG_LEVEL)",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level, force=True)
    try:
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


if __name__ == "__main__":
    raise SystemExit(main())
