"""
Export SemaFS database to Markdown view.

Reference semafs/exporter.py implementation. Supports three export modes:
1. MarkdownExporter: Each CATEGORY exported as a separate .md file (flat directory)
2. TreeStructureExporter: Export folder structure only
3. TreeTextView: Output text tree view to stdout only

Usage:
    python -m semafs.export --db ./mydb.db
    python -m semafs.export --db ./mydb.db --out vault
    python -m semafs.export --db ./mydb.db --tree
    python -m semafs.export --db ./mydb.db --print
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from semafs.core.enums import NodeStatus, NodeType
from semafs.core.node import TreeNode
from semafs.storage.sqlite.factory import SQLiteUoWFactory

logger = logging.getLogger(__name__)

_NOW = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _node_meta_block(
    node_type: str,
    path: str,
    status: str,
    node_id: str = "",
    version: int = 1,
    created_at: str = "",
    updated_at: str = "",
    name: str = "",
) -> str:
    """Node metadata block for parsing and identification."""
    parts = [f"类型: {node_type}", f"路径: {path}", f"状态: {status}"]
    if node_id:
        parts.append(f"ID: {node_id}")
    if version:
        parts.append(f"版本: v{version}")
    if created_at:
        parts.append(f"创建: {created_at}")
    if updated_at:
        parts.append(f"更新: {updated_at}")
    if name:
        parts.append(f"名称: {name}")
    return " | ".join(parts)


def _leaf_section(node: TreeNode, idx: int) -> str:
    """Render a single leaf node as an independent block with full metadata."""
    slug = node.path.rsplit(".", 1)[-1]
    meta = _node_meta_block(
        node_type="LEAF",
        path=node.path,
        status=node.status.value,
        node_id=node.id,
        version=node.version,
        created_at=node.created_at.strftime("%Y-%m-%d %H:%M"),
        updated_at=node.updated_at.strftime("%Y-%m-%d %H:%M"),
        name=node.display_name or node.name or slug,
    )
    lines = [
        "",
        "---",
        "",
        f"### 节点 {idx} · {slug}",
        "",
        f"<!-- {meta} -->",
        "",
        node.content or "_(空)_",
        "",
    ]
    if node.tags:
        lines += ["**标签:** " + "  ".join(f"`{t}`" for t in node.tags), ""]
    if node.status == NodeStatus.PENDING_REVIEW or node.payload.get("_auto"):
        lines += ["**来源:** 待整理碎片", ""]
    lines += [
        f"<sub>{meta}</sub>",
        "",
    ]
    return "\n".join(lines)


def _sub_category_entry(cat: TreeNode, fname: str) -> str:
    """Sub-category entry with type and path."""
    name = cat.display_name or cat.name or cat.path.rsplit(".", 1)[-1]
    meta = _node_meta_block(
        node_type="CATEGORY",
        path=cat.path,
        status=cat.status.value,
        node_id=cat.id,
        version=cat.version,
        updated_at=cat.updated_at.strftime("%Y-%m-%d %H:%M"),
        name=name,
    )
    return f"- 📁 [{name}](./{fname})  `{cat.path}`"


def _render_category(
    node: TreeNode,
    leaves: List[TreeNode],
    sub_categories: List[TreeNode],
) -> str:
    label = node.display_name or node.name or node.path.rsplit(".", 1)[-1]
    depth = node.path.count(".") + 1
    heading = "#" * min(depth, 3)

    cat_meta = _node_meta_block(
        node_type="CATEGORY",
        path=node.path,
        status=node.status.value,
        node_id=node.id,
        version=node.version,
        created_at=node.created_at.strftime("%Y-%m-%d %H:%M"),
        updated_at=node.updated_at.strftime("%Y-%m-%d %H:%M"),
        name=label,
    )

    lines = [
        "---",
        "",
        f"{heading} {label}",
        "",
        f"<!-- {cat_meta} -->",
        "",
        f"<sub>{cat_meta}</sub>",
        "",
    ]

    if node.content:
        lines += ["**摘要:**", "", node.content, "", "---", ""]

    if sub_categories:
        lines += ["## 子目录 (CATEGORY)", ""]
        for c in sorted(sub_categories, key=lambda x: x.path):
            fname = _category_filename(c.path)
            lines.append(_sub_category_entry(c, fname))
        lines += ["", "---", ""]

    active = [n for n in leaves if n.status == NodeStatus.ACTIVE]
    pending = [n for n in leaves if n.status == NodeStatus.PENDING_REVIEW]

    if active:
        lines += ["## 内容 (LEAF)", ""]
        for i, leaf in enumerate(
                sorted(active, key=lambda x: x.updated_at, reverse=True), 1):
            lines.append(_leaf_section(leaf, i))

    if pending:
        lines += ["## ⏳ 待整理 (LEAF)", ""]
        for i, leaf in enumerate(sorted(pending, key=lambda x: x.created_at),
                                 1):
            lines.append(_leaf_section(leaf, i))

    lines += ["---", "", f"<sub>导出于 {_NOW()}</sub>", ""]
    return "\n".join(lines)


def _category_filename(path: str) -> str:
    """root → root.md, root.work → root.work.md"""
    return path + ".md"


def _path_to_dir(path: str) -> str:
    """root → root/, root.work.personal → root/work/personal/"""
    if not path or path == "root":
        return "root"
    return path.replace(".", "/")


def _segment_name(path: str) -> str:
    """root.work.personal → personal"""
    if not path or path == "root":
        return "root"
    return path.rsplit(".", 1)[-1]


class TreeTextView:
    """
    Output text tree view only, without creating any files or directories.
    Output to stdout, format example:
      root
      ├── personal
      │   ├── diet_health
      │   └── fitness
      └── work
    """

    def __init__(self, repo) -> None:
        self._repo = repo
        self._lines: List[str] = []

    async def export(self, root_path: str = "root") -> str:
        """Return tree text."""
        self._lines = []
        await self._visit(root_path, "", True, is_root=True)
        return "\n".join(self._lines)

    async def _visit(
        self,
        path: str,
        prefix: str,
        is_last: bool,
        is_root: bool = False,
    ) -> None:
        node = await self._repo.get_by_path(path)
        if not node or node.status == NodeStatus.ARCHIVED:
            return
        if node.node_type != NodeType.CATEGORY:
            return

        statuses = [
            NodeStatus.ACTIVE,
            NodeStatus.PENDING_REVIEW,
            NodeStatus.PROCESSING,
        ]
        all_children = await self._repo.list_children(path, statuses=statuses)
        sub_cats = sorted(
            [c for c in all_children if c.node_type == NodeType.CATEGORY],
            key=lambda x: x.path,
        )

        name = _segment_name(path)
        if is_root:
            self._lines.append(name)
        else:
            connector = "└── " if is_last else "├── "
            self._lines.append(prefix + connector + name)

        child_prefix = (prefix +
                        ("    " if is_last else "│   ") if not is_root else "")
        for i, sub in enumerate(sub_cats):
            await self._visit(
                sub.path,
                child_prefix,
                i == len(sub_cats) - 1,
                is_root=False,
            )


class TreeStructureExporter:
    """
    Export folder structure only, without generating markdown files.
    Create directory structure under output_dir matching path, e.g. root/work/personal/.
    """

    def __init__(self, repo, output_dir: str | Path = "tree") -> None:
        self._repo = repo
        self._out = Path(output_dir)
        self._created = 0

    async def export(self, root_path: str = "root") -> int:
        """Export directory structure from root_path, return number of directories created."""
        self._created = 0
        await self._visit(root_path)
        logger.info(f"📁 导出完成：{self._created} 个目录 → {self._out}/")
        return self._created

    async def _visit(self, path: str) -> None:
        node = await self._repo.get_by_path(path)
        if not node or node.status == NodeStatus.ARCHIVED:
            return
        if node.node_type != NodeType.CATEGORY:
            return

        statuses = [
            NodeStatus.ACTIVE,
            NodeStatus.PENDING_REVIEW,
            NodeStatus.PROCESSING,
        ]
        all_children = await self._repo.list_children(path, statuses=statuses)
        sub_cats = [
            c for c in all_children if c.node_type == NodeType.CATEGORY
        ]

        dir_path = self._out / _path_to_dir(path)
        dir_path.mkdir(parents=True, exist_ok=True)
        self._created += 1
        logger.debug(f"  📁 {dir_path}")

        for sub in sub_cats:
            await self._visit(sub.path)


class MarkdownExporter:
    """
    Export each CATEGORY node as a .md file (flat directory, no subfolders).
    Leaf node content is inlined in the parent category file.

    Args:
        repo:        NodeRepository implementation
        output_dir:  Export directory (default "vault")
        only_active: When True, export ACTIVE nodes only (default False, full export includes PENDING/PROCESSING)
    """

    def __init__(
        self,
        repo,
        output_dir: str | Path = "vault",
        *,
        only_active: bool = False,
    ) -> None:
        self._repo = repo
        self._out = Path(output_dir)
        self._only_active = only_active
        self._written = 0

    async def export(self, root_path: str = "root") -> int:
        """Export full subtree from root_path, return number of files written."""
        self._written = 0
        self._out.mkdir(parents=True, exist_ok=True)
        await self._visit(root_path)
        logger.info(f"📄 导出完成：{self._written} 个文件 → {self._out}/")
        return self._written

    async def _visit(self, path: str) -> None:
        node = await self._repo.get_by_path(path)
        if not node or node.status == NodeStatus.ARCHIVED:
            return
        if node.node_type != NodeType.CATEGORY:
            return

        statuses = [NodeStatus.ACTIVE] if self._only_active else None
        all_children = await self._repo.list_children(path, statuses=statuses)

        leaves = [c for c in all_children if c.node_type == NodeType.LEAF]
        sub_cats = [
            c for c in all_children if c.node_type == NodeType.CATEGORY
        ]

        out_path = self._out / _category_filename(path)
        try:
            content = _render_category(node, leaves, sub_cats)
            out_path.write_text(content, encoding="utf-8")
        except Exception as e:
            logger.warning(f"  ⚠️ 跳过 {path}: {e}")
            return
        self._written += 1
        logger.debug(f"  ✍️  {out_path.name}")

        for sub in sub_cats:
            await self._visit(sub.path)


# --- Single-file export (compatible with legacy export_to_markdown) ---


def _heading(level: int) -> str:
    return "#" * min(level + 1, 6)


async def _export_tree_single(
        repo,
        path: str,
        lines: list[str],
        depth: int = 0,
        statuses: tuple[NodeStatus, ...] = (NodeStatus.ACTIVE, ),
) -> None:
    """Recursively traverse directory tree to generate single-file Markdown."""
    children = await repo.list_children(path, statuses=list(statuses))

    def _key(n):
        return (0 if n.node_type == NodeType.CATEGORY else 1, n.display_name
                or n.name)

    children = sorted(children, key=_key)

    for node in children:
        if node.node_type == NodeType.CATEGORY:
            title = node.display_name or node.name
            summary = (node.content or "").strip()
            if summary and len(summary) > 80:
                summary = summary[:77] + "..."
            header = f"{_heading(depth)} {title}"
            if summary:
                lines.append(f"{header}\n\n{summary}\n\n")
            else:
                lines.append(f"{header}\n\n")
            await _export_tree_single(repo, node.path, lines, depth + 1,
                                      statuses)
        else:
            content = (node.content or "").strip()
            if not content:
                content = f"[空] (id={node.id[:8]}...)"
            if len(content) > 200:
                content = content[:197] + "..."
            indent = "  " * depth
            lines.append(f"{indent}- {content}\n")


async def export_to_markdown(db_path: Path,
                             out_path: Path | None = None) -> str:
    """
    Export database to single-file Markdown string. If out_path is specified, also write to file.
    (Compatible with run.py --export invocation)
    """
    factory = SQLiteUoWFactory(db_path)
    await factory.init()
    try:
        lines = ["# SemaFS 记忆视图\n\n", f"数据库: `{db_path}`\n\n"]
        statuses = (
            NodeStatus.ACTIVE,
            NodeStatus.PENDING_REVIEW,
            NodeStatus.PROCESSING,
        )
        await _export_tree_single(factory.repo,
                                  "root",
                                  lines,
                                  depth=0,
                                  statuses=statuses)
        md = "".join(lines)
        if out_path:
            out_path.write_text(md, encoding="utf-8")
            print(f"已导出到: {out_path}")
        return md
    finally:
        await factory.close()


# --- CLI ---


def _get_default_db() -> Path:
    for name in ("openai_demo", "demo"):
        p = _project_root / "tests" / "output" / f"semafs_{name}.db"
        if p.exists():
            return p
    return _project_root / "tests" / "output" / "semafs_openai_demo.db"


async def _export_md(args: argparse.Namespace) -> None:
    factory = SQLiteUoWFactory(args.db)
    await factory.init()
    try:
        exporter = MarkdownExporter(factory.repo,
                                    args.out,
                                    only_active=args.only_active)
        count = await exporter.export(args.root)
        print(f"✅  {count} 个文件 → {args.out}/")
    finally:
        await factory.close()


async def _export_tree(args: argparse.Namespace) -> None:
    factory = SQLiteUoWFactory(args.db)
    await factory.init()
    try:
        if getattr(args, "print_only", False):
            exporter = TreeTextView(factory.repo)
            text = await exporter.export(args.root)
            print(text)
        else:
            exporter = TreeStructureExporter(factory.repo, args.out)
            count = await exporter.export(args.root)
            print(f"✅  {count} 个目录 → {args.out}/")
    finally:
        await factory.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m semafs.export",
        description="SemaFS database export",
    )
    parser.add_argument(
        "--db",
        default=None,
        metavar="PATH",
        help="Database path (default: tests/output/semafs_*_demo.db)",
    )
    parser.add_argument(
        "--out",
        default="vault",
        metavar="DIR",
        help="Export directory (default: vault)",
    )
    parser.add_argument(
        "--root",
        default="root",
        metavar="PATH",
        help="Export root path",
    )
    parser.add_argument(
        "--tree",
        action="store_true",
        help="Export folder structure (create directories)",
    )
    parser.add_argument(
        "--print",
        dest="print_only",
        action="store_true",
        help="Output text tree view only, no files or directories created",
    )
    parser.add_argument(
        "--only-active",
        action="store_true",
        help="Export ACTIVE nodes only (default: export all non-archived)",
    )
    parser.add_argument(
        "--all-statuses",
        action="store_true",
        help=
        "Export all statuses (default enabled, mutually exclusive with --only-active)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help=
        "Output path for single-file export (mutually exclusive with --out)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    db_path = Path(args.db) if args.db else _get_default_db()
    if not db_path.exists():
        print(f"错误: 数据库不存在: {db_path}", file=sys.stderr)
        sys.exit(1)
    args.db = db_path

    if args.all_statuses:
        args.only_active = False  # --all-statuses explicitly requests full export

    if args.output is not None:
        out = None if args.output == "-" else Path(args.output)
        md = asyncio.run(export_to_markdown(db_path, out))
        if out is None:
            print(md)
        return

    if args.print_only or args.tree:
        asyncio.run(_export_tree(args))
    else:
        asyncio.run(_export_md(args))


if __name__ == "__main__":
    main()
