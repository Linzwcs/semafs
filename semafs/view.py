import argparse
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

from .logging_utils import configure_logging

logger = logging.getLogger(__name__)

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse
    import uvicorn
except ImportError:
    logging.basicConfig(
        level=logging.ERROR,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logger.error("Required: pip install fastapi uvicorn")
    raise SystemExit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Database Layer
# ─────────────────────────────────────────────────────────────────────────────


class NodeDB:
    """Optimized database access for large-scale trees."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_node(self, node_id: str) -> Optional[dict]:
        """Get single node by ID."""
        with self._conn() as conn:
            cur = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id, ))
            row = cur.fetchone()
            return self._row_to_dict(row) if row else None

    def get_node_by_path(self, path: str) -> Optional[dict]:
        """Get single node by path."""
        with self._conn() as conn:
            cur = conn.execute("SELECT * FROM nodes WHERE canonical_path = ?",
                               (path, ))
            row = cur.fetchone()
            return self._row_to_dict(row) if row else None

    def get_children(self,
                     parent_id: str,
                     offset: int = 0,
                     limit: int = 50) -> dict:
        """Get paginated children of a node."""
        with self._conn() as conn:
            # Count total
            cur = conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE parent_id = ? AND stage != 'archived'",
                (parent_id, ))
            total = cur.fetchone()[0]

            # Fetch page
            cur = conn.execute(
                """SELECT * FROM nodes
                   WHERE parent_id = ? AND stage != 'archived'
                   ORDER BY node_type DESC, name
                   LIMIT ? OFFSET ?""", (parent_id, limit, offset))
            children = [self._row_to_dict(r) for r in cur.fetchall()]

            return {
                "items": children,
                "total": total,
                "offset": offset,
                "limit": limit
            }

    def get_root(self) -> Optional[dict]:
        """Get root node."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT * FROM nodes WHERE canonical_path = 'root'")
            row = cur.fetchone()
            return self._row_to_dict(row) if row else None

    def search(self, query: str, offset: int = 0, limit: int = 50) -> dict:
        """Full-text search across nodes."""
        with self._conn() as conn:
            pattern = f"%{query}%"
            # Count
            cur = conn.execute(
                """SELECT COUNT(*) FROM nodes
                   WHERE stage != 'archived'
                   AND (name LIKE ? OR content LIKE ? OR summary LIKE ?)""",
                (pattern, pattern, pattern))
            total = cur.fetchone()[0]

            # Fetch
            cur = conn.execute(
                """SELECT * FROM nodes
                   WHERE stage != 'archived'
                   AND (name LIKE ? OR content LIKE ? OR summary LIKE ?)
                   ORDER BY canonical_path
                   LIMIT ? OFFSET ?""",
                (pattern, pattern, pattern, limit, offset))
            items = [self._row_to_dict(r) for r in cur.fetchall()]

            return {
                "items": items,
                "total": total,
                "offset": offset,
                "limit": limit,
                "query": query
            }

    def get_stats(self) -> dict:
        """Get database statistics."""
        with self._conn() as conn:
            stats = {}
            cur = conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE stage != 'archived'")
            stats["total"] = cur.fetchone()[0]

            cur = conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE node_type = 'category' AND stage != 'archived'"
            )
            stats["categories"] = cur.fetchone()[0]

            cur = conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE node_type = 'leaf' AND stage != 'archived'"
            )
            stats["leaves"] = cur.fetchone()[0]

            cur = conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE stage = 'pending'")
            stats["pending"] = cur.fetchone()[0]

            cur = conn.execute(
                "SELECT MAX(LENGTH(canonical_path) - LENGTH(REPLACE(canonical_path, '.', ''))) FROM nodes"
            )
            stats["max_depth"] = cur.fetchone()[0] or 0

            return stats

    def get_ancestors(self, node_id: str) -> list:
        """Get ancestor chain for breadcrumb."""
        ancestors = []
        with self._conn() as conn:
            current_id = node_id
            while current_id:
                cur = conn.execute("SELECT * FROM nodes WHERE id = ?",
                                   (current_id, ))
                row = cur.fetchone()
                if not row:
                    break
                ancestors.insert(0, self._row_to_dict(row))
                current_id = row["parent_id"]
        return ancestors

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        keywords: list[str] = []
        if row["node_type"] == "category":
            category_meta_raw = row["category_meta"] if "category_meta" in row.keys(
            ) else "{}"
            try:
                category_meta = json.loads(category_meta_raw or "{}")
            except json.JSONDecodeError:
                category_meta = {}

            raw_keywords = category_meta.get("keywords", [])
            if isinstance(raw_keywords, (list, tuple)):
                seen: set[str] = set()
                normalized: list[str] = []
                for value in raw_keywords:
                    token = str(value).strip()
                    if not token or token in seen:
                        continue
                    seen.add(token)
                    normalized.append(token)
                keywords = normalized

        return {
            "id": row["id"],
            "parent_id": row["parent_id"],
            "name": row["name"],
            "path": row["canonical_path"],
            "type": row["node_type"],
            "stage": row["stage"],
            "content": row["content"] or row["summary"] or "",
            "keywords": keywords,
            "tags": json.loads(row["tags"] or "[]"),
            "skeleton": bool(row["skeleton"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="SemaFS Viewer")
db: Optional[NodeDB] = None
VIEWER_DB_ENV = "SEMAFS_VIEW_DB"


def _configure_db(db_path: str) -> None:
    global db
    db = NodeDB(db_path)
    app.state.db_path = db_path


def _require_db() -> NodeDB:
    if db is None:
        raise HTTPException(500, "Viewer DB is not configured")
    return db


@app.on_event("startup")
def _startup_configure_db() -> None:
    db_path = getattr(app.state, "db_path", None) or os.getenv(VIEWER_DB_ENV)
    if not db_path:
        return
    if not Path(db_path).exists():
        raise RuntimeError(f"Database not found: {db_path}")
    _configure_db(db_path)


@app.get("/api/stats")
def api_stats():
    return _require_db().get_stats()


@app.get("/api/root")
def api_root():
    root = _require_db().get_root()
    if not root:
        raise HTTPException(404, "Root not found")
    return root


@app.get("/api/node/{node_id}")
def api_node(node_id: str):
    node = _require_db().get_node(node_id)
    if not node:
        raise HTTPException(404, "Node not found")
    return node


@app.get("/api/node/{node_id}/children")
def api_children(node_id: str, offset: int = 0, limit: int = 50):
    return _require_db().get_children(node_id, offset, limit)


@app.get("/api/node/{node_id}/ancestors")
def api_ancestors(node_id: str):
    return _require_db().get_ancestors(node_id)


@app.get("/api/path")
def api_by_path(path: str):
    node = _require_db().get_node_by_path(path)
    if not node:
        raise HTTPException(404, "Path not found")
    return node


@app.get("/api/search")
def api_search(q: str, offset: int = 0, limit: int = 50):
    return _require_db().search(q, offset, limit)


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_PAGE


# ─────────────────────────────────────────────────────────────────────────────
# Frontend (Single HTML with Vue 3 + Tailwind)
# ─────────────────────────────────────────────────────────────────────────────

HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SemaFS Viewer</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>
    <style>
        :root {
            --bg: #eef4f0;
            --bg-deep: #e3ece6;
            --panel: rgba(255, 255, 255, 0.9);
            --panel-solid: #ffffff;
            --line: #cfd9d2;
            --line-strong: #192922;
            --text: #15221c;
            --text-dim: #3f5247;
            --text-muted: #62776b;
            --accent: #0b7a64;
            --accent-soft: #dff5ee;
            --accent-strong: #085847;
            --ok: #166534;
            --warn: #9a5b10;
            --err: #b42318;
            --shadow-soft: 0 3px 10px rgba(21, 34, 28, 0.06);
            --shadow-panel: 0 12px 32px rgba(21, 34, 28, 0.08);
        }

        [v-cloak] {
            display: none !important;
        }

        body {
            margin: 0;
            background:
                radial-gradient(circle at 0% -10%, #ffffff 0%, rgba(255, 255, 255, 0) 42%),
                radial-gradient(circle at 100% 0%, #dff3ea 0%, rgba(223, 243, 234, 0) 46%),
                linear-gradient(155deg, var(--bg) 0%, var(--bg-deep) 100%);
            color: var(--text);
            font-family: "Avenir Next", "Segoe UI Variable", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
            text-rendering: optimizeLegibility;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
            line-height: 1.45;
        }

        .mono {
            font-family: "JetBrains Mono", "SF Mono", "SFMono-Regular", Menlo, Consolas, "Liberation Mono", "Noto Sans Mono CJK SC", monospace;
            font-feature-settings: "zero" 1;
        }

        ::selection {
            background: #b6ead9;
            color: #0a2f24;
        }

        .page {
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        .topbar {
            border-bottom: 1px solid var(--line-strong);
            background: rgba(255, 255, 255, 0.92);
            position: sticky;
            top: 0;
            z-index: 40;
            box-shadow: var(--shadow-soft);
        }

        .topbar-inner {
            max-width: 96rem;
            margin: 0 auto;
            padding: 1rem 1.15rem 0.95rem;
            display: grid;
            gap: 0.75rem;
        }

        .title-row {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 0.75rem;
            flex-wrap: wrap;
        }

        .title {
            font-family: "Iowan Old Style", "Palatino Linotype", "Songti SC", "STSong", serif;
            font-size: 1.32rem;
            font-weight: 700;
            letter-spacing: 0.02em;
        }

        .subtitle {
            color: var(--text-dim);
            font-size: 0.74rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .toolbar {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto;
            gap: 0.5rem;
        }

        .input {
            width: 100%;
            border: 1px solid var(--line);
            border-radius: 10px;
            background: rgba(255, 255, 255, 0.96);
            color: var(--text);
            padding: 0.5rem 0.62rem;
            font-size: 0.9rem;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
            transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }

        .input::placeholder {
            color: var(--text-muted);
        }

        .input:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(11, 122, 100, 0.15);
        }

        .btn {
            border: 1px solid #b8c7be;
            border-radius: 10px;
            background: linear-gradient(180deg, #ffffff 0%, #f5f9f7 100%);
            color: var(--text);
            padding: 0.5rem 0.78rem;
            font-size: 0.85rem;
            line-height: 1.05;
            font-weight: 600;
            letter-spacing: 0.01em;
            transition: background 0.12s ease, border-color 0.12s ease, color 0.12s ease;
            box-shadow: var(--shadow-soft);
        }

        .btn:hover:not(:disabled) {
            border-color: var(--accent);
            color: var(--accent-strong);
            background: #f2faf7;
        }

        .btn:disabled {
            opacity: 0.45;
            cursor: not-allowed;
        }

        .stats-row {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            flex-wrap: wrap;
        }

        .pill {
            border: 1px solid var(--line);
            border-radius: 999px;
            padding: 0.24rem 0.56rem;
            background: rgba(255, 255, 255, 0.9);
            font-size: 0.75rem;
            color: var(--text-dim);
        }

        .pill strong {
            color: var(--text);
            margin-right: 0.3rem;
        }

        .status {
            margin-left: auto;
            border: 1px solid var(--line);
            border-radius: 999px;
            padding: 0.24rem 0.58rem;
            font-size: 0.74rem;
            color: var(--text-dim);
            background: rgba(255, 255, 255, 0.92);
            max-width: min(56rem, 100%);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .status.ok {
            color: var(--ok);
            border-color: #86efac;
            background: #f0fdf4;
        }

        .status.warn {
            color: var(--warn);
            border-color: #fcd34d;
            background: #fffbeb;
        }

        .status.error {
            color: var(--err);
            border-color: #fca5a5;
            background: #fef2f2;
        }

        .workspace {
            max-width: 96rem;
            margin: 0 auto;
            padding: 1rem 1.1rem 1.2rem;
            display: grid;
            gap: 1rem;
            grid-template-columns: 24rem minmax(0, 1fr);
            width: 100%;
        }

        .panel {
            border: 1px solid #c2cec7;
            border-radius: 14px;
            background: var(--panel);
            min-width: 0;
            box-shadow: var(--shadow-panel);
            overflow: hidden;
        }

        .panel-head {
            border-bottom: 1px solid var(--line);
            padding: 0.62rem 0.72rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.4rem;
            flex-wrap: wrap;
            background: linear-gradient(180deg, rgba(247, 250, 248, 0.98) 0%, rgba(240, 246, 242, 0.85) 100%);
        }

        .panel-title {
            font-size: 0.74rem;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            color: var(--text-dim);
            font-weight: 700;
        }

        .panel-actions {
            display: flex;
            gap: 0.35rem;
            flex-wrap: wrap;
        }

        .btn-xs {
            font-size: 0.73rem;
            padding: 0.3rem 0.52rem;
        }

        .tree-viewport {
            height: calc(100vh - 240px);
            min-height: 20rem;
            overflow: auto;
            background: linear-gradient(180deg, #ffffff 0%, #f8fbf9 100%);
            scrollbar-gutter: stable both-edges;
        }

        .tree-row {
            height: 32px;
        }

        .tree-row-main {
            display: flex;
            align-items: center;
            gap: 0.3rem;
            height: 32px;
            border-top: 1px solid transparent;
            border-bottom: 1px solid transparent;
            background: transparent;
            padding-right: 0.2rem;
        }

        .tree-row-main.selected {
            background: var(--accent-soft);
            border-top-color: #9adbc8;
            border-bottom-color: #9adbc8;
        }

        .tree-toggle {
            border: none;
            background: transparent;
            color: var(--text-muted);
            width: 1.5rem;
            height: 1.5rem;
            font-size: 0.84rem;
            line-height: 1;
            flex: 0 0 auto;
            cursor: pointer;
            border-radius: 8px;
        }

        .tree-toggle:disabled {
            cursor: default;
            color: #9ca3af;
        }

        .tree-toggle:not(:disabled):hover {
            background: rgba(11, 122, 100, 0.12);
            color: var(--accent-strong);
        }

        .tree-node-btn {
            display: flex;
            align-items: center;
            gap: 0.36rem;
            flex: 1;
            min-width: 0;
            border: none;
            background: transparent;
            color: var(--text);
            text-align: left;
            height: 100%;
            padding-right: 0.35rem;
            cursor: pointer;
        }

        .tree-node-btn:hover .tree-name {
            color: var(--accent);
        }

        .tree-kind {
            border: 1px solid var(--line);
            min-width: 1.2rem;
            text-align: center;
            font-size: 0.68rem;
            color: var(--text-muted);
            background: #f2f7f4;
            flex: 0 0 auto;
            border-radius: 6px;
            line-height: 1.2rem;
        }

        .tree-name {
            font-size: 0.85rem;
            font-weight: 500;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .depth-chip,
        .count-chip {
            border: 1px solid var(--line);
            color: var(--text-muted);
            background: #fff;
            font-size: 0.69rem;
            padding: 0.02rem 0.3rem;
            flex: 0 0 auto;
            border-radius: 6px;
        }

        .tree-load-more {
            border: none;
            background: transparent;
            color: var(--accent);
            font-size: 0.71rem;
            padding: 0 0.35rem;
            cursor: pointer;
            flex: 0 0 auto;
            font-weight: 600;
        }

        .main {
            display: grid;
            gap: 0.8rem;
            min-width: 0;
            align-content: start;
        }

        .section {
            padding: 0.78rem;
        }

        .path-line {
            border: 1px solid var(--line);
            background: #f6faf8;
            padding: 0.38rem 0.5rem;
            font-size: 0.75rem;
            color: var(--text-dim);
            overflow-x: auto;
            white-space: nowrap;
            border-radius: 10px;
        }

        .kv-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.45rem;
        }

        .kv {
            border: 1px solid var(--line);
            padding: 0.38rem 0.46rem;
            font-size: 0.77rem;
            color: var(--text-dim);
            background: #fff;
            border-radius: 10px;
        }

        .label {
            font-size: 0.7rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.12em;
            margin-bottom: 0.34rem;
            font-weight: 600;
        }

        .text-block {
            border: 1px solid var(--line);
            padding: 0.58rem;
            white-space: pre-wrap;
            line-height: 1.5;
            font-size: 0.92rem;
            background: #fff;
            max-height: 34rem;
            overflow: auto;
            border-radius: 12px;
        }

        .chip-list {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem;
        }

        .chip {
            border: 1px solid var(--line);
            font-size: 0.72rem;
            padding: 0.2rem 0.46rem;
            color: var(--text-dim);
            background: #fff;
            border-radius: 999px;
        }

        .list-row {
            border: 1px solid var(--line);
            background: #fff;
            padding: 0.52rem;
            display: grid;
            gap: 0.34rem;
            cursor: pointer;
            border-radius: 12px;
            transition: border-color 0.12s ease, box-shadow 0.12s ease, background 0.12s ease;
        }

        .list-row:hover {
            border-color: var(--accent);
            background: #f4faf7;
            box-shadow: var(--shadow-soft);
        }

        .list-title {
            display: flex;
            align-items: center;
            gap: 0.4rem;
            min-width: 0;
        }

        .list-name {
            font-size: 0.86rem;
            font-weight: 650;
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .list-preview {
            font-size: 0.81rem;
            color: var(--text-dim);
            line-height: 1.42;
            overflow: hidden;
            text-overflow: ellipsis;
            display: -webkit-box;
            -webkit-box-orient: vertical;
            -webkit-line-clamp: 2;
        }

        .pager {
            display: flex;
            gap: 0.45rem;
            align-items: center;
            justify-content: center;
            margin-top: 0.62rem;
        }

        .breadcrumb {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem;
            align-items: center;
            margin-bottom: 0.55rem;
        }

        .crumb-btn {
            border: 1px solid var(--line);
            background: #fff;
            padding: 0.23rem 0.5rem;
            font-size: 0.74rem;
            color: var(--text-dim);
            border-radius: 999px;
            transition: border-color 0.12s ease, color 0.12s ease, background 0.12s ease;
        }

        .crumb-btn:hover {
            border-color: var(--accent);
            color: var(--accent-strong);
            background: #f2faf7;
        }

        .crumb-btn.current {
            border-color: var(--line-strong);
            color: var(--text);
            font-weight: 600;
            background: #f4f9f6;
        }

        * {
            scrollbar-width: thin;
            scrollbar-color: #a9beb3 #e7efe9;
        }

        .tree-viewport::-webkit-scrollbar,
        .text-block::-webkit-scrollbar,
        .path-line::-webkit-scrollbar {
            width: 10px;
            height: 10px;
        }

        .tree-viewport::-webkit-scrollbar-track,
        .text-block::-webkit-scrollbar-track,
        .path-line::-webkit-scrollbar-track {
            background: #e7efe9;
            border-radius: 999px;
        }

        .tree-viewport::-webkit-scrollbar-thumb,
        .text-block::-webkit-scrollbar-thumb,
        .path-line::-webkit-scrollbar-thumb {
            background: #a9beb3;
            border-radius: 999px;
            border: 2px solid #e7efe9;
        }

        @media (max-width: 1200px) {
            .workspace {
                grid-template-columns: minmax(0, 1fr);
            }

            .tree-viewport {
                height: 42vh;
            }
        }

        @media (max-width: 720px) {
            .toolbar {
                grid-template-columns: minmax(0, 1fr) auto;
            }

            .stats-row {
                gap: 0.35rem;
            }

            .status {
                width: 100%;
                margin-left: 0;
            }

            .kv-grid {
                grid-template-columns: minmax(0, 1fr);
            }
        }
    </style>
</head>
<body>
    <div id="app" v-cloak class="page">
        <header class="topbar">
            <div class="topbar-inner">
                <div class="title-row">
                    <div>
                        <div class="title">SemaFS Viewer</div>
                        <div class="subtitle">minimal tree explorer for deep hierarchies</div>
                    </div>
                </div>

                <div class="toolbar">
                    <input
                        class="input"
                        v-model="searchQuery"
                        @keyup.enter="search"
                        placeholder="Search name / content / summary"
                    >
                    <button class="btn" @click="search">Search</button>
                    <input
                        class="input mono"
                        v-model="jumpPath"
                        @keyup.enter="jumpToPath"
                        placeholder="Jump path: root.user.y2026.m03"
                    >
                    <button class="btn" @click="jumpToPath">Go Path</button>
                </div>

                <div class="stats-row">
                    <span class="pill" v-if="stats"><strong class="mono">{{ formatNumber(stats.total) }}</strong>nodes</span>
                    <span class="pill" v-if="stats"><strong class="mono">{{ formatNumber(stats.categories) }}</strong>categories</span>
                    <span class="pill" v-if="stats"><strong class="mono">{{ formatNumber(stats.leaves) }}</strong>leaves</span>
                    <span class="pill" v-if="stats"><strong class="mono">{{ formatNumber(stats.max_depth) }}</strong>max depth</span>
                    <span class="status" :class="statusKind">{{ statusMessage }}</span>
                </div>
            </div>
        </header>

        <div class="workspace">
            <aside class="panel">
                <div class="panel-head">
                    <div class="panel-title">Tree Navigator</div>
                    <div class="panel-actions">
                        <button class="btn btn-xs" @click="goRoot" :disabled="!rootNode">Root</button>
                        <button class="btn btn-xs" @click="expandSelectedOneLevel" :disabled="!selectedNode || selectedNode.type !== 'category'">Expand+1</button>
                        <button class="btn btn-xs" @click="collapseAll" :disabled="!rootNode">Collapse</button>
                    </div>
                </div>

                <div ref="treeViewport" class="tree-viewport" @scroll="onTreeScroll">
                    <div :style="{ height: virtualTop + 'px' }"></div>

                    <div
                        v-for="row in virtualRows"
                        :key="row.node.id"
                        class="tree-row"
                    >
                        <div
                            class="tree-row-main"
                            :class="{ selected: selectedNode && selectedNode.id === row.node.id }"
                        >
                            <button
                                class="tree-toggle mono"
                                @click.stop="toggleExpand(row.node)"
                                :disabled="row.node.type !== 'category'"
                            >
                                <span v-if="row.node.type === 'category'">{{ isExpanded(row.node.id) ? '-' : '+' }}</span>
                                <span v-else>·</span>
                            </button>

                            <button
                                class="tree-node-btn"
                                @click="selectNode(row.node)"
                                :style="{ paddingLeft: depthPadding(row.depth) }"
                            >
                                <span class="tree-kind mono">{{ row.node.type === 'category' ? 'C' : 'L' }}</span>
                                <span class="tree-name">{{ row.node.name }}</span>
                                <span v-if="row.depth > MAX_INDENT_DEPTH" class="depth-chip mono">d{{ row.depth }}</span>
                                <span
                                    v-if="row.node.type === 'category' && childMetaByParent[row.node.id]"
                                    class="count-chip mono"
                                >
                                    {{ formatNumber(childMetaByParent[row.node.id].total) }}
                                </span>
                            </button>

                            <button
                                v-if="canLoadMore(row.node.id)"
                                class="tree-load-more mono"
                                @click.stop="loadMoreTreeChildren(row.node.id)"
                            >
                                +{{ formatNumber(remainingChildren(row.node.id)) }}
                            </button>
                        </div>
                    </div>

                    <div :style="{ height: virtualBottom + 'px' }"></div>
                </div>
            </aside>

            <main class="main">
                <section class="panel section" v-if="searchResults">
                    <div class="panel-head" style="margin: -0.7rem -0.7rem 0.7rem -0.7rem;">
                        <div class="panel-title">Search Results</div>
                        <div class="panel-actions">
                            <span class="pill mono">{{ formatNumber(searchResults.total) }} hits</span>
                            <button class="btn btn-xs" @click="clearSearch">Close</button>
                        </div>
                    </div>

                    <div class="list-row" v-for="item in searchResults.items" :key="item.id" @click="openSearchResult(item)">
                        <div class="list-title">
                            <span class="tree-kind mono">{{ item.type === 'category' ? 'C' : 'L' }}</span>
                            <span class="list-name">{{ item.name }}</span>
                        </div>
                        <div class="path-line mono">{{ item.path }}</div>
                        <div class="list-preview">{{ item.content || '-' }}</div>
                    </div>

                    <div class="pager" v-if="searchResults.total > searchResults.limit">
                        <button
                            class="btn btn-xs"
                            @click="searchPage(searchResults.offset - searchResults.limit)"
                            :disabled="searchResults.offset <= 0"
                        >
                            Prev
                        </button>
                        <span class="pill mono">
                            {{ Math.floor(searchResults.offset / searchResults.limit) + 1 }}
                            /
                            {{ Math.ceil(searchResults.total / searchResults.limit) }}
                        </span>
                        <button
                            class="btn btn-xs"
                            @click="searchPage(searchResults.offset + searchResults.limit)"
                            :disabled="searchResults.offset + searchResults.limit >= searchResults.total"
                        >
                            Next
                        </button>
                    </div>
                </section>

                <section class="panel section" v-if="selectedNode">
                    <div class="breadcrumb" v-if="breadcrumb.length">
                        <button
                            v-for="(item, index) in breadcrumb"
                            :key="item.id"
                            class="crumb-btn"
                            :class="{ current: index === breadcrumb.length - 1 }"
                            @click="selectNode(item)"
                        >
                            {{ item.name }}
                        </button>
                    </div>

                    <div class="label">Node</div>
                    <div class="kv-grid">
                        <div class="kv"><span class="mono">name</span> = {{ selectedNode.name }}</div>
                        <div class="kv"><span class="mono">type</span> = {{ selectedNode.type }}</div>
                        <div class="kv"><span class="mono">stage</span> = {{ selectedNode.stage }}</div>
                        <div class="kv"><span class="mono">id</span> = {{ selectedNode.id.slice(0, 8) }}</div>
                    </div>

                    <div class="path-line mono" style="margin-top: 0.55rem;">{{ selectedNode.path }}</div>

                    <div style="margin-top: 0.65rem;" v-if="selectedNode.tags && selectedNode.tags.length">
                        <div class="label">Tags</div>
                        <div class="chip-list">
                            <span class="chip mono" v-for="tag in selectedNode.tags" :key="tag">#{{ tag }}</span>
                        </div>
                    </div>

                    <div style="margin-top: 0.65rem;" v-if="selectedNode.type === 'category'">
                        <div class="label">Keywords</div>
                        <div class="chip-list">
                            <span
                                class="chip"
                                v-for="kw in selectedNode.keywords || []"
                                :key="kw"
                            >{{ kw }}</span>
                            <span class="chip" v-if="!selectedNode.keywords || !selectedNode.keywords.length">none</span>
                        </div>
                    </div>

                    <div style="margin-top: 0.65rem;" v-if="selectedNode.content">
                        <div class="label">Content</div>
                        <div class="text-block">{{ selectedNode.content }}</div>
                    </div>
                </section>

                <section class="panel section" v-if="selectedNode && selectedNode.type === 'category'">
                    <div class="panel-head" style="margin: -0.7rem -0.7rem 0.7rem -0.7rem;">
                        <div class="panel-title">Children</div>
                        <div class="panel-actions">
                            <span class="pill mono" v-if="selectedChildren">{{ formatNumber(selectedChildren.total) }} total</span>
                        </div>
                    </div>

                    <div v-if="selectedChildren && selectedChildren.items && selectedChildren.items.length">
                        <div class="list-row" v-for="child in selectedChildren.items" :key="child.id" @click="selectNode(child)">
                            <div class="list-title">
                                <span class="tree-kind mono">{{ child.type === 'category' ? 'C' : 'L' }}</span>
                                <span class="list-name">{{ child.name }}</span>
                            </div>
                            <div class="path-line mono">{{ child.path }}</div>
                            <div class="list-preview">{{ child.content || '-' }}</div>
                        </div>
                    </div>
                    <div v-else class="kv">No children</div>

                    <div class="pager" v-if="selectedChildren && selectedChildren.total > selectedChildren.limit">
                        <button
                            class="btn btn-xs"
                            @click="loadSelectedChildren(selectedChildren.offset - selectedChildren.limit)"
                            :disabled="selectedChildren.offset <= 0"
                        >
                            Prev
                        </button>
                        <span class="pill mono">
                            {{ Math.floor(selectedChildren.offset / selectedChildren.limit) + 1 }}
                            /
                            {{ Math.ceil(selectedChildren.total / selectedChildren.limit) }}
                        </span>
                        <button
                            class="btn btn-xs"
                            @click="loadSelectedChildren(selectedChildren.offset + selectedChildren.limit)"
                            :disabled="selectedChildren.offset + selectedChildren.limit >= selectedChildren.total"
                        >
                            Next
                        </button>
                    </div>
                </section>

                <section class="panel section" v-if="!selectedNode">
                    <div class="kv">Loading root node...</div>
                </section>
            </main>
        </div>
    </div>

    <script>
    const { createApp, ref, computed, onMounted, onUnmounted, nextTick } = Vue;

    createApp({
        setup() {
            const TREE_PAGE_SIZE = 120;
            const DETAIL_PAGE_SIZE = 40;
            const TREE_ROW_HEIGHT = 32;
            const TREE_OVERSCAN = 14;
            const MAX_INDENT_DEPTH = 24;

            const stats = ref(null);
            const rootNode = ref(null);
            const selectedNode = ref(null);
            const breadcrumb = ref([]);
            const selectedChildren = ref(null);

            const searchQuery = ref("");
            const searchResults = ref(null);
            const jumpPath = ref("root");

            const statusMessage = ref("ready");
            const statusKind = ref("ok");

            const expandedIds = ref(new Set());
            const childrenByParent = ref({});
            const childMetaByParent = ref({});

            const treeRows = ref([]);
            const treeViewport = ref(null);
            const treeScrollTop = ref(0);
            const treeViewportHeight = ref(560);

            const formatNumber = (n) => Number(n || 0).toLocaleString();

            const depthPadding = (depth) => {
                const clamped = Math.min(depth, MAX_INDENT_DEPTH);
                return (clamped * 14 + 2) + "px";
            };

            const setStatus = (msg, kind = "ok") => {
                statusMessage.value = msg || "";
                statusKind.value = kind;
            };

            const fetchJson = async (url) => {
                const res = await fetch(url);
                if (!res.ok) {
                    let text = "";
                    try {
                        text = await res.text();
                    } catch (_) {}
                    throw new Error(text || `HTTP ${res.status}`);
                }
                return await res.json();
            };

            const isExpanded = (nodeId) => expandedIds.value.has(nodeId);

            const canLoadMore = (parentId) => {
                const meta = childMetaByParent.value[parentId];
                const items = childrenByParent.value[parentId] || [];
                if (!meta) return false;
                return items.length < meta.total;
            };

            const remainingChildren = (parentId) => {
                const meta = childMetaByParent.value[parentId];
                const items = childrenByParent.value[parentId] || [];
                if (!meta) return 0;
                return Math.max(0, meta.total - items.length);
            };

            const rebuildTreeRows = () => {
                if (!rootNode.value) {
                    treeRows.value = [];
                    return;
                }
                const stack = [{ node: rootNode.value, depth: 0 }];
                const flattened = [];

                while (stack.length > 0) {
                    const current = stack.pop();
                    flattened.push(current);
                    if (current.node.type !== "category") {
                        continue;
                    }
                    if (!expandedIds.value.has(current.node.id)) {
                        continue;
                    }
                    const children = childrenByParent.value[current.node.id] || [];
                    for (let i = children.length - 1; i >= 0; i -= 1) {
                        stack.push({ node: children[i], depth: current.depth + 1 });
                    }
                }

                treeRows.value = flattened;
            };

            const virtualRange = computed(() => {
                const total = treeRows.value.length;
                if (total === 0) {
                    return { start: 0, end: 0 };
                }
                const start = Math.max(
                    0,
                    Math.floor(treeScrollTop.value / TREE_ROW_HEIGHT) - TREE_OVERSCAN,
                );
                const visibleCount =
                    Math.ceil(treeViewportHeight.value / TREE_ROW_HEIGHT) + TREE_OVERSCAN * 2;
                const end = Math.min(total, start + visibleCount);
                return { start, end };
            });

            const virtualRows = computed(() =>
                treeRows.value.slice(virtualRange.value.start, virtualRange.value.end),
            );

            const virtualTop = computed(() => virtualRange.value.start * TREE_ROW_HEIGHT);
            const virtualBottom = computed(
                () => Math.max(0, (treeRows.value.length - virtualRange.value.end) * TREE_ROW_HEIGHT),
            );

            const loadTreeChildren = async (parentId, offset = 0, append = false) => {
                try {
                    const data = await fetchJson(
                        `/api/node/${parentId}/children?offset=${offset}&limit=${TREE_PAGE_SIZE}`,
                    );
                    const existing = append ? (childrenByParent.value[parentId] || []) : [];
                    childrenByParent.value = {
                        ...childrenByParent.value,
                        [parentId]: existing.concat(data.items || []),
                    };
                    childMetaByParent.value = {
                        ...childMetaByParent.value,
                        [parentId]: {
                            total: data.total || 0,
                            offset: (data.offset || 0) + (data.items || []).length,
                            limit: data.limit || TREE_PAGE_SIZE,
                        },
                    };
                    rebuildTreeRows();
                } catch (err) {
                    setStatus(`load children failed: ${err.message}`, "error");
                }
            };

            const ensureTreeChildrenLoaded = async (parentId) => {
                if (childrenByParent.value[parentId]) {
                    return;
                }
                await loadTreeChildren(parentId, 0, false);
            };

            const loadMoreTreeChildren = async (parentId) => {
                const meta = childMetaByParent.value[parentId];
                if (!meta) {
                    return;
                }
                await loadTreeChildren(parentId, meta.offset, true);
            };

            const toggleExpand = async (node) => {
                if (!node || node.type !== "category") {
                    return;
                }
                const next = new Set(expandedIds.value);
                if (next.has(node.id)) {
                    next.delete(node.id);
                    expandedIds.value = next;
                    rebuildTreeRows();
                    return;
                }
                next.add(node.id);
                expandedIds.value = next;
                await ensureTreeChildrenLoaded(node.id);
                rebuildTreeRows();
            };

            const scrollToTreeNode = async (nodeId) => {
                await nextTick();
                if (!treeViewport.value) {
                    return;
                }
                const index = treeRows.value.findIndex((row) => row.node.id === nodeId);
                if (index < 0) {
                    return;
                }
                const top = index * TREE_ROW_HEIGHT;
                const bottom = top + TREE_ROW_HEIGHT;
                const viewTop = treeViewport.value.scrollTop;
                const viewBottom = viewTop + treeViewportHeight.value;
                if (top < viewTop) {
                    treeViewport.value.scrollTop = Math.max(0, top - TREE_ROW_HEIGHT * 2);
                } else if (bottom > viewBottom) {
                    treeViewport.value.scrollTop = Math.max(
                        0,
                        bottom - treeViewportHeight.value + TREE_ROW_HEIGHT * 2,
                    );
                }
            };

            const loadSelectedChildren = async (offset = 0) => {
                if (!selectedNode.value || selectedNode.value.type !== "category") {
                    selectedChildren.value = null;
                    return;
                }
                selectedChildren.value = await fetchJson(
                    `/api/node/${selectedNode.value.id}/children?offset=${offset}&limit=${DETAIL_PAGE_SIZE}`,
                );
            };

            const selectNode = async (node, options = {}) => {
                const { skipScroll = false } = options;
                try {
                    const fullNode = node.path && node.stage
                        ? node
                        : await fetchJson(`/api/node/${node.id}`);
                    selectedNode.value = fullNode;

                    const ancestors = await fetchJson(`/api/node/${fullNode.id}/ancestors`);
                    breadcrumb.value = ancestors || [];

                    const next = new Set(expandedIds.value);
                    for (const anc of ancestors) {
                        if (anc.type === "category") {
                            next.add(anc.id);
                        }
                    }
                    expandedIds.value = next;

                    for (const anc of ancestors) {
                        if (anc.type === "category") {
                            await ensureTreeChildrenLoaded(anc.id);
                        }
                    }

                    rebuildTreeRows();
                    if (!skipScroll) {
                        await scrollToTreeNode(fullNode.id);
                    }

                    if (fullNode.type === "category") {
                        await loadSelectedChildren(0);
                    } else {
                        selectedChildren.value = null;
                    }

                    jumpPath.value = fullNode.path || "";
                    setStatus(`selected: ${fullNode.path}`, "ok");
                } catch (err) {
                    setStatus(`select failed: ${err.message}`, "error");
                }
            };

            const goRoot = async () => {
                if (!rootNode.value) {
                    return;
                }
                await selectNode(rootNode.value);
            };

            const expandSelectedOneLevel = async () => {
                if (!selectedNode.value || selectedNode.value.type !== "category") {
                    return;
                }
                const next = new Set(expandedIds.value);
                next.add(selectedNode.value.id);
                expandedIds.value = next;
                await ensureTreeChildrenLoaded(selectedNode.value.id);
                rebuildTreeRows();
                setStatus(`expanded: ${selectedNode.value.path}`, "ok");
            };

            const collapseAll = () => {
                if (!rootNode.value) {
                    return;
                }
                expandedIds.value = new Set([rootNode.value.id]);
                rebuildTreeRows();
                setStatus("collapsed to root", "warn");
            };

            const search = async () => {
                const query = searchQuery.value.trim();
                if (!query) {
                    searchResults.value = null;
                    return;
                }
                try {
                    searchResults.value = await fetchJson(
                        `/api/search?q=${encodeURIComponent(query)}&offset=0&limit=40`,
                    );
                    setStatus(`search: ${query}`, "ok");
                } catch (err) {
                    setStatus(`search failed: ${err.message}`, "error");
                }
            };

            const searchPage = async (offset) => {
                if (!searchResults.value || offset < 0) {
                    return;
                }
                try {
                    searchResults.value = await fetchJson(
                        `/api/search?q=${encodeURIComponent(searchResults.value.query)}&offset=${offset}&limit=${searchResults.value.limit}`,
                    );
                } catch (err) {
                    setStatus(`search page failed: ${err.message}`, "error");
                }
            };

            const clearSearch = () => {
                searchResults.value = null;
                searchQuery.value = "";
                setStatus("search cleared", "warn");
            };

            const openSearchResult = async (item) => {
                await selectNode(item);
                clearSearch();
            };

            const jumpToPath = async () => {
                const path = jumpPath.value.trim();
                if (!path) {
                    return;
                }
                try {
                    const node = await fetchJson(`/api/path?path=${encodeURIComponent(path)}`);
                    await selectNode(node);
                } catch (err) {
                    setStatus(`path not found: ${path}`, "error");
                }
            };

            const loadStats = async () => {
                stats.value = await fetchJson("/api/stats");
            };

            const loadRoot = async () => {
                rootNode.value = await fetchJson("/api/root");
                expandedIds.value = new Set([rootNode.value.id]);
                await ensureTreeChildrenLoaded(rootNode.value.id);
                rebuildTreeRows();
                await selectNode(rootNode.value, { skipScroll: true });
            };

            const onTreeScroll = (event) => {
                treeScrollTop.value = event.target.scrollTop || 0;
            };

            const measureTreeViewport = () => {
                if (!treeViewport.value) {
                    return;
                }
                treeViewportHeight.value = Math.max(180, treeViewport.value.clientHeight || 180);
            };

            onMounted(async () => {
                window.addEventListener("resize", measureTreeViewport);
                try {
                    await Promise.all([loadStats(), loadRoot()]);
                    setStatus("viewer ready", "ok");
                } catch (err) {
                    setStatus(`init failed: ${err.message}`, "error");
                }
                measureTreeViewport();
            });

            onUnmounted(() => {
                window.removeEventListener("resize", measureTreeViewport);
            });

            return {
                MAX_INDENT_DEPTH,
                stats,
                rootNode,
                selectedNode,
                breadcrumb,
                selectedChildren,
                searchQuery,
                searchResults,
                jumpPath,
                statusMessage,
                statusKind,
                childMetaByParent,
                treeViewport,
                virtualRows,
                virtualTop,
                virtualBottom,
                formatNumber,
                depthPadding,
                isExpanded,
                canLoadMore,
                remainingChildren,
                toggleExpand,
                loadMoreTreeChildren,
                selectNode,
                goRoot,
                expandSelectedOneLevel,
                collapseAll,
                loadSelectedChildren,
                search,
                searchPage,
                clearSearch,
                openSearchResult,
                jumpToPath,
                onTreeScroll,
            };
        },
    }).mount("#app");
    </script>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def view(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SemaFS Web Viewer")
    parser.add_argument("--db",
                        default="data/semafs_real_llm.db",
                        help="Database path")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--reload",
                        action="store_true",
                        help="Enable autoreload")
    parser.add_argument(
        "--log-level",
        default=None,
        help="Log level (env fallback: SEMAFS_LOG_LEVEL)",
    )
    args = parser.parse_args(argv)
    configure_logging(args.log_level)

    db_path = str(Path(args.db).expanduser().resolve())
    if not Path(db_path).exists():
        logger.error("Database not found: %s", args.db)
        return 1

    os.environ[VIEWER_DB_ENV] = db_path
    _configure_db(db_path)

    logger.info("SemaFS Viewer starting at http://%s:%s", args.host, args.port)
    logger.info("Database: %s", db_path)
    app_target = "semafs.view:app" if args.reload else app
    uvicorn.run(
        app_target,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(view())
