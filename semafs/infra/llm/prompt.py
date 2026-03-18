"""Prompt builder and tool schema for LLM-based reorganization."""

from __future__ import annotations
from typing import Tuple

from ...core.node import Node, NodeType
from ...core.snapshot import Snapshot

_TREE_OPS_SCHEMA = {
    "name": "tree_ops",
    "description": "Decide how to reorganize memory fragments in a directory.",
    "input_schema": {
        "type": "object",
        "required": ["ops", "overall_reasoning", "updated_content", "should_dirty_parent"],
        "properties": {
            "ops": {
                "type": "array",
                "description": "List of operations. Return empty [] if healthy.",
                "items": {
                    "type": "object",
                    "required": ["op_type", "ids", "reasoning", "name"],
                    "properties": {
                        "op_type": {"type": "string", "enum": ["MERGE", "GROUP", "MOVE"]},
                        "ids": {"type": "array", "items": {"type": "string"}},
                        "reasoning": {"type": "string"},
                        "name": {"type": "string"},
                        "content": {"type": "string"},
                        "path_to_move": {"type": "string"},
                    },
                },
            },
            "overall_reasoning": {"type": "string"},
            "updated_content": {"type": "string"},
            "updated_name": {"type": "string"},
            "should_dirty_parent": {"type": "boolean"},
        },
    },
}


def _format_node_list(nodes: list[Node]) -> str:
    if not nodes:
        return "  (empty)"
    lines = []
    for n in nodes:
        content = n.content or n.summary or ""
        lines.append(
            f"  - [id: {n.id[:8]}] type: {n.node_type.value} | "
            f"name: {n.name} | content: {content[:120]}..."
        )
    return "\n".join(lines) + "\n\nNote: use id to identify nodes, not name."


def build_prompt(snapshot: Snapshot) -> Tuple[str, str]:
    """Build (system, user) prompts from Snapshot."""
    all_nodes = list(snapshot.leaves) + list(snapshot.pending)
    total = len(all_nodes) + len(snapshot.subcategories)
    budget = snapshot.budget

    sub_cats = list(snapshot.subcategories)
    available_paths = "\n".join(
        f"  * {c.path.value}" for c in sub_cats
    ) or "  (no subcategories)"

    sibling_info = ""
    if snapshot.siblings:
        names = [f"'{s.name}'" for s in snapshot.siblings]
        sibling_info = (
            f"\n<sibling_categories>\n"
            f"Sibling names (avoid conflicts): {', '.join(names)}\n"
            f"</sibling_categories>"
        )

    ancestor_info = ""
    if snapshot.ancestors:
        chain = []
        for i, anc in enumerate(reversed(snapshot.ancestors)):
            indent = "  " * i
            summary = (anc.summary or "")[:50]
            chain.append(f"{indent}└─ {anc.path.value}: {summary}")
        ancestor_info = (
            f"\n<hierarchical_context>\n"
            + "\n".join(chain)
            + f"\n{'  ' * len(snapshot.ancestors)}"
            + f"└─ {snapshot.target.path.value} (current)\n"
            + "</hierarchical_context>"
        )

    system_prompt = (
        "You are a knowledge graph scheduling engine running inside SemaFS.\n"
        f"Core responsibility: Semantically cluster and reduce nodes under {budget.soft}.\n\n"
        "Operation priority: MOVE > GROUP > MERGE.\n"
        "MOVE: node fits existing subcategory. GROUP: related nodes, no existing category. "
        "MERGE: different aspects of same thing (last resort, loses granularity).\n\n"
        "Naming: lowercase a-z/0-9, dots for hierarchy. Names are RELATIVE to current dir.\n"
        "updated_content: rewrite directory summary after ops.\n"
        "should_dirty_parent: true if major new themes extracted."
    )

    status_warning = ""
    if total > budget.soft:
        status_warning = (
            f"CRITICAL: Node count ({total}) exceeds limit ({budget.soft}). "
            "You MUST perform MERGE or GROUP to reduce nodes!"
        )
    elif snapshot.pending:
        status_warning = "New fragments arrived. Consider proactive organization."

    target_path = snapshot.target.path.value
    target_summary = snapshot.target.summary or "(empty)"

    user_content = (
        f"<directory_status>\n"
        f"- current_path: \"{target_path}\"\n"
        f"- capacity: {total}/{budget.soft}\n"
        f"- alert: {status_warning}\n"
        f"</directory_status>\n\n"
        f"<current_directory_summary>\n{target_summary}\n</current_directory_summary>\n"
        f"{sibling_info}{ancestor_info}\n"
        f"<available_move_targets>\n{available_paths}\n</available_move_targets>\n\n"
        f"<existing_active_nodes>\n{_format_node_list(list(snapshot.leaves))}\n</existing_active_nodes>\n\n"
        f"<new_pending_fragments>\n{_format_node_list(list(snapshot.pending))}\n</new_pending_fragments>\n\n"
        "Please call `tree_ops` with your reorganization plan."
    )

    return (system_prompt, user_content)
