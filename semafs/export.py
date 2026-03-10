"""
将 SemaFS 数据库导出为 Markdown 视图。

参考 semafs/exporter.py 实现，支持三种导出模式：
1. MarkdownExporter：每个 CATEGORY 导出为独立 .md 文件（扁平目录）
2. TreeStructureExporter：仅导出文件夹架构
3. TreeTextView：仅输出文本树视图到 stdout

用法：
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
    """节点元信息块，便于解析与区分。"""
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
    """单个叶节点渲染为独立区块，含完整元信息。"""
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
    """子 category 条目，含类型与路径。"""
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
    """root → root.md，root.work → root.work.md"""
    return path + ".md"


def _path_to_dir(path: str) -> str:
    """root → root/，root.work.personal → root/work/personal/"""
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
    仅输出文本树视图，不创建任何文件或目录。
    输出到 stdout，格式如：
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
        """返回树形文本。"""
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
    仅导出文件夹架构，不生成 markdown 文件。
    在 output_dir 下创建与 path 对应的目录结构，如 root/work/personal/。
    """

    def __init__(self, repo, output_dir: str | Path = "tree") -> None:
        self._repo = repo
        self._out = Path(output_dir)
        self._created = 0

    async def export(self, root_path: str = "root") -> int:
        """导出从 root_path 开始的目录结构，返回创建的目录数。"""
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
    将每个 CATEGORY 节点导出为一个 .md 文件（扁平目录，无子文件夹）。
    叶节点内容内联在所属目录文件中。

    Args:
        repo:        NodeRepository 实现
        output_dir:  导出目录（默认 "vault"）
        only_active: True 时仅导出 ACTIVE 节点（默认 False，完整导出含 PENDING/PROCESSING）
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
        """导出从 root_path 开始的完整子树，返回写入文件数。"""
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


# --- 单文件导出（兼容原有 export_to_markdown）---


def _heading(level: int) -> str:
    return "#" * min(level + 1, 6)


async def _export_tree_single(
        repo,
        path: str,
        lines: list[str],
        depth: int = 0,
        statuses: tuple[NodeStatus, ...] = (NodeStatus.ACTIVE, ),
) -> None:
    """递归遍历目录树，生成单文件 Markdown。"""
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
    导出数据库到单文件 Markdown 字符串。若 out_path 指定则同时写入文件。
    （兼容 run.py --export 调用）
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
        description="SemaFS 数据库导出",
    )
    parser.add_argument(
        "--db",
        default=None,
        metavar="PATH",
        help="数据库路径（默认 tests/output/semafs_*_demo.db）",
    )
    parser.add_argument(
        "--out",
        default="vault",
        metavar="DIR",
        help="导出目录（默认 vault）",
    )
    parser.add_argument(
        "--root",
        default="root",
        metavar="PATH",
        help="导出起点路径",
    )
    parser.add_argument(
        "--tree",
        action="store_true",
        help="导出文件夹架构（创建目录）",
    )
    parser.add_argument(
        "--print",
        dest="print_only",
        action="store_true",
        help="仅输出文本树视图，不创建文件或目录",
    )
    parser.add_argument(
        "--only-active",
        action="store_true",
        help="仅导出 ACTIVE 节点（默认导出全部非归档状态）",
    )
    parser.add_argument(
        "--all-statuses",
        action="store_true",
        help="导出所有状态（默认已启用，与 --only-active 互斥）",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="单文件导出时的输出路径（与 --out 互斥）",
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
        args.only_active = False  # --all-statuses 显式要求完整导出

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
