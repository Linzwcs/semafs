from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from semafs import __version__
from semafs.core.enums import NodeStatus
from semafs.core.node import NodePath, TreeNode
from semafs.semafs import SemaFS
from semafs.storage.sqlite.factory import SQLiteUoWFactory
from semafs.strategies.rule import RuleOnlyStrategy

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


async def cmd_init(args: argparse.Namespace) -> None:
    """Initialize a new SemaFS database."""
    db_path = Path(args.db)
    if db_path.exists() and not args.force:
        print(f"Error: Database already exists: {db_path}", file=sys.stderr)
        print("Use --force to overwrite", file=sys.stderr)
        sys.exit(1)

    db_path.parent.mkdir(parents=True, exist_ok=True)

    factory = SQLiteUoWFactory(db_path)
    await factory.init()

    print(f"✓ Initialized SemaFS database: {db_path}")

    # Create default categories if requested
    if args.categories:
        categories = args.categories.split(',')
        for cat_name in categories:
            cat_name = cat_name.strip()
            if not cat_name:
                continue
            async with factory.begin() as uow:
                cat = TreeNode.new_category(
                    path=NodePath(f"root.{cat_name}"),
                    content="",
                    display_name=cat_name,
                )
                uow.register_new(cat)
                await uow.commit()
            print(f"  Created category: root.{cat_name}")

    await factory.close()


async def cmd_write(args: argparse.Namespace) -> None:
    """Write a fragment to a category."""
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        print("Run 'semafs init' first", file=sys.stderr)
        sys.exit(1)

    # Read content from stdin or argument
    if args.content == '-':
        content = sys.stdin.read().strip()
    else:
        content = args.content

    if not content:
        print("Error: No content provided", file=sys.stderr)
        sys.exit(1)

    factory = SQLiteUoWFactory(db_path)
    await factory.init()

    try:
        strategy = RuleOnlyStrategy()
        semafs = SemaFS(uow_factory=factory, strategy=strategy)

        payload = {}
        if args.tags:
            payload['tags'] = args.tags.split(',')
        if args.source:
            payload['source'] = args.source

        frag_id = await semafs.write(args.path, content, payload)
        print(f"✓ Written fragment {frag_id[:8]} to {args.path}")

        # Auto-maintain if requested
        if args.maintain:
            processed = await semafs.maintain()
            if processed > 0:
                print(f"✓ Maintained {processed} categories")

    finally:
        await factory.close()


async def cmd_maintain(args: argparse.Namespace) -> None:
    """Run maintenance to reorganize fragments."""
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    factory = SQLiteUoWFactory(db_path)
    await factory.init()

    try:
        # Determine strategy based on mode
        if args.llm == 'openai':
            try:
                from openai import AsyncOpenAI
                from semafs.infra.llm.openai import OpenAIAdapter
                from semafs.strategies.hybrid import HybridStrategy
            except ImportError:
                print(
                    "Error: Install openai package: pip install 'semafs[openai]'",
                    file=sys.stderr)
                sys.exit(1)

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                print("Error: Set OPENAI_API_KEY environment variable",
                      file=sys.stderr)
                sys.exit(1)

            client = AsyncOpenAI(api_key=api_key, timeout=120.0)
            adapter = OpenAIAdapter(client, model=args.model or "gpt-4o-mini")
            strategy = HybridStrategy(adapter, max_nodes=args.max_nodes)

        elif args.llm == 'anthropic':
            try:
                from anthropic import AsyncAnthropic
                from semafs.infra.llm.anthropic import AnthropicAdapter
                from semafs.strategies.hybrid import HybridStrategy
            except ImportError:
                print(
                    "Error: Install anthropic package: pip install 'semafs[anthropic]'",
                    file=sys.stderr)
                sys.exit(1)

            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                print("Error: Set ANTHROPIC_API_KEY environment variable",
                      file=sys.stderr)
                sys.exit(1)

            client = AsyncAnthropic(api_key=api_key, timeout=120.0)
            adapter = AnthropicAdapter(client,
                                       model=args.model
                                       or "claude-3-haiku-20240307")
            strategy = HybridStrategy(adapter, max_nodes=args.max_nodes)

        else:
            strategy = RuleOnlyStrategy()

        semafs = SemaFS(uow_factory=factory,
                        strategy=strategy,
                        max_children=args.max_children)

        rounds = 0
        total_processed = 0
        max_rounds = args.rounds

        print(f"Running maintenance (max {max_rounds} rounds)...")

        while rounds < max_rounds:
            rounds += 1
            processed = await semafs.maintain()
            total_processed += processed

            if processed == 0:
                print(
                    f"✓ Completed in {rounds} rounds, processed {total_processed} categories"
                )
                break

            print(f"  Round {rounds}: processed {processed} categories")

        if rounds >= max_rounds:
            print(
                f"! Stopped after {max_rounds} rounds, processed {total_processed} categories"
            )

    finally:
        await factory.close()


async def cmd_list(args: argparse.Namespace) -> None:
    """List nodes in a category."""
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    factory = SQLiteUoWFactory(db_path)
    await factory.init()

    try:
        strategy = RuleOnlyStrategy()
        semafs = SemaFS(uow_factory=factory, strategy=strategy)

        nodes = await semafs.list(args.path, include_archived=args.archived)

        if not nodes:
            print(f"No nodes found in {args.path}")
            return

        print(f"\n{args.path} ({len(nodes)} nodes):")
        print("─" * 60)

        for view in nodes:
            node = view.node
            status_icon = {
                NodeStatus.ACTIVE: "✓",
                NodeStatus.PENDING_REVIEW: "⏳",
                NodeStatus.PROCESSING: "⚙️",
                NodeStatus.ARCHIVED: "📦",
            }.get(node.status, "?")

            content_preview = node.content[:50] + "..." if len(
                node.content) > 50 else node.content
            print(f"{status_icon} {node.path}")
            print(f"  {content_preview}")
            if args.verbose and node.payload:
                print(f"  payload: {node.payload}")
            print()

    finally:
        await factory.close()


async def cmd_read(args: argparse.Namespace) -> None:
    """Read a specific node."""
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    factory = SQLiteUoWFactory(db_path)
    await factory.init()

    try:
        strategy = RuleOnlyStrategy()
        semafs = SemaFS(uow_factory=factory, strategy=strategy)

        view = await semafs.read(args.path)

        if not view:
            print(f"Error: Node not found: {args.path}", file=sys.stderr)
            sys.exit(1)

        node = view.node

        print("\n" + "=" * 60)
        print(f"Path: {node.path}")
        print(f"Type: {node.node_type.value}")
        print(f"Status: {node.status.value}")
        print(f"Breadcrumb: {' > '.join(view.breadcrumb)}")
        print(f"Children: {view.child_count}")
        print("=" * 60)
        print()
        print(node.content)
        print()

        if args.verbose and node.payload:
            print("Payload:")
            for key, value in node.payload.items():
                print(f"  {key}: {value}")
            print()

    finally:
        await factory.close()


async def cmd_export(args: argparse.Namespace) -> None:
    """Export database to various formats."""
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    from semafs.export import export_to_markdown

    output_path = Path(args.output) if args.output else None

    md = await export_to_markdown(db_path, output_path)

    if not output_path:
        print(md)
    else:
        print(f"✓ Exported to {output_path}")


async def cmd_stats(args: argparse.Namespace) -> None:
    """Show database statistics."""
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    factory = SQLiteUoWFactory(db_path)
    await factory.init()

    try:
        strategy = RuleOnlyStrategy()
        semafs = SemaFS(uow_factory=factory, strategy=strategy)

        stats = await semafs.stats()

        print("\n" + "=" * 60)
        print("SemaFS Statistics")
        print("=" * 60)
        print(f"Total nodes: {stats.total_nodes}")
        print(f"  Categories: {stats.category_count}")
        print(f"  Leaves: {stats.leaf_count}")
        print()
        print(f"By status:")
        print(f"  Active: {stats.active_count}")
        print(f"  Pending: {stats.pending_count}")
        print(f"  Archived: {stats.archived_count}")
        print()
        print(f"Dirty categories: {stats.dirty_count}")
        print(f"Tree depth: {stats.max_depth}")
        print("=" * 60)
        print()

    finally:
        await factory.close()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description=f"SemaFS v{__version__} - Semantic Filesystem",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument('--version',
                        action='version',
                        version=f'semafs {__version__}')
    parser.add_argument('-v',
                        '--verbose',
                        action='store_true',
                        help='Verbose output')

    subparsers = parser.add_subparsers(dest='command',
                                       help='Available commands')

    # init command
    init_parser = subparsers.add_parser(
        'init', help='Initialize a new SemaFS database')
    init_parser.add_argument('db', help='Database path')
    init_parser.add_argument('--force',
                             action='store_true',
                             help='Overwrite existing database')
    init_parser.add_argument('--categories',
                             help='Comma-separated list of initial categories')

    # write command
    write_parser = subparsers.add_parser('write',
                                         help='Write a fragment to a category')
    write_parser.add_argument('db', help='Database path')
    write_parser.add_argument('path', help='Target category path')
    write_parser.add_argument(
        'content', help='Fragment content (use "-" to read from stdin)')
    write_parser.add_argument('--tags', help='Comma-separated tags')
    write_parser.add_argument('--source', help='Source identifier')
    write_parser.add_argument('--maintain',
                              action='store_true',
                              help='Run maintenance after writing')

    # maintain command
    maintain_parser = subparsers.add_parser(
        'maintain', help='Run maintenance to reorganize fragments')
    maintain_parser.add_argument('db', help='Database path')
    maintain_parser.add_argument('--llm',
                                 choices=['rule', 'openai', 'anthropic'],
                                 default='rule',
                                 help='LLM strategy')
    maintain_parser.add_argument('--model', help='LLM model name')
    maintain_parser.add_argument('--max-children',
                                 type=int,
                                 default=10,
                                 help='Max children before reorganization')
    maintain_parser.add_argument('--max-nodes',
                                 type=int,
                                 default=8,
                                 help='Max nodes for LLM strategy')
    maintain_parser.add_argument('--rounds',
                                 type=int,
                                 default=20,
                                 help='Maximum maintenance rounds')

    # list command
    list_parser = subparsers.add_parser('list',
                                        help='List nodes in a category')
    list_parser.add_argument('db', help='Database path')
    list_parser.add_argument('path', help='Category path')
    list_parser.add_argument('--archived',
                             action='store_true',
                             help='Include archived nodes')

    # read command
    read_parser = subparsers.add_parser('read', help='Read a specific node')
    read_parser.add_argument('db', help='Database path')
    read_parser.add_argument('path', help='Node path')

    # export command
    export_parser = subparsers.add_parser('export',
                                          help='Export database to markdown')
    export_parser.add_argument('db', help='Database path')
    export_parser.add_argument('-o',
                               '--output',
                               help='Output file (default: stdout)')

    # stats command
    stats_parser = subparsers.add_parser('stats',
                                         help='Show database statistics')
    stats_parser.add_argument('db', help='Database path')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    setup_logging(args.verbose)

    # Route to command handlers
    commands = {
        'init': cmd_init,
        'write': cmd_write,
        'maintain': cmd_maintain,
        'list': cmd_list,
        'read': cmd_read,
        'export': cmd_export,
        'stats': cmd_stats,
    }

    try:
        asyncio.run(commands[args.command](args))
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        if args.verbose:
            raise
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
