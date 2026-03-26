"""Prompt builder and tool schema for LLM-based reorganization."""

from __future__ import annotations
from dataclasses import dataclass
import json
from typing import Any, Tuple

from ...core.node import Node
from ...core.plan.ops import Plan, GroupOp, MoveOp, MergeOp, RenameOp
from ...core.rules import GENERIC_CATEGORY_NAMES, is_name_locked_node
from ...core.snapshot import Snapshot

KEYWORD_MIN_ITEMS = 2
KEYWORD_MAX_ITEMS = 6
SUMMARY_MAX_CHARS = 500
SUMMARY_SENTENCE_RANGE = "1-3"
GROUP_SUMMARY_SENTENCE_RANGE = "1-2"

SUMMARY_CONTRACT_TEXT = (
    f"{SUMMARY_SENTENCE_RANGE} concise sentences, plain text only, "
    f"max {SUMMARY_MAX_CHARS} chars, no bullets/JSON.")
GROUP_SUMMARY_CONTRACT_TEXT = (
    "For GROUP: required category summary "
    f"({GROUP_SUMMARY_SENTENCE_RANGE} sentences). For MERGE: merged content.")
KEYWORD_CONTRACT_TEXT = (f"Required semantic keywords for current category "
                         f"({KEYWORD_MIN_ITEMS}-{KEYWORD_MAX_ITEMS}). "
                         "No time tokens (e.g. 15:00), no system tokens "
                         "(e.g. leaf_xxx/rollup_xxx), no placeholders.")

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
                            "type":
                            "string",
                            "description":
                            ("For GROUP/RENAME: category name relative to "
                             "current directory. Never include parent "
                             "prefix and never repeat adjacent segments "
                             "(e.g. `a.a`). Must be readable English words; "
                             "forbid suffix-variant naming like "
                             "`worka/workb` or `worksa/worksb`."),
                        },
                        "content": {
                            "type": "string",
                            "description": GROUP_SUMMARY_CONTRACT_TEXT,
                        },
                        "keywords": {
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
                            ("For GROUP: semantic keywords for the "
                             "new category (2-6)."),
                        },
                        "path_to_move": {
                            "type":
                            "string",
                            "description":
                            ("For MOVE only: copy EXACTLY one existing path "
                             "from <available_move_targets>. Do not invent "
                             "new paths."),
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
                "type": "array",
                "items": {
                    "type": "string"
                },
                "minItems": KEYWORD_MIN_ITEMS,
                "maxItems": KEYWORD_MAX_ITEMS,
                "description": KEYWORD_CONTRACT_TEXT,
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
                "type":
                "string",
                "description":
                ("For descend only: EXACT child path from <children> "
                 "(prefer path over name)."),
            },
            "reasoning": {
                "type":
                "string",
                "description":
                ("Explain semantic anchors and why this beats alternatives."),
            },
            "confidence": {
                "type": "number",
                "description":
                "Confidence 0.0~1.0, calibrated conservatively.",
            },
            "semantic_anchors": {
                "type":
                "array",
                "items": {
                    "type": "string"
                },
                "description":
                ("Concrete shared anchors between content and target child."),
            },
            "runner_up": {
                "type":
                "string",
                "description":
                ("Optional: closest alternative child path/name if any."),
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
                "items": {
                    "type": "string"
                },
                "minItems": KEYWORD_MIN_ITEMS,
                "maxItems": KEYWORD_MAX_ITEMS,
                "description": KEYWORD_CONTRACT_TEXT,
            },
        },
    },
}

_PLAN_REVIEW_SCHEMA = {
    "name": "review_tree_ops",
    "description": "Review candidate tree_ops plan and keep only quality ops.",
    "input_schema": {
        "type":
        "object",
        "required": [
            "decision",
            "keep_op_indices",
            "drop_reasons",
            "reasoning",
            "confidence",
        ],
        "properties": {
            "decision": {
                "type": "string",
                "enum": ["accept", "revise", "reject"],
            },
            "keep_op_indices": {
                "type":
                "array",
                "items": {
                    "type": "integer"
                },
                "description":
                ("Indices of candidate_plan_ops to keep for execution."),
            },
            "drop_reasons": {
                "type":
                "array",
                "description": ("One reason entry for every dropped op index "
                                "(candidate op not in keep_op_indices). "
                                "If all ops are kept, return []."),
                "items": {
                    "type": "object",
                    "required": ["op_index", "reason", "rule"],
                    "properties": {
                        "op_index": {
                            "type": "integer"
                        },
                        "reason": {
                            "type": "string"
                        },
                        "rule": {
                            "type":
                            "string",
                            "enum": [
                                "placeholder",
                                "semantic_duplicate",
                                "weak_move",
                                "weak_merge",
                                "insufficient_evidence",
                                "low_novelty",
                                "other",
                            ],
                        },
                    },
                },
            },
            "reasoning": {
                "type": "string"
            },
            "confidence": {
                "type": "number"
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
        skeleton = "true" if bool(n.skeleton) else "false"
        editable = "true" if bool(n.name_editable) else "false"
        lines.append(
            f"  - [id: {n.id[:8]}] type: {n.node_type.value} | "
            f"name: {n.name} | skeleton: {skeleton} | "
            f"name_editable: {editable} | content: {content[:120]}...")
    return "\n".join(lines) + "\n\nNote: use id to identify nodes, not name."


def _format_plan_op_list(plan: Plan) -> str:
    """Compact op list for structure review prompt."""
    if not plan.ops:
        return "  (empty)"
    lines = []
    for idx, op in enumerate(plan.ops):
        if isinstance(op, GroupOp):
            lines.append(
                f"  - idx:{idx} | GROUP | path:{op.category_path} | "
                f"ids:{len(op.source_ids)} | summary:{op.category_summary[:90]}"
            )
            continue
        if isinstance(op, MoveOp):
            lines.append(f"  - idx:{idx} | MOVE | leaf_id:{op.leaf_id[:8]} | "
                         f"target:{op.target_path}")
            continue
        if isinstance(op, MergeOp):
            lines.append(f"  - idx:{idx} | MERGE | ids:{len(op.source_ids)} | "
                         f"name:{op.new_name}")
            continue
        if isinstance(op, RenameOp):
            lines.append(
                f"  - idx:{idx} | RENAME | node_id:{op.node_id[:8]} | "
                f"new_name:{op.new_name}")
            continue
        lines.append(f"  - idx:{idx} | {type(op).__name__}")
    return "\n".join(lines)


@dataclass
class _PromptLeafView:
    id: str
    name: str
    content: str
    kind: str


@dataclass
class _PromptCategoryView:
    path: str
    name: str
    summary: str = ""
    keywords: tuple[str, ...] = ()
    locked: bool = False
    current: bool = False
    fresh: bool = False


@dataclass
class _PromptTreeState:
    current_path: str
    categories: dict[str, _PromptCategoryView]
    leaf_buckets: dict[str, list[_PromptLeafView]]


def _compact_text(text: str, limit: int = 96) -> str:
    """Collapse whitespace and trim long text for prompt display."""
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit - 3].rstrip() + "..."


def _leaf_kind(node: Node) -> str:
    """Map node stage to a stable display kind."""
    stage = getattr(node.stage, "value", "active")
    if stage == "pending":
        return "pending"
    if stage == "cold":
        return "cold"
    return "leaf"


def _category_keyword_preview(node: Node | _PromptCategoryView) -> str:
    """Render a short keyword preview from category metadata."""
    raw: tuple[str, ...] | list[str] | tuple[Any, ...]
    if isinstance(node, Node):
        raw_meta = node.category_meta.get("keywords")
        if not isinstance(raw_meta, (list, tuple)):
            return ""
        raw = raw_meta
    else:
        raw = node.keywords
    items: list[str] = []
    seen = set()
    for item in raw:
        text = _compact_text(str(item), limit=24)
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
        if len(items) >= 4:
            break
    return ", ".join(items)


def _format_tree_category(
    node: Node | _PromptCategoryView,
    *,
    current: bool = False,
) -> str:
    """Render one category label in the snapshot tree."""
    if isinstance(node, Node):
        path = node.path.value
        name = "root" if path == "root" else node.name
        summary = node.summary or ""
        locked = is_name_locked_node(node)
        fresh = False
    else:
        path = node.path
        name = "root" if path == "root" else node.name
        summary = node.summary
        locked = node.locked
        fresh = node.fresh
        current = current or node.current
    if fresh:
        name = f"{name} (new)"
    if current:
        name = f"{name} (current)"
    parts = [name]
    compact_summary = _compact_text(summary)
    if compact_summary:
        parts.append(f"summary: {compact_summary}")
    keywords = _category_keyword_preview(node)
    if keywords:
        parts.append(f"keywords: {keywords}")
    if locked:
        parts.append("name_editable: false")
    return " | ".join(parts)


def _format_tree_leaf(
    node: Node | _PromptLeafView,
    *,
    kind: str | None = None,
) -> str:
    """Render one leaf label in the snapshot tree."""
    if isinstance(node, Node):
        display_kind = kind or _leaf_kind(node)
        content = node.content or ""
        name = node.name
    else:
        display_kind = kind or node.kind
        content = node.content
        name = node.name
    compact_content = _compact_text(content)
    return f"[{display_kind}] {name} | content: {compact_content or '(empty)'}"


def _make_prompt_leaf(node: Node) -> _PromptLeafView:
    """Convert snapshot leaf node to local prompt view."""
    return _PromptLeafView(
        id=node.id,
        name=node.name,
        content=node.content or "",
        kind=_leaf_kind(node),
    )


def _make_prompt_category(
    node: Node,
    *,
    current: bool = False,
    fresh: bool = False,
) -> _PromptCategoryView:
    """Convert snapshot category node to local prompt view."""
    raw_keywords = node.category_meta.get("keywords")
    if not isinstance(raw_keywords, (list, tuple)):
        raw_keywords = ()
    return _PromptCategoryView(
        path=node.path.value,
        name=node.name,
        summary=node.summary or "",
        keywords=tuple(str(item) for item in raw_keywords),
        locked=is_name_locked_node(node),
        current=current,
        fresh=fresh,
    )


def _build_prompt_tree_state(snapshot: Snapshot) -> _PromptTreeState:
    """Build base local tree state from snapshot."""
    categories = {
        snapshot.target.path.value: _make_prompt_category(
            snapshot.target,
            current=True,
        )
    }
    for sub in snapshot.subcategories:
        categories[sub.path.value] = _make_prompt_category(sub)
    leaf_buckets = {
        snapshot.target.path.value: [
            *(_make_prompt_leaf(leaf) for leaf in snapshot.leaves),
            *(_make_prompt_leaf(leaf) for leaf in snapshot.pending),
            *(_make_prompt_leaf(leaf) for leaf in snapshot.cold_leaves),
        ]
    }
    return _PromptTreeState(
        current_path=snapshot.target.path.value,
        categories=categories,
        leaf_buckets=leaf_buckets,
    )


def _clone_tree_state(state: _PromptTreeState) -> _PromptTreeState:
    """Clone tree state for predicted after-view rendering."""
    return _PromptTreeState(
        current_path=state.current_path,
        categories={
            path: _PromptCategoryView(
                path=view.path,
                name=view.name,
                summary=view.summary,
                keywords=view.keywords,
                locked=view.locked,
                current=view.current,
                fresh=view.fresh,
            )
            for path, view in state.categories.items()
        },
        leaf_buckets={
            path: [
                _PromptLeafView(
                    id=leaf.id,
                    name=leaf.name,
                    content=leaf.content,
                    kind=leaf.kind,
                )
                for leaf in leaves
            ]
            for path, leaves in state.leaf_buckets.items()
        },
    )


def _path_in_scope(path: str, root_path: str) -> bool:
    """Check whether a path stays inside current snapshot subtree."""
    return path == root_path or path.startswith(f"{root_path}.")


def _path_name(path: str) -> str:
    """Extract terminal segment from path."""
    if path == "root":
        return "root"
    return path.rsplit(".", 1)[-1]


def _ensure_tree_category(
    state: _PromptTreeState,
    path: str,
    *,
    summary: str = "",
    keywords: tuple[str, ...] = (),
    fresh: bool = False,
) -> None:
    """Ensure local category path exists in predicted tree."""
    if not _path_in_scope(path, state.current_path):
        return
    if path == state.current_path:
        target_view = state.categories.get(path)
        if target_view and summary and not target_view.summary:
            target_view.summary = summary
        return

    root_segments = state.current_path.split(".")
    full_segments = path.split(".")
    for idx in range(len(root_segments), len(full_segments)):
        subpath = ".".join(full_segments[:idx + 1])
        existing = state.categories.get(subpath)
        if existing is None:
            state.categories[subpath] = _PromptCategoryView(
                path=subpath,
                name=full_segments[idx],
                summary=summary if subpath == path else "",
                keywords=keywords if subpath == path else (),
                fresh=fresh,
            )
            continue
        if subpath == path:
            if summary and not existing.summary:
                existing.summary = summary
            if keywords and not existing.keywords:
                existing.keywords = keywords


def _remove_leaf_from_tree(
    state: _PromptTreeState,
    leaf_id: str,
) -> _PromptLeafView | None:
    """Remove one leaf by id from predicted tree."""
    for leaves in state.leaf_buckets.values():
        for idx, leaf in enumerate(leaves):
            if leaf.id == leaf_id:
                removed = leaf
                del leaves[idx]
                return removed
    return None


def _add_leaf_to_tree(
    state: _PromptTreeState,
    parent_path: str,
    leaf: _PromptLeafView,
) -> None:
    """Insert leaf into one category bucket if still local."""
    if not _path_in_scope(parent_path, state.current_path):
        return
    _ensure_tree_category(state, parent_path)
    state.leaf_buckets.setdefault(parent_path, []).append(leaf)


def _rename_tree_category(
    state: _PromptTreeState,
    old_path: str,
    new_name: str,
) -> str:
    """Rename one local category path and descendants."""
    if old_path not in state.categories or old_path == "root":
        return old_path

    parent_path = old_path.rsplit(".", 1)[0]
    new_path = f"{parent_path}.{new_name}"
    remapped_categories: dict[str, _PromptCategoryView] = {}
    for path, view in state.categories.items():
        if path == old_path or path.startswith(f"{old_path}."):
            suffix = path[len(old_path):]
            replaced = f"{new_path}{suffix}"
            remapped_categories[replaced] = _PromptCategoryView(
                path=replaced,
                name=new_name if path == old_path else _path_name(replaced),
                summary=view.summary,
                keywords=view.keywords,
                locked=view.locked,
                current=view.current,
                fresh=view.fresh,
            )
            continue
        remapped_categories[path] = view
    state.categories = remapped_categories

    remapped_buckets: dict[str, list[_PromptLeafView]] = {}
    for path, leaves in state.leaf_buckets.items():
        if path == old_path or path.startswith(f"{old_path}."):
            suffix = path[len(old_path):]
            remapped_buckets[f"{new_path}{suffix}"] = leaves
            continue
        remapped_buckets[path] = leaves
    state.leaf_buckets = remapped_buckets

    if state.current_path == old_path or state.current_path.startswith(f"{old_path}."):
        state.current_path = f"{new_path}{state.current_path[len(old_path):]}"
    return new_path


def _render_tree_line(
    lines: list[str],
    prefix: str,
    *,
    last: bool,
    label: str,
) -> str:
    """Append one unicode tree line and return child prefix."""
    branch = "└─ " if last else "├─ "
    lines.append(f"{prefix}{branch}{label}")
    return prefix + ("   " if last else "│  ")


def _render_tree_subtree(
    lines: list[str],
    state: _PromptTreeState,
    *,
    prefix: str,
    parent_path: str,
) -> None:
    """Render one subtree from predicted or current local tree state."""
    child_categories = sorted(
        [
            view
            for path, view in state.categories.items()
            if path != parent_path and path.rsplit(".", 1)[0] == parent_path
        ],
        key=lambda view: view.name,
    )
    child_leaves = sorted(
        state.leaf_buckets.get(parent_path, []),
        key=lambda leaf: (leaf.kind, leaf.name),
    )
    entries: list[tuple[str, _PromptCategoryView | _PromptLeafView]] = [
        *[("category", view) for view in child_categories],
        *[("leaf", leaf) for leaf in child_leaves],
    ]
    if not entries:
        _render_tree_line(lines, prefix, last=True, label="(empty)")
        return

    for idx, (kind, item) in enumerate(entries):
        child_prefix = _render_tree_line(
            lines,
            prefix,
            last=idx == len(entries) - 1,
            label=(
                _format_tree_category(item)
                if kind == "category"
                else _format_tree_leaf(item)
            ),
        )
        if kind == "category":
            _render_tree_subtree(
                lines,
                state,
                prefix=child_prefix,
                parent_path=item.path,
            )


def _render_snapshot_tree_with_state(
    snapshot: Snapshot,
    state: _PromptTreeState,
) -> str:
    """Render ancestor chain, sibling context, and current subtree."""
    lines: list[str] = []
    if snapshot.target.path.value == "root":
        child_prefix = _render_tree_line(
            lines,
            "",
            last=True,
            label=_format_tree_category(state.categories[state.current_path]),
        )
        _render_tree_subtree(
            lines,
            state,
            prefix=child_prefix,
            parent_path=state.current_path,
        )
        return "\n".join(lines)

    ancestors_from_root = list(reversed(snapshot.ancestors))
    parent_prefix = ""
    if ancestors_from_root:
        parent_prefix = _render_tree_line(
            lines,
            "",
            last=True,
            label=_format_tree_category(ancestors_from_root[0]),
        )
        for anc in ancestors_from_root[1:]:
            parent_prefix = _render_tree_line(
                lines,
                parent_prefix,
                last=True,
                label=_format_tree_category(anc),
            )

    current_view = state.categories[state.current_path]
    peers: list[tuple[str, Node | _PromptCategoryView]] = [
        ("node", sibling) for sibling in snapshot.siblings
    ]
    peers.append(("view", current_view))
    peers.sort(key=lambda item: item[1].name)

    for idx, (kind, item) in enumerate(peers):
        child_prefix = _render_tree_line(
            lines,
            parent_prefix,
            last=idx == len(peers) - 1,
            label=_format_tree_category(item),
        )
        if kind == "view":
            _render_tree_subtree(
                lines,
                state,
                prefix=child_prefix,
                parent_path=state.current_path,
            )
    return "\n".join(lines)


def _build_snapshot_tree(snapshot: Snapshot) -> str:
    """Render one integrated local tree using all snapshot components."""
    return _render_snapshot_tree_with_state(
        snapshot,
        _build_prompt_tree_state(snapshot),
    )


def _preview_after_structure(snapshot: Snapshot, plan: Plan) -> str:
    """Generate minimal after-preview for local structure changes."""
    if not plan.ops:
        return "  (no change)"
    lines = []
    for op in plan.ops:
        if isinstance(op, GroupOp):
            lines.append(f"  - category+: {op.category_path}")
        elif isinstance(op, MoveOp):
            lines.append(f"  - move-> {op.target_path}")
        elif isinstance(op, MergeOp):
            lines.append("  - leaf_count: reduce by 1")
        elif isinstance(op, RenameOp):
            lines.append(f"  - rename-> {op.new_name}")
    return "\n".join(lines) if lines else "  (no structural hint)"


def _build_tree_before_partial(snapshot: Snapshot) -> str:
    """Render partial local tree before applying plan."""
    lines = [f"- target: {snapshot.target.path.value}"]
    lines.append(f"- direct_categories ({len(snapshot.subcategories)}):")
    if snapshot.subcategories:
        for sub in sorted(snapshot.subcategories, key=lambda n: n.path.value):
            lines.append(
                f"  - {sub.path.value} | summary: {(sub.summary or '')[:120]}"
            )
    else:
        lines.append("  - (none)")

    active_leaf_ids = ", ".join(n.id[:8] for n in snapshot.leaves) or "(none)"
    pending_leaf_ids = ", ".join(n.id[:8] for n in snapshot.pending) or "(none)"
    lines.append(f"- direct_active_leaves ({len(snapshot.leaves)}): {active_leaf_ids}")
    lines.append(f"- direct_pending_leaves ({len(snapshot.pending)}): {pending_leaf_ids}")
    return "\n".join(lines)


def _build_tree_after_partial(snapshot: Snapshot, plan: Plan) -> str:
    """Predict local tree after applying candidate plan."""
    state = _clone_tree_state(_build_prompt_tree_state(snapshot))
    category_paths_by_id = {
        snapshot.target.id: snapshot.target.path.value,
        **{sub.id: sub.path.value for sub in snapshot.subcategories},
    }

    for op in plan.ops:
        if isinstance(op, GroupOp):
            if not _path_in_scope(op.category_path, state.current_path):
                continue
            _ensure_tree_category(
                state,
                op.category_path,
                summary=op.category_summary,
                keywords=op.category_keywords,
                fresh=True,
            )
            for source_id in op.source_ids:
                leaf = _remove_leaf_from_tree(state, source_id)
                if leaf is not None:
                    _add_leaf_to_tree(state, op.category_path, leaf)
            continue

        if isinstance(op, MoveOp):
            leaf = _remove_leaf_from_tree(state, op.leaf_id)
            if leaf is None:
                continue
            if _path_in_scope(op.target_path, state.current_path):
                _ensure_tree_category(state, op.target_path)
                _add_leaf_to_tree(state, op.target_path, leaf)
            continue

        if isinstance(op, MergeOp):
            removed_any = False
            for source_id in op.source_ids:
                removed = _remove_leaf_from_tree(state, source_id)
                if removed is not None:
                    removed_any = True
            if removed_any:
                _add_leaf_to_tree(
                    state,
                    state.current_path,
                    _PromptLeafView(
                        id=f"merged:{op.new_name}",
                        name=op.new_name,
                        content=op.new_content,
                        kind="leaf",
                    ),
                )

    for op in plan.ops:
        if not isinstance(op, RenameOp):
            continue
        old_path = category_paths_by_id.get(op.node_id)
        if not old_path or old_path not in state.categories:
            continue
        new_path = _rename_tree_category(state, old_path, op.new_name)
        for node_id, path in list(category_paths_by_id.items()):
            if path == old_path or path.startswith(f"{old_path}."):
                category_paths_by_id[node_id] = f"{new_path}{path[len(old_path):]}"

    if plan.updated_name and state.current_path in state.categories:
        state.categories[state.current_path].name = plan.updated_name

    return _render_snapshot_tree_with_state(snapshot, state)


def build_prompt(
        snapshot: Snapshot,
        *,
        retry_feedback: dict[str, Any] | None = None,
        frozen_ops: tuple[dict[str, Any], ...] = (),
) -> Tuple[str, str]:
    blocked_names = ", ".join(f"`{name}`"
                              for name in sorted(GENERIC_CATEGORY_NAMES))
    """Build (system, user) prompts from Snapshot."""
    all_nodes = list(snapshot.leaves) + list(snapshot.pending)
    total = len(all_nodes) + len(snapshot.subcategories)
    budget = snapshot.budget

    sub_cats = list(snapshot.subcategories)
    available_paths = "\n".join(f"  * {c.path.value}"
                                for c in sub_cats) or "  (no subcategories)"
    forbidden_group_names = []
    seen_forbidden = set()
    for raw_name in [snapshot.target.name] + [c.name for c in sub_cats]:
        name = (raw_name or "").strip().lower()
        if not name or name in seen_forbidden:
            continue
        seen_forbidden.add(name)
        forbidden_group_names.append(name)
    forbidden_group_block = "\n".join(
        f"  - {name}" for name in forbidden_group_names) or "  (none)"

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
            display_name = "root" if anc.path.value == "root" else anc.name
            chain.append(f"{indent}└─ {display_name}: {summary}")
        current_display = ("root" if snapshot.target.path.value == "root" else
                           snapshot.target.name)
        ancestor_info = ("\n<hierarchical_context>\n" + "\n".join(chain) +
                         "\n" + ("  " * len(snapshot.ancestors)) +
                         f"└─ {current_display} (current)\n" +
                         "</hierarchical_context>")
    snapshot_tree = _build_snapshot_tree(snapshot)
    target_locked_rule = ""
    if is_name_locked_node(snapshot.target):
        target_locked_rule = (
            "Current target category is name-locked. "
            "You MUST set `updated_name` to null.\n"
        )

    system_prompt = (
        "You are a knowledge graph scheduling engine running inside SemaFS.\n"
        f"Core responsibility: Semantically cluster and reduce "
        f"nodes under {budget.soft}.\n\n"
        "Operation priority: MOVE > GROUP > MERGE.\n"
        "MOVE: node fits existing subcategory. "
        "GROUP: related nodes, but only when no existing category fits. "
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
        f"{target_locked_rule}"
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
        "Mandatory reuse rule: for every coherent subset of leaves that "
        "matches an existing subcategory, you MUST move those leaf ids to that "
        "existing path (MOVE). You MUST NOT create a new GROUP for that subset.\n"
        "Anti-duplicate rule: if a candidate GROUP overlaps with an existing "
        "subcategory (similar name/theme/summary), DO NOT create a new "
        "category. Reuse existing category via one or more MOVE ops.\n"
        "High-overlap rule: when semantic overlap with an existing "
        "subcategory is high, ALWAYS use MOVE into that existing path. "
        "Do not create a parallel sibling GROUP; the existing category will "
        "self-organize in later reconcile rounds.\n"
        "GROUP partition rule: sibling GROUP categories under the same "
        "parent must be semantically disjoint. If two candidate GROUPs share "
        "major entities/events/intents, keep only one and MOVE nodes into "
        "the stronger existing/broader category.\n"
        "GROUP fallback-only rule: use GROUP only if no existing subcategory "
        "can absorb the candidate leaves with comparable semantics.\n"
        "Expansion rule: if an existing category is too narrow but new data "
        "shows a broader umbrella is better (e.g. `database` -> `practice`), "
        "prefer RENAME existing category to umbrella and MOVE relevant leaves, "
        "instead of creating another overlapping GROUP.\n"
        "MOVE target guard: `path_to_move` must be copied exactly from "
        "<available_move_targets>; never compose new path strings.\n"
        "Relative naming guard: names must be relative to current directory; "
        "never repeat parent prefix.\n"
        "Duplicate segment guard: never output adjacent repeated path "
        "segments in category names "
        "(e.g. `bestpractices.bestpractices`).\n"
        "Stacked-duplicate guard: never create parent/child chains whose "
        "adjacent segments are lexical or semantic variants of each other "
        "(e.g. `practice.practices`, `policy.policies`, "
        "`process.processes`). If child meaning mostly repeats parent, do not "
        "add another level.\n"
        "Semantic redundancy guard: first new segment must not be lexical "
        "variant of current category or existing siblings "
        "(e.g. under `bestpractices`, avoid `practices`; "
        "under `processes`, avoid `processes`).\n"
        "GROUP forbidden-list guard: first segment in GROUP `name` must not "
        "be equal or lexical variant of any token in "
        "<forbidden_group_names> (includes current category and existing "
        "subcategories).\n"
        "Hierarchy economy: prefer single-segment GROUP names; use dotted "
        "hierarchy only when each segment adds distinct meaning.\n"
        "Suffix-variant naming ban: never create sibling categories that only "
        "differ by trailing letters/digits "
        "(e.g. `worka/workb`, `worksa/worksb`, `topic1/topic2`).\n"
        "Category naming guard: each category segment must be "
        "a single readable English word (`^[a-z]+$`). You may use dotted "
        "recursive paths like "
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
        "updated_name readability: choose a readable common English word; "
        "forbid fabricated suffix variants like `worksa`/`worksb`.\n"
        "updated_name guard: do NOT rename current category to a name that "
        "duplicates or nearly duplicates its parent or a direct child/new "
        "child segment. Invalid examples: `root.techniques.techniques`, "
        "`root.practice.practices`.\n"
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
        "If <retry_feedback> is provided, treat `must_fix` as hard failures "
        "from previous attempt and avoid repeating them.\n"
        "If <frozen_ops> is provided, keep them semantically stable and "
        "focus new ops on unresolved problems.\n"
        "Read <snapshot_tree> as the canonical local structure view: "
        "ancestor chain, siblings, current category, and direct children are "
        "shown together there.\n"
        "should_dirty_parent: true if major new themes extracted.")

    status_warning = ""
    if total > budget.soft:
        status_warning = (
            f"CRITICAL: Node count ({total}) exceeds limit ({budget.soft}). "
            "You MUST perform MOVE to existing subcategories or MERGE "
            "(GROUP only as last fallback when no existing subcategory fits).")
    elif snapshot.pending:
        status_warning = (
            "New fragments arrived. Consider proactive organization.")

    target_path = snapshot.target.path.value
    target_summary = snapshot.target.summary or "(empty)"
    target_skeleton = "true" if bool(snapshot.target.skeleton) else "false"
    target_name_editable = ("true" if bool(snapshot.target.name_editable)
                            else "false")

    user_content = (f"<directory_status>\n"
                    f"- current_path: \"{target_path}\"\n"
                    f"- capacity: {total}/{budget.soft}\n"
                    f"- skeleton: {target_skeleton}\n"
                    f"- name_editable: {target_name_editable}\n"
                    f"- alert: {status_warning}\n"
                    f"</directory_status>\n\n"
                    f"<current_directory_summary>\n{target_summary}\n"
                    f"</current_directory_summary>\n"
                    "<forbidden_group_names>\n"
                    f"{forbidden_group_block}\n"
                    "</forbidden_group_names>\n"
                    f"{sibling_info}{ancestor_info}\n"
                    "<snapshot_tree>\n"
                    f"{snapshot_tree}\n"
                    "</snapshot_tree>\n\n"
                    "<available_move_targets>\n"
                    f"{available_paths}\n"
                    "</available_move_targets>\n\n"
                    f"<existing_subcategories>\n"
                    f"{_format_node_list(list(snapshot.subcategories))}\n"
                    f"</existing_subcategories>\n\n"
                    f"<existing_active_nodes>\n"
                    f"{_format_node_list(list(snapshot.leaves))}\n"
                    f"</existing_active_nodes>\n\n"
                    f"<new_pending_fragments>\n"
                    f"{_format_node_list(list(snapshot.pending))}\n"
                    f"</new_pending_fragments>\n\n"
                    "Please call `tree_ops` with your reorganization plan.")

    retry_block = ""
    if retry_feedback:
        retry_text = json.dumps(retry_feedback, ensure_ascii=False, indent=2)
        retry_block = ("\n\n<retry_feedback>\n"
                       f"{retry_text}\n"
                       "</retry_feedback>")

    frozen_block = ""
    if frozen_ops:
        frozen_preview = "\n".join(
            f"  - {json.dumps(item, ensure_ascii=False)}"
            for item in frozen_ops[:12])
        frozen_block = ("\n\n<frozen_ops>\n"
                        f"{frozen_preview}\n"
                        "</frozen_ops>")

    user_content = user_content + retry_block + frozen_block

    return (system_prompt, user_content)


def build_placement_prompt(
    *,
    content: str,
    current_path: str,
    current_summary: str,
    children: tuple[dict[str, Any], ...],
) -> Tuple[str, str]:
    """Build placement prompt for one recursive routing step."""
    child_lines = []
    for child in children:
        kws = (child.get("keywords", "") or "").strip()
        kw_part = f" | keywords: {kws}" if kws else ""
        skeleton = "true" if bool(child.get("skeleton", False)) else "false"
        editable = "true" if bool(child.get("name_editable", True)) else "false"
        child_lines.append(f"- name: {child.get('name', '')} | "
                           f"path: {child.get('path', '')} | "
                           f"summary: {(child.get('summary', '') or '')[:512]}"
                           f"{kw_part} | skeleton: {skeleton} | "
                           f"name_editable: {editable}")
    child_block = "\n".join(child_lines) if child_lines else "- (none)"

    system = (
        "You are a placement router for SemaFS.\n"
        "Goal: choose whether new content should stay at current path "
        "or descend into one existing child category.\n"
        "Core policy: conservative routing. Wrong descend is worse than stay.\n"
        "Hard rules:\n"
        "1) Choose `descend` only when one child is a clear semantic winner.\n"
        "2) Clear winner means: concrete shared anchors with content, and "
        "no close competitor among other children.\n"
        "3) If two or more children are plausible, choose `stay`.\n"
        "4) If evidence is weak/ambiguous, choose `stay`.\n"
        "5) `target_child` must be copied exactly from child `path` "
        "(prefer path, not name).\n"
        "6) `reasoning` must mention anchors and why alternatives lose.\n"
        "7) Confidence calibration:\n"
        "   - 0.90-1.00: near-certain, multiple strong anchors and clear gap.\n"
        "   - 0.70-0.89: strong but some uncertainty.\n"
        "   - 0.50-0.69: ambiguous; usually should be `stay`.\n"
        "   - <0.50: weak evidence; must be `stay`.\n"
        "8) Never invent child names or paths.\n")
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
            items.append(f"- [leaf] {leaf.content[:1024]}")
    for sub in snapshot.subcategories:
        text = sub.summary or sub.name
        items.append(f"- [category:{sub.name}] {text[:1024]}")
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


def build_plan_review_prompt(snapshot: Snapshot,
                             plan: Plan) -> Tuple[str, str]:
    """Build prompt for LLM structure review before plan execution."""
    ancestors = []
    for anc in reversed(snapshot.ancestors):
        name = "root" if anc.path.value == "root" else anc.name
        summary = (anc.summary or "")[:1024] + "..."
        ancestors.append(f"  - {name}: {summary}")
    ancestor_block = "\n".join(ancestors) if ancestors else "  (none)"

    subs = []
    for sub in snapshot.subcategories:
        subs.append(f"  - {sub.name}: {(sub.summary or '')[:256]}")
    sub_block = "\n".join(subs) if subs else "  (none)"
    before_partial = _build_tree_before_partial(snapshot)
    after_partial = _build_tree_after_partial(snapshot, plan)
    snapshot_tree = _build_snapshot_tree(snapshot)

    system = (
        "You are a plan quality reviewer for SemaFS.\n"
        "Task: review candidate ops and keep only those that improve local "
        "tree quality.\n"
        "You must use ALL provided snapshot context, especially "
        "<snapshot_tree_before> and <tree_after_partial_predicted>; both are "
        "tree-form local structures with sibling context.\n"
        "Primary criteria:\n"
        "1) GROUP creates strongly independent category semantics.\n"
        "2) Tree structure remains clear, compact, and non-redundant.\n"
        "Reject ops that create placeholder or low-novelty categories, "
        "semantic duplicates with parent/siblings, or weakly justified moves.\n"
        "When GROUP semantically overlaps existing subcategory, drop GROUP "
        "and prefer MOVE ops into that existing path.\n"
        "Mandatory MOVE enforcement: if a GROUP's source leaves can be mapped "
        "to an existing subcategory, that GROUP must be dropped and those "
        "leaves must be moved to the existing path.\n"
        "If candidate plan lacks such MOVE ops, reject the plan "
        "(decision=revise or reject) instead of accepting overlapping GROUP.\n"
        "When semantic overlap is high, ALWAYS keep MOVE-to-existing and drop "
        "new sibling GROUP; existing directory should absorb first and "
        "self-organize later.\n"
        "If two candidate GROUP ops under the same parent overlap in "
        "scope/theme, keep at most one and drop the others as overlap.\n"
        "If proposed GROUP semantics are mostly a subset of an existing "
        "subcategory (e.g. `database` vs existing `practice` covering "
        "database practices), drop GROUP and prefer MOVE.\n"
        "Hard structural invalid examples that must be dropped:\n"
        "- suffix variants like `worka/workb`, `worksa/worksb`, `topica/topicb`\n"
        "- repeated segments like `root.work.work` or `x.y.x`\n"
        "- stacked near-duplicate chains like `root.practice.practices` or "
        "`root.policy.policies`\n"
        "- updated_name creating `root.techniques.techniques`\n"
        "Hard rule: reject GROUP ops whose first new segment is placeholder-like "
        "(e.g. `topic`, `topica`, `topicb`, `category`, `cluster`).\n"
        "Output contract:\n"
        "1) keep_op_indices lists ONLY kept ops.\n"
        "2) For EVERY dropped op, you MUST add one drop_reasons entry with "
        "op_index + concrete reason + rule.\n"
        "3) Do not use vague reasons like 'low quality' without specifics.\n"
        "Be conservative: if uncertain about an op quality, drop that op.\n"
        "Return ONLY one tool call.")
    user = (
        f"<current_category>\n"
        f"path: {snapshot.target.path.value}\n"
        f"name: {snapshot.target.name}\n"
        f"summary: {(snapshot.target.summary or '')[:]}\n"
        f"</current_category>\n\n"
        f"<ancestor_chain>\n{ancestor_block}\n</ancestor_chain>\n\n"
        f"<snapshot_tree_before>\n{snapshot_tree}\n</snapshot_tree_before>\n\n"
        f"<existing_subcategories>\n{sub_block}\n</existing_subcategories>\n\n"
        f"<tree_before_partial>\n{before_partial}\n</tree_before_partial>\n\n"
        f"<tree_after_partial_predicted>\n{after_partial}\n"
        f"</tree_after_partial_predicted>\n\n"
        f"<candidate_plan_ops>\n{_format_plan_op_list(plan)}\n"
        f"</candidate_plan_ops>\n\n"
        f"<after_preview>\n{_preview_after_structure(snapshot, plan)}\n"
        f"</after_preview>\n\n"
        "Please call `review_tree_ops`.")
    return system, user
