"""
Renderer implementations: Convert views to various output formats.

This module provides concrete implementations of the Renderer protocol,
each optimized for a specific output target:

- TextRenderer: Terminal output with tree visualization
- MarkdownRenderer: Document export with proper headings
- LLMRenderer: Minimal format for LLM context (lowest token cost)
- JSONRenderer: Structured data for API responses

Design Philosophy:
    Data is data, presentation is presentation - never mix them.
    Views contain only data; Renderers handle all formatting.

Usage:
    from semafs.renderer import TextRenderer, MarkdownRenderer

    tree_view = await semafs.view_tree("root")
    print(TextRenderer.render_tree(tree_view))

    with open("export.md", "w") as f:
        f.write(MarkdownRenderer.render_tree(tree_view))
"""
from __future__ import annotations

import json
from typing import Any, Dict

from .core.views import NodeView, TreeView, RelatedNodes, StatsView
from .ports.renderer import Renderer


class TextRenderer(Renderer):
    """
    Terminal-friendly text renderer.

    Produces human-readable output with tree visualization using
    box-drawing characters (├── └── │).

    Best for:
    - CLI output
    - Debug logging
    - Quick inspection
    """

    @staticmethod
    def render_node(view: NodeView, show_breadcrumb: bool = True) -> str:
        """
        Render a single node view to text.

        Args:
            view: The NodeView to render.
            show_breadcrumb: Whether to show the path breadcrumb.

        Returns:
            Formatted text representation.
        """
        lines = []

        if show_breadcrumb:
            lines.append(f"Path: {' > '.join(view.breadcrumb)}")

        lines.append(f"Type: {'Category' if view.is_category else 'Leaf'}")

        if view.is_category:
            lines.append(f"Children: {view.child_count}")
            lines.append(f"Siblings: {view.sibling_count}")

        lines.append(f"\nContent:\n{view.node.content}")

        return "\n".join(lines)

    @staticmethod
    def render_tree(view: TreeView,
                    indent: str = "  ",
                    show_content: bool = False) -> str:
        """
        Render tree structure with box-drawing characters.

        Example output:
            root
              ├── work (3 items)
              │   ├── projects (5 items)
              │   └── meetings (2 items)
              └── personal (1 item)

        Args:
            view: The TreeView to render.
            indent: Base indentation string.
            show_content: Whether to show content preview for leaves.

        Returns:
            Formatted tree representation.
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

        # Render children with tree connectors
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
        """
        Render related nodes navigation map.

        Args:
            related: The RelatedNodes to render.

        Returns:
            Formatted navigation information.
        """
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
        """
        Render statistics overview.

        Args:
            stats: The StatsView to render.

        Returns:
            Formatted statistics.
        """
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


class MarkdownRenderer(Renderer):
    """
    Markdown document renderer.

    Produces properly formatted Markdown suitable for documentation,
    note-taking apps, and export.

    Best for:
    - Document export
    - Knowledge sharing
    - Integration with Markdown-based tools
    """

    @staticmethod
    def render_node(view: NodeView, heading_level: int = 1) -> str:
        """
        Render a node as Markdown.

        Args:
            view: The NodeView to render.
            heading_level: Heading level (1-6) for the title.

        Returns:
            Formatted Markdown string.
        """
        h = "#" * heading_level
        lines = [f"{h} {view.node.display_name or view.node.name}", ""]

        # Breadcrumb navigation
        breadcrumb = " → ".join(view.breadcrumb)
        lines.append(f"**Path**: {breadcrumb}  ")

        # Type information
        if view.is_category:
            lines.append(f"**Type**: Category ({view.child_count} children)  ")
        else:
            lines.append(f"**Type**: Leaf  ")

        lines.append("")

        # Content section
        if view.node.content:
            lines.append("## Content")
            lines.append("")
            lines.append(view.node.content)

        return "\n".join(lines)

    @staticmethod
    def render_tree(view: TreeView, heading_level: int = 1) -> str:
        """
        Recursively render tree as Markdown with nested headings.

        Args:
            view: The TreeView to render.
            heading_level: Starting heading level.

        Returns:
            Formatted Markdown document.
        """
        from .core.enums import NodeType

        h = "#" * heading_level
        name = view.node.display_name or view.node.name
        lines = [f"{h} {name}"]

        if view.node.content:
            lines.append("")
            # Truncate long content
            content = view.node.content[:200]
            if len(view.node.content) > 200:
                content += "..."
            lines.append(content)

        lines.append("")

        # Recursively render children with increased heading level
        for child in view.children:
            child_md = MarkdownRenderer.render_tree(child, heading_level + 1)
            lines.append(child_md)

        return "\n".join(lines)


class LLMRenderer(Renderer):
    """
    Minimalist renderer optimized for LLM consumption.

    Produces compact output that minimizes token usage while
    maintaining semantic clarity. Uses simple tags and minimal
    formatting.

    Design Principles:
        1. Minimal tokens: No verbose headers or decorations
        2. Clear structure: Indentation and simple separators
        3. Semantic clarity: Preserve meaning despite brevity

    Best for:
    - LLM context windows
    - API responses to LLMs
    - Token-constrained scenarios
    """

    @staticmethod
    def render_node(view: NodeView) -> str:
        """
        Render node in minimal LLM-friendly format.

        Args:
            view: The NodeView to render.

        Returns:
            Compact representation with [DIR]/[LEAF] tags.
        """
        type_tag = "[DIR]" if view.is_category else "[LEAF]"
        lines = [f"{type_tag} {view.path}"]

        if view.is_category and view.child_count > 0:
            lines.append(f"  Contains: {view.child_count} items")

        if view.node.content:
            # Truncate to 150 chars for minimal token usage
            content = view.node.content[:150].replace("\n", " ")
            if len(view.node.content) > 150:
                content += "..."
            lines.append(f"  {content}")

        return "\n".join(lines)

    @staticmethod
    def render_tree(view: TreeView, max_content_len: int = 80) -> str:
        """
        Render tree in compact format.

        Output format:
            root/
              work/ (3)
                projects/ (5)
                  - frontend_refactor: content preview...
                meetings/ (2)
              personal/ (1)

        Args:
            view: The TreeView to render.
            max_content_len: Maximum content preview length.

        Returns:
            Compact tree representation.
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
        Render navigation in single-line format.

        Output format:
            Current: root.work.projects
            Parent: root.work
            Siblings: meetings, tasks
            Children: frontend, backend

        Args:
            related: The RelatedNodes to render.

        Returns:
            Compact navigation summary.
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
    JSON renderer for structured data output.

    Produces properly formatted JSON suitable for API responses
    and programmatic consumption.

    Best for:
    - API endpoints
    - Data export
    - Integration with other systems
    """

    @staticmethod
    def render_node(view: NodeView) -> str:
        """
        Render node as JSON.

        Args:
            view: The NodeView to render.

        Returns:
            Formatted JSON string.
        """
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
        """
        Recursively render tree as JSON.

        Args:
            view: The TreeView to render.

        Returns:
            Formatted JSON with nested structure.
        """

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
        """
        Render statistics as JSON.

        Args:
            stats: The StatsView to render.

        Returns:
            Formatted JSON with statistics.
        """
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
