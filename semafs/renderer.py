from __future__ import annotations

import json
from typing import Any, Dict

from .core.views import NodeView, TreeView, RelatedNodes, StatsView
from .ports.renderer import Renderer


class TextRenderer(Renderer):

    @staticmethod
    def render_node(view: NodeView, show_breadcrumb: bool = True) -> str:
        """渲染单个节点视图。"""
        lines = []

        if show_breadcrumb:
            lines.append(f"路径: {' > '.join(view.breadcrumb)}")

        lines.append(f"类型: {'目录' if view.is_category else '叶子'}")

        if view.is_category:
            lines.append(f"子节点: {view.child_count} 个")
            lines.append(f"同级节点: {view.sibling_count} 个")

        lines.append(f"\n内容:\n{view.node.content}")

        return "\n".join(lines)

    @staticmethod
    def render_tree(view: TreeView,
                    indent: str = "  ",
                    show_content: bool = False) -> str:
        """
        渲染树形结构（类似 `tree` 命令）。

        示例:
            root
              ├── work (3 items)
              │   ├── projects (5 items)
              │   └── meetings (2 items)
              └── personal (1 item)
        """
        from .core.enums import NodeType

        lines = []
        name = view.node.display_name or view.node.name

        if view.node.node_type == NodeType.CATEGORY:
            count_info = f" ({len(view.children)} items)" if view.children else ""
            lines.append(f"{name}{count_info}")
        else:
            if show_content:
                preview = view.node.content[:40].replace("\n", " ")
                lines.append(f"{name}: {preview}...")
            else:
                lines.append(name)

        for i, child in enumerate(view.children):
            is_last = i == len(view.children) - 1
            prefix = "└── " if is_last else "├── "
            child_indent = "    " if is_last else "│   "

            child_text = TextRenderer.render_tree(child, indent, show_content)
            first_line, *rest_lines = child_text.split("\n")
            lines.append(indent + prefix + first_line)

            for line in rest_lines:
                if line.strip():
                    lines.append(indent + child_indent + line)

        return "\n".join(lines)

    @staticmethod
    def render_related(related: RelatedNodes) -> str:
        """渲染相关节点。"""
        lines = [related.navigation_summary, "", "详细信息:", ""]

        if related.parent:
            lines.append(f"父级: {related.parent.path}")

        if related.siblings:
            lines.append(f"\n同级节点 ({len(related.siblings)}):")
            for sib in related.siblings:
                lines.append(f"  - {sib.path}")

        if related.children:
            lines.append(f"\n子节点 ({len(related.children)}):")
            for child in related.children:
                lines.append(f"  - {child.path}")

        if related.ancestors:
            lines.append(f"\n祖先链:")
            for anc in related.ancestors:
                lines.append(f"  - {anc.path}")

        return "\n".join(lines)

    @staticmethod
    def render_stats(stats: StatsView) -> str:
        """渲染统计信息。"""
        lines = [
            "知识库统计",
            "=" * 50,
            stats.summary,
            "",
            f"待整理目录: {stats.dirty_categories} 个",
            "",
            "热门目录 (Top 10):",
        ]

        for path, count in stats.top_categories:
            lines.append(f"  {path}: {count} 个子节点")

        return "\n".join(lines)


class MarkdownRenderer(Renderer):
    """
    Markdown 渲染器：生成 Markdown 格式。

    适用于：文档导出、笔记整理、分享。
    实现 Renderer 协议。
    """

    @staticmethod
    def render_node(view: NodeView, heading_level: int = 1) -> str:
        """渲染单个节点为 Markdown。"""
        h = "#" * heading_level
        lines = [f"{h} {view.node.display_name or view.node.name}", ""]

        # 面包屑
        breadcrumb = " → ".join(view.breadcrumb)
        lines.append(f"**路径**: {breadcrumb}  ")

        # 元信息
        if view.is_category:
            lines.append(f"**类型**: 目录 (包含 {view.child_count} 个子节点)  ")
        else:
            lines.append(f"**类型**: 叶子节点  ")

        lines.append("")

        # 内容
        if view.node.content:
            lines.append("## 内容")
            lines.append("")
            lines.append(view.node.content)

        return "\n".join(lines)

    @staticmethod
    def render_tree(view: TreeView, heading_level: int = 1) -> str:
        """递归渲染树形结构为 Markdown。"""
        from .core.enums import NodeType

        h = "#" * heading_level
        name = view.node.display_name or view.node.name
        lines = [f"{h} {name}"]

        if view.node.content:
            lines.append("")
            # 截断内容避免太长
            content = view.node.content[:200]
            if len(view.node.content) > 200:
                content += "..."
            lines.append(content)

        lines.append("")

        # 递归渲染子节点
        for child in view.children:
            child_md = MarkdownRenderer.render_tree(child, heading_level + 1)
            lines.append(child_md)

        return "\n".join(lines)


class LLMRenderer(Renderer):
    """
    LLM 专用渲染器：生成极简、结构化的格式。

    设计原则：
    1. 最小 token 消耗：省略冗余信息
    2. 结构清晰：使用缩进、分隔符保持可读性
    3. 语义优先：只保留 LLM 需要的语义信息

    实现 Renderer 协议。
    """

    @staticmethod
    def render_node(view: NodeView) -> str:
        """极简节点视图（适合 LLM 快速理解）。"""
        type_tag = "[DIR]" if view.is_category else "[LEAF]"
        lines = [f"{type_tag} {view.path}"]

        if view.is_category and view.child_count > 0:
            lines.append(f"  Contains: {view.child_count} items")

        if view.node.content:
            # 只保留前 150 字符
            content = view.node.content[:150].replace("\n", " ")
            if len(view.node.content) > 150:
                content += "..."
            lines.append(f"  {content}")

        return "\n".join(lines)

    @staticmethod
    def render_tree(view: TreeView, max_content_len: int = 80) -> str:
        """
        极简树形视图。

        格式:
            root/
              work/ (3)
                projects/ (5)
                  - frontend_refactor: 重构前端架构...
                  - backend_api: 后端API设计...
                meetings/ (2)
              personal/ (1)
        """
        from .core.enums import NodeType

        lines = []
        indent = "  " * view.depth

        if view.node.node_type == NodeType.CATEGORY:
            count = f" ({len(view.children)})" if view.children else ""
            lines.append(f"{indent}{view.node.name}/{count}")
        else:
            content_preview = view.node.content[:max_content_len].replace(
                "\n", " ")
            if len(view.node.content) > max_content_len:
                content_preview += "..."
            lines.append(f"{indent}- {view.node.name}: {content_preview}")

        for child in view.children:
            lines.append(LLMRenderer.render_tree(child, max_content_len))

        return "\n".join(lines)

    @staticmethod
    def render_related(related: RelatedNodes) -> str:
        """
        极简相关节点视图。

        格式:
            Current: root.work.projects
            Parent: root.work
            Siblings: meetings, tasks
            Children: frontend, backend
        """
        lines = [f"Current: {related.current.path}"]

        if related.parent:
            lines.append(f"Parent: {related.parent.path}")

        if related.siblings:
            sibling_names = ", ".join(s.node.name for s in related.siblings)
            lines.append(f"Siblings: {sibling_names}")

        if related.children:
            child_names = ", ".join(c.node.name for c in related.children[:10])
            if len(related.children) > 10:
                child_names += f" ... (+{len(related.children) - 10} more)"
            lines.append(f"Children: {child_names}")

        return "\n".join(lines)


class JSONRenderer(Renderer):
    """
    JSON 渲染器：生成结构化 JSON。

    适用于：API 响应、程序间交互、数据导出。
    实现 Renderer 协议。
    """

    @staticmethod
    def render_node(view: NodeView) -> str:
        """渲染节点为 JSON。"""
        data = {
            "path": view.path,
            "type": "category" if view.is_category else "leaf",
            "breadcrumb": list(view.breadcrumb),
            "content": view.node.content,
            "child_count": view.child_count,
            "sibling_count": view.sibling_count,
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    @staticmethod
    def render_tree(view: TreeView) -> str:
        """递归渲染树为 JSON。"""

        def _to_dict(v: TreeView) -> Dict[str, Any]:
            return {
                "path": v.path,
                "type":
                "category" if v.node.node_type.value == "CATEGORY" else "leaf",
                "content": v.node.content,
                "depth": v.depth,
                "children": [_to_dict(child) for child in v.children],
            }

        data = _to_dict(view)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @staticmethod
    def render_stats(stats: StatsView) -> str:
        """渲染统计信息为 JSON。"""
        data = {
            "total_nodes":
            stats.total_nodes,
            "total_categories":
            stats.total_categories,
            "total_leaves":
            stats.total_leaves,
            "max_depth":
            stats.max_depth,
            "dirty_categories":
            stats.dirty_categories,
            "top_categories": [{
                "path": path,
                "child_count": count
            } for path, count in stats.top_categories],
        }
        return json.dumps(data, ensure_ascii=False, indent=2)
