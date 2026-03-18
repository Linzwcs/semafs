"""Prompt builder and tool schema for LLM-based reorganization."""

from __future__ import annotations
from typing import Tuple

from ...core.node import Node
from ...core.rules import GENERIC_CATEGORY_NAMES
from ...core.snapshot import Snapshot

_TREE_OPS_SCHEMA = {
    "name": "tree_ops",
    "description": "Decide how to reorganize memory fragments in a directory.",
    "input_schema": {
        "type":
        "object",
        "required": [
            "ops",
            "overall_reasoning",
            "updated_content",
            "should_dirty_parent",
        ],
        "properties": {
            "ops": {
                "type": "array",
                "description":
                ("List of operations. Return empty [] if healthy."),
                "items": {
                    "type": "object",
                    "required": ["op_type", "ids", "reasoning", "name"],
                    "properties": {
                        "op_type": {
                            "type": "string",
                            "enum": ["MERGE", "GROUP", "MOVE", "RENAME"],
                        },
                        "ids": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            }
                        },
                        "reasoning": {
                            "type": "string"
                        },
                        "name": {
                            "type": "string"
                        },
                        "content": {
                            "type": "string"
                        },
                        "path_to_move": {
                            "type": "string"
                        },
                        "evidence": {
                            "type":
                            "array",
                            "items": {
                                "type": "string"
                            },
                            "description":
                            ("For MERGE/GROUP, list concrete shared "
                             "semantic anchors that justify the operation."),
                        },
                    },
                },
            },
            "overall_reasoning": {
                "type": "string"
            },
            "updated_content": {
                "type": "string"
            },
            "updated_name": {
                "type": "string"
            },
            "updated_keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description":
                ("Semantic keywords for current category "
                 "(2-6 concise terms)."),
            },
            "should_dirty_parent": {
                "type": "boolean"
            },
        },
    },
}


def _format_node_list(nodes: list[Node]) -> str:
    if not nodes:
        return "  (empty)"
    lines = []
    for n in nodes:
        content = n.content or n.summary or ""
        lines.append(f"  - [id: {n.id[:8]}] type: {n.node_type.value} | "
                     f"name: {n.name} | content: {content[:120]}...")
    return "\n".join(lines) + "\n\nNote: use id to identify nodes, not name."


def build_prompt(snapshot: Snapshot) -> Tuple[str, str]:
    blocked_names = ", ".join(f"`{name}`"
                              for name in sorted(GENERIC_CATEGORY_NAMES))
    """Build (system, user) prompts from Snapshot."""
    all_nodes = list(snapshot.leaves) + list(snapshot.pending)
    total = len(all_nodes) + len(snapshot.subcategories)
    budget = snapshot.budget

    sub_cats = list(snapshot.subcategories)
    available_paths = "\n".join(f"  * {c.path.value}"
                                for c in sub_cats) or "  (no subcategories)"

    sibling_info = ""
    if snapshot.siblings:
        names = [f"'{s.name}'" for s in snapshot.siblings]
        sibling_info = (
            f"\n<sibling_categories>\n"
            f"Sibling names (avoid conflicts): {', '.join(names)}\n"
            f"</sibling_categories>")

    ancestor_info = ""
    if snapshot.ancestors:
        chain = []
        for i, anc in enumerate(reversed(snapshot.ancestors)):
            indent = "  " * i
            summary = (anc.summary or "")[:50]
            chain.append(f"{indent}└─ {anc.path.value}: {summary}")
        ancestor_info = ("\n<hierarchical_context>\n" + "\n".join(chain) +
                         "\n" + ("  " * len(snapshot.ancestors)) +
                         f"└─ {snapshot.target.path.value} (current)\n" +
                         "</hierarchical_context>")

    system_prompt = (
        "You are a knowledge graph scheduling engine running inside SemaFS.\n"
        f"Core responsibility: Semantically cluster and reduce "
        f"nodes under {budget.soft}.\n\n"
        "Operation priority: GROUP > MOVE > MERGE.\n"
        "GROUP: related nodes, no existing category. "
        "MOVE: node fits existing subcategory. "
        "MERGE: different aspects of same thing "
        "(last resort, loses granularity). "
        "RENAME: improve semantic readability for placeholder names.\n\n"
        "Leaf naming policy: leaf names are technical and stable. "
        "Do NOT rename leaf nodes. RENAME is category-only.\n"
        "Stability guard: do NOT rename top-level categories under root "
        "(e.g. keep root.work/root.personal/"
        "root.learning/root.ideas stable).\n"
        "MERGE guard: only emit MERGE when there is clear non-empty "
        "semantic intersection across all source nodes.\n"
        "Prefer GROUP over MERGE for high-volume preference/log-like data.\n"
        "For each MERGE, include `evidence` with shared anchors "
        "(entities/topics/keywords). If you cannot provide evidence, "
        "do not emit MERGE.\n"
        "MERGE content guard: merged `content` must be non-empty and include "
        "core facts from all source nodes; if not possible, do not MERGE.\n"
        "MOVE guard: only move when target category has stronger semantic fit "
        "than current parent, and explain why in `reasoning`.\n"
        "Relative naming guard: names must be relative to current directory; "
        "never repeat parent prefix.\n"
        "Category naming guard: each category segment must be "
        "a single english "
        "word (`^[a-z]+$`). You may use dotted recursive paths like "
        "`project.documentation.guides`, where every segment is one word.\n"
        "Do NOT use generic placeholder category names like "
        f"{blocked_names}.\n"
        "Example: if current_path is root.work, use `practices` "
        "(NOT `work_practices`, NOT `work.practices`, "
        "NOT `root.work.practices`).\n"
        "For MERGE result leaf, keep technical naming style (leaf_<hex>). "
        "Do not invent semantic leaf names.\n"
        "Naming: ONLY [a-z0-9_], ascii only, no spaces/chinese/punctuation. "
        "Do not output empty names or trailing dots.\n"
        "If you provide updated_name, it MUST be a single english word: "
        "regex ^[a-z]+$.\n"
        "Names are RELATIVE to current dir.\n"
        "updated_content: rewrite directory summary after ops.\n"
        "updated_keywords: provide 2-6 semantic keywords for current "
        "category.\n"
        "Summary contract: write 1-3 concise sentences that summarize all "
        "direct child content under the current category.\n"
        "should_dirty_parent: true if major new themes extracted.")

    status_warning = ""
    if total > budget.soft:
        status_warning = (
            f"CRITICAL: Node count ({total}) exceeds limit ({budget.soft}). "
            "You MUST perform MERGE or GROUP to reduce nodes!")
    elif snapshot.pending:
        status_warning = (
            "New fragments arrived. Consider proactive organization.")

    target_path = snapshot.target.path.value
    target_summary = snapshot.target.summary or "(empty)"

    user_content = (f"<directory_status>\n"
                    f"- current_path: \"{target_path}\"\n"
                    f"- capacity: {total}/{budget.soft}\n"
                    f"- alert: {status_warning}\n"
                    f"</directory_status>\n\n"
                    f"<current_directory_summary>\n{target_summary}\n"
                    f"</current_directory_summary>\n"
                    f"{sibling_info}{ancestor_info}\n"
                    "<available_move_targets>\n"
                    f"{available_paths}\n"
                    "</available_move_targets>\n\n"
                    f"<existing_active_nodes>\n"
                    f"{_format_node_list(list(snapshot.leaves))}\n"
                    f"</existing_active_nodes>\n\n"
                    f"<new_pending_fragments>\n"
                    f"{_format_node_list(list(snapshot.pending))}\n"
                    f"</new_pending_fragments>\n\n"
                    "Please call `tree_ops` with your reorganization plan.")

    return (system_prompt, user_content)
