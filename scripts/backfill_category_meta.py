"""Backfill minimal category_meta for existing category rows."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from semafs.core.summary import build_category_meta, render_category_summary


def backfill(db_path: str, *, dry_run: bool = False) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, name, summary, category_meta
        FROM nodes
        WHERE node_type='category' AND is_archived=0
        """
    )
    rows = cur.fetchall()
    scanned = len(rows)
    updated = 0

    for row in rows:
        node_id = row["id"]
        raw_meta = row["category_meta"] or "{}"
        try:
            existing_meta = json.loads(raw_meta)
        except json.JSONDecodeError:
            existing_meta = {}
        has_keywords = isinstance(
            existing_meta.get("keywords"), list
        ) and bool(existing_meta.get("keywords"))
        has_summary = bool(str(existing_meta.get("summary", "")).strip())
        if has_keywords and has_summary:
            continue

        cur.execute(
            """
            SELECT c.summary, c.content, c.name
            FROM nodes c
            WHERE c.parent_id = ? AND c.is_archived = 0
            ORDER BY c.name ASC
            """,
            (node_id,),
        )
        child_rows = cur.fetchall()
        leaf_texts = []
        child_names = []
        for child in child_rows:
            child_names.append(child["name"])
            if child["content"]:
                leaf_texts.append(child["content"])
            elif child["summary"]:
                leaf_texts.append(child["summary"])

        meta = build_category_meta(
            raw_summary=row["summary"],
            leaf_texts=tuple(leaf_texts),
            child_names=tuple(child_names),
            keywords=tuple(existing_meta.get("keywords", []))
            if isinstance(existing_meta.get("keywords"), list) else None,
            ext=existing_meta.get("ext", {})
            if isinstance(existing_meta.get("ext"), dict) else {},
        )
        summary = render_category_summary(meta)
        updated += 1

        if dry_run:
            continue

        cur.execute(
            """
            UPDATE nodes
            SET summary = ?, category_meta = ?, updated_at=datetime('now')
            WHERE id = ?
            """,
            (summary, json.dumps(meta), node_id),
        )

    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    conn.close()
    return scanned, updated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill category_meta for category rows"
    )
    parser.add_argument("--db", default="data/semafs_real_llm.db")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = Path(args.db).resolve()
    scanned, updated = backfill(str(db), dry_run=args.dry_run)
    mode = "DRY-RUN" if args.dry_run else "APPLIED"
    print(f"{mode} scanned={scanned} updated={updated} db={db}")


if __name__ == "__main__":
    main()
