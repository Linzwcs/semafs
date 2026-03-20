"""Rename low-semantic category names to semantic ones."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

from semafs.core.rules import (
    allocate_unique_category_segment,
    is_generic_category_name,
    semantic_category_segment,
)
from semafs.infra.sqlite.store import SQLiteStore
from semafs.infra.sqlite.uow import SQLiteUnitOfWork

_TOKEN_RE = re.compile(r"[a-z]{3,}")


def _propose_name(meta_text: str, summary: str) -> str:
    try:
        meta = json.loads(meta_text or "{}")
    except json.JSONDecodeError:
        meta = {}
    raw_keywords = meta.get("keywords", [])
    if isinstance(raw_keywords, list):
        for item in raw_keywords:
            if not isinstance(item, str):
                continue
            token = semantic_category_segment(item, context_text=summary)
            if not is_generic_category_name(token):
                return token
    for token in _TOKEN_RE.findall((summary or "").lower()):
        candidate = semantic_category_segment(token, context_text=summary)
        if not is_generic_category_name(candidate):
            return candidate
    return "topic"


def _collect_targets(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, parent_id, name, canonical_path, summary, category_meta
        FROM nodes
        WHERE node_type='category' AND is_archived=0 AND canonical_path!='root'
        ORDER BY canonical_path
        """
    )
    rows = cur.fetchall()
    return [row for row in rows if is_generic_category_name(row["name"])]


def cleanup(db_path: str, *, dry_run: bool) -> tuple[int, int]:
    store = SQLiteStore(db_path)
    conn = store._get_conn()  # noqa: SLF001
    conn.row_factory = sqlite3.Row
    targets = _collect_targets(conn)
    if not targets:
        store.close()
        return 0, 0

    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, parent_id, name FROM nodes
        WHERE is_archived=0
        """
    )
    rows = cur.fetchall()
    sibling_used: dict[str, set[str]] = {}
    for row in rows:
        parent_id = row["parent_id"] or "__root__"
        sibling_used.setdefault(parent_id, set()).add(row["name"])

    planned: list[tuple[str, str, str]] = []
    for row in targets:
        node_id = row["id"]
        parent_key = row["parent_id"] or "__root__"
        old_name = row["name"]
        used = sibling_used.setdefault(parent_key, set())
        if old_name in used:
            used.remove(old_name)
        proposed = _propose_name(row["category_meta"], row["summary"] or "")
        new_name = allocate_unique_category_segment(
            proposed,
            used_names=used,
            fallback="topic",
        )
        planned.append((node_id, old_name, new_name))

    if dry_run:
        store.close()
        return len(targets), len(planned)

    uow = SQLiteUnitOfWork(conn)
    for node_id, _, new_name in planned:
        uow.register_rename(node_id, new_name)
    import asyncio
    asyncio.run(uow.commit())
    store.close()
    return len(targets), len(planned)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cleanup ambiguous category names in SQLite DB"
    )
    parser.add_argument("--db", default="data/semafs_real_llm.db")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = Path(args.db).resolve()
    scanned, renamed = cleanup(str(db), dry_run=args.dry_run)
    mode = "DRY-RUN" if args.dry_run else "APPLIED"
    print(f"{mode} ambiguous={scanned} renamed={renamed} db={db}")


if __name__ == "__main__":
    main()
