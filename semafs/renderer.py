"""Renderer implementations - Convert views to various output formats."""

from __future__ import annotations
import json
from typing import Any, Dict

from .core.views import NodeView, TreeView, RelatedNodes, StatsView
from .core.node import NodeType


class TextRenderer:
    """Terminal-friendly text renderer with box-drawing characters."""

    @staticmethod
    def render_node(view: NodeView, show_breadcrumb: bool = True) -> str:
        lines = []
        if show_breadcrumb:
            lines.append(f"Path: {' > '.join(view.breadcrumb)}")
        lines.append(f"Observed At: {view.observed_at}")
        lines.append(f"Type: {'Category' if view.is_category else 'Leaf'}")
        if view.is_category:
            lines.append(f"Children: {view.child_count}")
            lines.append(f"Siblings: {view.sibling_count}")
        timestamps = JSONRenderer._node_timestamps(view)  # noqa: SLF001
        if timestamps:
            lines.append(
                f"Timestamps: {json.dumps(timestamps, ensure_ascii=False)}")
        content = view.node.content or view.node.summary or ""
        lines.append(f"\nContent:\n{content}")
        return "\n".join(lines)

    @staticmethod
    def render_tree(view: TreeView,
                    indent: str = "  ",
                    show_content: bool = False) -> str:
        lines = []
        name = view.node.name
        if view.node.node_type == NodeType.CATEGORY:
            count_info = f" ({len(view.children)} items)" if view.children else ""
            lines.append(f"{name}{count_info}")
        else:
            if show_content and view.node.content:
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
        lines = [related.navigation_summary, "", "Details:", ""]
        if related.parent:
            lines.append(f"Parent: {related.parent.path}")
        if related.siblings:
            lines.append(f"\nSiblings ({len(related.siblings)}):")
            for sib in related.siblings:
                lines.append(f"  - {sib.path}")
        if related.children:
            lines.append(f"\nChildren ({len(related.children)}):")
            for child in related.children:
                lines.append(f"  - {child.path}")
        if related.ancestors:
            lines.append(f"\nAncestor chain:")
            for anc in related.ancestors:
                lines.append(f"  - {anc.path}")
        return "\n".join(lines)

    @staticmethod
    def render_stats(stats: StatsView) -> str:
        lines = [
            "Knowledge Base Statistics",
            "=" * 50,
            stats.summary,
            "",
            f"Pending maintenance: {stats.dirty_categories} categories",
            "",
            "Top Categories (by child count):",
        ]
        for path, count in stats.top_categories:
            lines.append(f"  {path}: {count} children")
        return "\n".join(lines)


class MarkdownRenderer:
    """Markdown document renderer."""

    @staticmethod
    def render_node(view: NodeView, heading_level: int = 1) -> str:
        h = "#" * heading_level
        lines = [f"{h} {view.node.name}", ""]
        breadcrumb = " → ".join(view.breadcrumb)
        lines.append(f"**Path**: {breadcrumb}  ")
        if view.is_category:
            lines.append(f"**Type**: Category ({view.child_count} children)  ")
        else:
            lines.append(f"**Type**: Leaf  ")
        lines.append("")
        content = view.node.content or view.node.summary or ""
        if content:
            lines.append("## Content")
            lines.append("")
            lines.append(content)
        return "\n".join(lines)

    @staticmethod
    def render_tree(view: TreeView, heading_level: int = 1) -> str:
        h = "#" * heading_level
        name = view.node.name
        lines = [f"{h} {name}"]
        content = view.node.content or view.node.summary or ""
        if content:
            lines.append("")
            preview = content[:200]
            if len(content) > 200:
                preview += "..."
            lines.append(preview)
        lines.append("")
        for child in view.children:
            child_md = MarkdownRenderer.render_tree(child, heading_level + 1)
            lines.append(child_md)
        return "\n".join(lines)


class LLMRenderer:
    """Minimalist renderer optimized for LLM consumption."""

    @staticmethod
    def render_node(view: NodeView) -> str:
        type_tag = "[DIR]" if view.is_category else "[LEAF]"
        lines = [f"{type_tag} {view.path}"]
        if view.is_category and view.child_count > 0:
            lines.append(f"  Contains: {view.child_count} items")
        content = view.node.content or view.node.summary or ""
        if content:
            preview = content[:150].replace("\n", " ")
            if len(content) > 150:
                preview += "..."
            lines.append(f"  {preview}")
        return "\n".join(lines)

    @staticmethod
    def render_tree(view: TreeView, max_content_len: int = 80) -> str:
        lines = []
        indent = "  " * view.depth
        if view.node.node_type == NodeType.CATEGORY:
            count = f" ({len(view.children)})" if view.children else ""
            lines.append(f"{indent}{view.node.name}/{count}")
        else:
            content = view.node.content or ""
            preview = content[:max_content_len].replace("\n", " ")
            if len(content) > max_content_len:
                preview += "..."
            lines.append(f"{indent}- {view.node.name}: {preview}")
        for child in view.children:
            lines.append(LLMRenderer.render_tree(child, max_content_len))
        return "\n".join(lines)

    @staticmethod
    def render_related(related: RelatedNodes) -> str:
        lines = [f"Current: {related.current.path}"]
        if related.parent:
            lines.append(f"Parent: {related.parent.path}")
        if related.siblings:
            names = ", ".join(s.node.name for s in related.siblings)
            lines.append(f"Siblings: {names}")
        if related.children:
            names = ", ".join(c.node.name for c in related.children[:10])
            if len(related.children) > 10:
                names += f" ... (+{len(related.children) - 10} more)"
            lines.append(f"Children: {names}")
        return "\n".join(lines)


class JSONRenderer:
    """JSON renderer for structured data output."""

    @staticmethod
    def render_node(view: NodeView) -> str:
        data = {
            "path": view.path,
            "type": "category" if view.is_category else "leaf",
            "breadcrumb": list(view.breadcrumb),
            "observed_at": view.observed_at,
            "content": view.node.content or view.node.summary or "",
            "child_count": view.child_count,
            "sibling_count": view.sibling_count,
            "timestamps": JSONRenderer._node_timestamps(view),
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    @staticmethod
    def _node_timestamps(view: NodeView) -> Dict[str, Any]:
        payload = view.node.payload if isinstance(view.node.payload,
                                                  dict) else {}
        ts = payload.get("_timestamps", {})
        if not isinstance(ts, dict):
            ts = {}
        # Backfill for legacy payloads if needed.
        if "_ingested_at" in payload and "written_at" not in ts:
            ts = dict(ts)
            ts["written_at"] = payload.get("_ingested_at")
        return {k: v for k, v in ts.items() if v}

    @staticmethod
    def render_tree(view: TreeView) -> str:

        def _to_dict(v: TreeView) -> Dict[str, Any]:
            return {
                "path": v.path,
                "type": "category"
                if v.node.node_type == NodeType.CATEGORY else "leaf",
                "content": v.node.content or v.node.summary or "",
                "depth": v.depth,
                "children": [_to_dict(c) for c in v.children],
            }

        return json.dumps(_to_dict(view), ensure_ascii=False, indent=2)

    @staticmethod
    def render_stats(stats: StatsView) -> str:
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
                "path": p,
                "child_count": c
            } for p, c in stats.top_categories],
        }
        return json.dumps(data, ensure_ascii=False, indent=2)
