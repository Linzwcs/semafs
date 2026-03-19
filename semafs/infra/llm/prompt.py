"""Prompt builder and tool schema for LLM-based reorganization."""

from __future__ import annotations
from typing import Tuple

from ...core.node import Node
from ...core.rules import GENERIC_CATEGORY_NAMES
from ...core.snapshot import Snapshot
from ...engine.guard import is_name_locked_node

KEYWORD_MIN_ITEMS = 2
KEYWORD_MAX_ITEMS = 6
SUMMARY_MAX_CHARS = 500
SUMMARY_SENTENCE_RANGE = "1-3"
GROUP_SUMMARY_SENTENCE_RANGE = "1-2"

SUMMARY_CONTRACT_TEXT = (
    f"{SUMMARY_SENTENCE_RANGE} concise sentences, plain text only, "
    f"max {SUMMARY_MAX_CHARS} chars, no bullets/JSON."
)
GROUP_SUMMARY_CONTRACT_TEXT = (
    "For GROUP: required category summary "
    f"({GROUP_SUMMARY_SENTENCE_RANGE} sentences). For MERGE: merged content."
)
KEYWORD_CONTRACT_TEXT = (
    f"Required semantic keywords for current category "
    f"({KEYWORD_MIN_ITEMS}-{KEYWORD_MAX_ITEMS}). "
    "No time tokens (e.g. 15:00), no system tokens "
    "(e.g. leaf_xxx/rollup_xxx), no placeholders."
)

_TREE_OPS_SCHEMA = {
    "name": "tree_ops",
    "description": "Decide how to reorganize memory fragments in a directory.",
    "input_schema": {
        "type":
        "object",
        "required": [
            "ops",
            "overall_reasoning",
            "updated_summary",
            "updated_keywords",
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
                            "type":
                            "string",
                            "description":
                            GROUP_SUMMARY_CONTRACT_TEXT,
                        },
                        "keywords": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                            "minItems": KEYWORD_MIN_ITEMS,
                            "maxItems": KEYWORD_MAX_ITEMS,
                            "description": (
                                "For GROUP: semantic keywords for the "
                                "new category (2-6)."
                            ),
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
            "updated_summary": {
                "type":
                "string",
                "description":
                "Updated category summary. " + SUMMARY_CONTRACT_TEXT,
            },
            "updated_name": {
                "type": "string"
            },
            "updated_keywords": {
                "type":
                "array",
                "items": {
                    "type": "string"
                },
                "minItems":
                KEYWORD_MIN_ITEMS,
                "maxItems":
                KEYWORD_MAX_ITEMS,
                "description":
                KEYWORD_CONTRACT_TEXT,
            },
            "should_dirty_parent": {
                "type": "boolean"
            },
        },
    },
}

_PLACEMENT_SCHEMA = {
    "name": "route_placement",
    "description": "Decide whether to stay or descend for placement.",
    "input_schema": {
        "type": "object",
        "required": ["action", "reasoning", "confidence"],
        "properties": {
            "action": {
                "type": "string",
                "enum": ["stay", "descend"],
            },
            "target_child": {
                "type": "string",
            },
            "reasoning": {
                "type": "string",
            },
            "confidence": {
                "type": "number",
            },
        },
    },
}

_SUMMARY_SCHEMA = {
    "name": "generate_summary",
    "description": "Generate concise category summary and keywords.",
    "input_schema": {
        "type": "object",
        "required": ["summary", "keywords"],
        "properties": {
            "summary": {
                "type": "string",
                "description":
                ("1-3 concise sentences covering direct children."),
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": KEYWORD_MIN_ITEMS,
                "maxItems": KEYWORD_MAX_ITEMS,
                "description": KEYWORD_CONTRACT_TEXT,
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
        lock_hint = ""
        if is_name_locked_node(n):
            lock_hint = " | skeleton: true | name_editable: false"
        lines.append(
            f"  - [id: {n.id[:8]}] type: {n.node_type.value} | "
            f"name: {n.name}{lock_hint} | content: {content[:120]}..."
        )
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
        "Skeleton guard: categories marked with `name_editable: false` are "
        "immutable in name. You may update summary/keywords, but do not "
        "rename them.\n"
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
        "updated_summary: rewrite directory summary after ops.\n"
        "updated_summary contract: 1-3 concise sentences, plain text only, "
        f"max {SUMMARY_MAX_CHARS} chars, no markdown bullets, no JSON, "
        "no field labels.\n"
        "GROUP contract: each GROUP op must provide non-empty `content` as "
        f"category summary ({GROUP_SUMMARY_SENTENCE_RANGE} concise "
        "sentences).\n"
        "GROUP keyword contract: each GROUP op should provide 2-6 semantic "
        "keywords in `keywords`.\n"
        "updated_keywords contract: MUST provide "
        f"{KEYWORD_MIN_ITEMS}-{KEYWORD_MAX_ITEMS} semantic keywords for "
        "current category in every response.\n"
        "Keyword guard: no time tokens (e.g. 15:00), no system tokens "
        "(leaf_xxx/rollup_xxx), no generic placeholders.\n"
        "If uncertain, derive keywords from major child themes.\n"
        "Summary contract: write 1-3 concise sentences that summarize all "
        "direct child content under the current category.\n"
        "Never output operation schema text into updated_summary "
        "(e.g. op_type/ids/overall_reasoning/updated_keywords).\n"
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


def build_placement_prompt(
    *,
    content: str,
    current_path: str,
    current_summary: str,
    children: tuple[dict[str, str], ...],
) -> Tuple[str, str]:
    """Build placement prompt for one recursive routing step."""
    child_lines = []
    for child in children:
        child_lines.append(
            f"- name: {child.get('name', '')} | "
            f"path: {child.get('path', '')} | "
            f"summary: {(child.get('summary', '') or '')[:140]}")
    child_block = "\n".join(child_lines) if child_lines else "- (none)"

    system = (
        "You are a placement router for SemaFS.\n"
        "Goal: choose whether new content should stay at current path "
        "or descend into one existing child category.\n"
        "Rules:\n"
        "1) action=descend only when one child has clear semantic advantage.\n"
        "2) target_child must be an existing child name/path.\n"
        "3) confidence is 0.0~1.0.\n"
        "4) If uncertain, choose stay.\n")
    user = (f"<current>\npath: {current_path}\nsummary: {current_summary}\n"
            "</current>\n\n"
            f"<content>\n{content[:500]}\n</content>\n\n"
            f"<children>\n{child_block}\n</children>\n\n"
            "Please call `route_placement`.")
    return system, user


def build_summary_prompt(snapshot: Snapshot) -> Tuple[str, str]:
    """Build summary-only prompt for category snapshot."""
    items = []
    for leaf in snapshot.leaves + snapshot.pending:
        if leaf.content:
            items.append(f"- [leaf] {leaf.content[:180]}")
    for sub in snapshot.subcategories:
        text = sub.summary or sub.name
        items.append(f"- [category:{sub.name}] {text[:180]}")
    item_block = "\n".join(items) if items else "- (empty)"

    system = ("You summarize a category in SemaFS.\n"
              "Return ONLY one tool call with fields "
              "`summary` and `keywords`.\n"
              "Rules:\n"
              f"1) {SUMMARY_SENTENCE_RANGE} concise sentences.\n"
              "2) Cover all major direct-child themes.\n"
              "3) No bullet list, no markdown headings.\n"
              f"4) Keep summary under {SUMMARY_MAX_CHARS} characters.\n"
              "5) Provide "
              f"{KEYWORD_MIN_ITEMS}-{KEYWORD_MAX_ITEMS} semantic keywords.\n"
              "6) Keywords cannot be time/system/placeholder tokens.\n")
    user = (f"<target>\npath: {snapshot.target.path.value}\n"
            f"name: {snapshot.target.name}\n"
            "</target>\n\n"
            f"<children>\n{item_block}\n</children>\n\n"
            "Please call `generate_summary`.")
    return system, user
