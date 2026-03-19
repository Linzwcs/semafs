"""Sanitizers for hybrid strategy LLM outputs."""

from __future__ import annotations

import logging

from ...core.raw import RawGroup, RawMerge, RawMove, RawRename
from ...core.snapshot import Snapshot

logger = logging.getLogger(__name__)


def parse_keywords(value) -> tuple[str, ...]:
    """Parse and normalize keyword list from raw payload."""
    if not isinstance(value, list):
        return ()
    parsed = []
    for item in value:
        if not isinstance(item, str):
            continue
        token = item.strip()
        if token:
            parsed.append(token)
    return tuple(parsed[:6])


def resolve_node_id(raw_id: str, snapshot: Snapshot) -> str:
    """Resolve short ID to full UUID; fallback to original value."""
    for node in snapshot.leaves + snapshot.pending + snapshot.subcategories:
        if node.id == raw_id or node.id[:8] == raw_id[:8]:
            return node.id
    return raw_id


def fallback_group_summary(ids: tuple[str, ...], snapshot: Snapshot) -> str:
    """Build non-empty fallback summary for GROUP op."""
    by_id = {}
    for node in snapshot.leaves + snapshot.pending + snapshot.subcategories:
        by_id[node.id] = node
        by_id[node.id[:8]] = node
    snippets = []
    for node_id in ids:
        node = by_id.get(node_id)
        if not node:
            continue
        text = (node.content or node.summary or "").strip()
        if text:
            snippets.append(text[:90])
        if len(snippets) >= 3:
            break
    if snippets:
        return "; ".join(snippets)
    return "Grouped related nodes under one semantic category."


def parse_raw_ops(raw_ops: list[dict], snapshot: Snapshot) -> list:
    """Parse raw LLM ops into executable raw operation objects."""
    ops = []
    for item in raw_ops:
        try:
            if not isinstance(item, dict):
                logger.warning("Skipping non-object op payload: %r", item)
                continue

            op_type = item["op_type"]
            raw_ids = item.get("ids", [])
            ids = tuple(resolve_node_id(i, snapshot) for i in raw_ids)

            if op_type == "MERGE":
                evidence = item.get("evidence", [])
                valid_evidence = tuple(
                    e.strip()
                    for e in evidence
                    if isinstance(e, str) and e.strip()
                )
                merged_content = str(item.get("content", "")).strip()
                if len(ids) < 2:
                    continue
                if not valid_evidence:
                    logger.warning(
                        "Skipping MERGE without semantic evidence: %s", item
                    )
                    continue
                if not merged_content:
                    logger.warning(
                        "Skipping MERGE without non-empty content: %s", item
                    )
                    continue
                ops.append(
                    RawMerge(
                        source_ids=ids,
                        new_content=merged_content,
                        new_name=item.get("name", ""),
                        evidence=valid_evidence,
                    )
                )
            elif op_type == "GROUP":
                if len(ids) < 2:
                    continue
                group_summary = str(item.get("content", "")).strip()
                if not group_summary:
                    group_summary = fallback_group_summary(ids, snapshot)
                ops.append(
                    RawGroup(
                        source_ids=ids,
                        category_name=item.get("name", ""),
                        category_summary=group_summary,
                    )
                )
            elif op_type == "MOVE":
                if not ids:
                    continue
                ops.append(
                    RawMove(
                        leaf_id=ids[0],
                        target_name=item.get("path_to_move", ""),
                    )
                )
            elif op_type == "RENAME":
                if not ids:
                    continue
                new_name = item.get("name", "")
                if not new_name:
                    continue
                ops.append(
                    RawRename(
                        node_id=ids[0],
                        new_name=new_name,
                    )
                )
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Failed to parse op: %s, skipping: %s", exc, item)
    return ops
