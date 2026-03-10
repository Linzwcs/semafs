"""
Renderer protocol: Interface for converting views to output formats.

This module defines the Renderer protocol that all view renderers must
implement. Renderers convert immutable View objects into formatted strings
suitable for different output targets.

Design Principles:
    1. Protocol-first: Define interface, not implementation
    2. Single responsibility: Each renderer handles one format
    3. Stateless: All methods are pure functions (static methods)
    4. Views are data, renderers handle presentation

Implementations:
    - TextRenderer: Terminal-friendly tree output with box characters
    - MarkdownRenderer: Export to Markdown documents
    - LLMRenderer: Minimal format optimized for LLM context (low token cost)
    - JSONRenderer: Structured data for API responses

Usage:
    tree_view = await semafs.view_tree("root")
    text_output = TextRenderer.render_tree(tree_view)
    markdown_output = MarkdownRenderer.render_tree(tree_view)
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..core.views import NodeView, TreeView, RelatedNodes, StatsView


@runtime_checkable
class Renderer(Protocol):
    """
    Protocol for view-to-string rendering.

    All renderers implement this protocol to provide consistent
    rendering interfaces across different output formats.

    Implementation Notes:
        - All methods are static (no instance state needed)
        - Methods may raise NotImplementedError if not applicable
        - Renderers should handle edge cases (empty content, etc.)

    Method Signatures:
        - render_node: Single node with context
        - render_tree: Recursive tree structure
        - render_related: Navigation map
        - render_stats: Knowledge base statistics
    """

    @staticmethod
    def render_node(view: NodeView) -> str:
        """
        Render a single node view to string.

        Args:
            view: NodeView containing node and context.

        Returns:
            Formatted string representation of the node.
        """
        ...

    @staticmethod
    def render_tree(view: TreeView) -> str:
        """
        Render a tree view to string.

        Args:
            view: TreeView containing recursive tree structure.

        Returns:
            Formatted string showing the tree hierarchy.
        """
        ...

    @staticmethod
    def render_related(related: RelatedNodes) -> str:
        """
        Render a related nodes navigation map to string.

        Args:
            related: RelatedNodes containing navigation context.

        Returns:
            Formatted string showing related nodes.
        """
        ...

    @staticmethod
    def render_stats(stats: StatsView) -> str:
        """
        Render statistics view to string.

        Args:
            stats: StatsView containing knowledge base metrics.

        Returns:
            Formatted string showing statistics.
        """
        ...
