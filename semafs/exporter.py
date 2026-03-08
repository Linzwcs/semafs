from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path
import argparse
import asyncio
import sys
from typing import List
from .models.enums import NodeStatus, NodeType
from .interface import TreeRepository
from .models.nodes import TreeNode

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
    if node.payload and node.payload.get("_is_virtual"):
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
    depth = node.path.count(".") + 1  # root=1, root.work=2, …
    heading = "#" * min(depth, 3)  # h1–h3

    # 当前 category 的元信息块
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

    # 子目录列表（含类型与路径）
    if sub_categories:
        lines += ["## 子目录 (CATEGORY)", ""]
        for c in sorted(sub_categories, key=lambda x: x.path):
            fname = _category_filename(c.path)
            lines.append(_sub_category_entry(c, fname))
        lines += ["", "---", ""]

    # 叶节点区块
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

    def __init__(self, repo: TreeRepository) -> None:
        self._repo = repo
        self._lines: List[str] = []

    async def export(self, root_path: str = "root") -> str:
        """返回树形文本。"""
        self._lines = []
        if hasattr(self._repo, "ensure_root_available"):
            await self._repo.ensure_root_available()
        await self._visit(root_path, "", True, is_root=True)
        return "\n".join(self._lines)

    async def _visit(self, path: str, prefix: str, is_last: bool, is_root: bool = False) -> None:
        node = await self._repo.get_node(path)
        if not node or node.status == NodeStatus.ARCHIVED:
            return
        if node.node_type != NodeType.CATEGORY:
            return

        statuses = [NodeStatus.ACTIVE, NodeStatus.PENDING_REVIEW, NodeStatus.PROCESSING]
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

        child_prefix = prefix + ("    " if is_last else "│   ") if not is_root else ""
        for i, sub in enumerate(sub_cats):
            await self._visit(sub.path, child_prefix, i == len(sub_cats) - 1, is_root=False)


class TreeStructureExporter:
    """
    仅导出文件夹架构，不生成 markdown 文件。
    在 output_dir 下创建与 path 对应的目录结构，如 root/work/personal/。
    """

    def __init__(self, repo: TreeRepository, output_dir: str | Path = "tree") -> None:
        self._repo = repo
        self._out = Path(output_dir)
        self._created = 0

    async def export(self, root_path: str = "root") -> int:
        """导出从 root_path 开始的目录结构，返回创建的目录数。"""
        self._created = 0
        if hasattr(self._repo, "ensure_root_available"):
            await self._repo.ensure_root_available()
        await self._visit(root_path)
        logger.info(f"📁 导出完成：{self._created} 个目录 → {self._out}/")
        return self._created

    async def _visit(self, path: str) -> None:
        node = await self._repo.get_node(path)
        if not node or node.status == NodeStatus.ARCHIVED:
            return
        if node.node_type != NodeType.CATEGORY:
            return

        statuses = [NodeStatus.ACTIVE, NodeStatus.PENDING_REVIEW, NodeStatus.PROCESSING]
        all_children = await self._repo.list_children(path, statuses=statuses)
        sub_cats = [c for c in all_children if c.node_type == NodeType.CATEGORY]

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
        repo:        任意 TreeRepository 实现
        output_dir:  导出目录（默认 "vault"）
        only_active: True 时跳过 PENDING_REVIEW 碎片
    """

    def __init__(
        self,
        repo: TreeRepository,
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
        # 读取层恢复：若 root 被误归档，确保可读（SQLite 会恢复为 ACTIVE）
        if hasattr(self._repo, "ensure_root_available"):
            await self._repo.ensure_root_available()
        await self._visit(root_path)
        logger.info(f"📄 导出完成：{self._written} 个文件 → {self._out}/")
        return self._written

    async def _visit(self, path: str) -> None:
        node = await self._repo.get_node(path)
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

        # Write this category's .md
        out_path = self._out / _category_filename(path)
        out_path.write_text(
            _render_category(node, leaves, sub_cats),
            encoding="utf-8",
        )
        self._written += 1
        logger.debug(f"  ✍️  {out_path.name}")

        # Recurse into sub-categories
        for sub in sub_cats:
            await self._visit(sub.path)


async def _export_md(args: argparse.Namespace) -> None:
    try:
        from semafs.infra.repositories import SQLiteTreeRepository
    except ImportError:
        print("❌  缺少依赖：pip install aiosqlite", file=sys.stderr)
        sys.exit(1)

    repo = SQLiteTreeRepository(args.db)
    await repo.init()

    exporter = MarkdownExporter(repo, args.out, only_active=args.only_active)
    count = await exporter.export(args.root)
    print(f"✅  {count} 个文件 → {args.out}/")


async def _export_tree(args: argparse.Namespace) -> None:
    try:
        from semafs.infra.repositories import SQLiteTreeRepository
    except ImportError:
        print("❌  缺少依赖：pip install aiosqlite", file=sys.stderr)
        sys.exit(1)

    repo = SQLiteTreeRepository(args.db)
    await repo.init()

    if getattr(args, "print_only", False):
        exporter = TreeTextView(repo)
        text = await exporter.export(args.root)
        print(text)
    else:
        exporter = TreeStructureExporter(repo, args.out)
        count = await exporter.export(args.root)
        print(f"✅  {count} 个目录 → {args.out}/")


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m semafs",
                                description="SemaFS CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    exp = sub.add_parser("export", help="导出数据库")
    exp.add_argument("--db", default="semafs.db", metavar="PATH")
    exp.add_argument("--out", default="vault", metavar="DIR")
    exp.add_argument("--root", default="root", metavar="PATH")
    exp.add_argument("--tree", action="store_true",
                     help="导出文件夹架构（创建目录）")
    exp.add_argument("--print", dest="print_only", action="store_true",
                     help="仅输出文本树视图，不创建文件或目录")
    exp.add_argument("--only-active", action="store_true")
    exp.add_argument("-v", "--verbose", action="store_true")

    args = p.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(message)s",
    )
    if getattr(args, "print_only", False):
        asyncio.run(_export_tree(args))
    elif getattr(args, "tree", False):
        asyncio.run(_export_tree(args))
    else:
        asyncio.run(_export_md(args))


if __name__ == "__main__":
    main()
