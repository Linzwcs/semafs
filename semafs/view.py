import argparse
import json
import sqlite3
from pathlib import Path
from typing import Optional

try:
    from fastapi import FastAPI, Query, HTTPException
    from fastapi.responses import HTMLResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn
except ImportError:
    print("Required: pip install fastapi uvicorn")
    exit(1)

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
        }


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="SemaFS Viewer")
db: Optional[NodeDB] = None


@app.get("/api/stats")
def api_stats():
    return db.get_stats()


@app.get("/api/root")
def api_root():
    root = db.get_root()
    if not root:
        raise HTTPException(404, "Root not found")
    return root


@app.get("/api/node/{node_id}")
def api_node(node_id: str):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(404, "Node not found")
    return node


@app.get("/api/node/{node_id}/children")
def api_children(node_id: str, offset: int = 0, limit: int = 50):
    return db.get_children(node_id, offset, limit)


@app.get("/api/node/{node_id}/ancestors")
def api_ancestors(node_id: str):
    return db.get_ancestors(node_id)


@app.get("/api/path")
def api_by_path(path: str):
    node = db.get_node_by_path(path)
    if not node:
        raise HTTPException(404, "Path not found")
    return node


@app.get("/api/search")
def api_search(q: str, offset: int = 0, limit: int = 50):
    return db.search(q, offset, limit)


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
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,700&family=Manrope:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

        :root {
            --bg-0: #f5f6f3;
            --bg-1: #eceee8;
            --bg-panel: rgba(255, 255, 255, 0.8);
            --line: #d7dbd1;
            --text-0: #1f2a20;
            --text-1: #4e5c50;
            --text-2: #728073;
            --accent: #1f7a59;
            --accent-soft: #e7f3ed;
            --hover: #eef3ec;
        }

        [v-cloak] { display: none; }
        body {
            font-family: "Manrope", ui-sans-serif, sans-serif;
            color: var(--text-0);
            background:
                radial-gradient(circle at 2% -8%, #ffffff 0%, #f5f6f3 45%, #eceee8 100%);
        }
        .app-shell {
            min-height: 100vh;
        }
        .brand-title {
            font-family: "Fraunces", ui-serif, serif;
            letter-spacing: 0.01em;
            color: var(--text-0);
        }
        .header-bar {
            background: rgba(245, 246, 243, 0.86);
            border-bottom: 1px solid var(--line);
            backdrop-filter: blur(10px);
        }
        .soft-input {
            width: 100%;
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 0.65rem 0.95rem 0.65rem 2.5rem;
            background: rgba(255, 255, 255, 0.85);
            color: var(--text-0);
            transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }
        .soft-input::placeholder {
            color: var(--text-2);
        }
        .soft-input:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(31, 122, 89, 0.12);
        }
        .stat-pill {
            border: 1px solid var(--line);
            border-radius: 999px;
            padding: 0.28rem 0.7rem;
            font-size: 0.78rem;
            color: var(--text-1);
            background: rgba(255, 255, 255, 0.7);
        }
        .stat-pill strong {
            color: var(--accent);
            font-family: "IBM Plex Mono", ui-monospace, monospace;
            font-weight: 500;
            margin-right: 0.2rem;
        }
        .panel {
            background: var(--bg-panel);
            border: 1px solid var(--line);
            border-radius: 18px;
            box-shadow: 0 10px 28px rgba(34, 53, 41, 0.08);
        }
        .section-card {
            background: rgba(255, 255, 255, 0.75);
            border: 1px solid var(--line);
            border-radius: 16px;
            box-shadow: 0 8px 24px rgba(31, 42, 32, 0.06);
        }
        .btn {
            border: 1px solid var(--line);
            background: #fff;
            color: var(--text-0);
            border-radius: 10px;
            padding: 0.32rem 0.7rem;
            transition: all 0.15s ease;
        }
        .btn:hover:not(:disabled) {
            background: var(--hover);
            border-color: #bac2b7;
        }
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .btn-ghost {
            color: var(--text-1);
        }
        .btn-ghost:hover {
            color: var(--text-0);
        }
        .section-label {
            color: var(--text-2);
            letter-spacing: 0.08em;
        }
        .mono {
            font-family: "IBM Plex Mono", ui-monospace, monospace;
        }
        .path-text {
            color: var(--text-2);
        }
        .text-main {
            color: var(--text-0);
        }
        .text-subtle {
            color: var(--text-1);
        }
        .text-accent {
            color: var(--accent);
        }
        .icon-muted {
            color: var(--text-2);
        }
        .content-text {
            color: var(--text-0);
        }
        .node-selected {
            background: var(--accent-soft);
            border: 1px solid #c8dfd3;
        }
        .node-default {
            border: 1px solid transparent;
        }
        .node-default:hover {
            background: var(--hover);
        }
        .node-hover-accent:hover {
            color: var(--accent);
        }
        .breadcrumb-link:hover {
            color: var(--text-0);
        }
        .status-badge {
            padding: 0.18rem 0.55rem;
            border-radius: 999px;
            font-size: 0.74rem;
            border: 1px solid transparent;
        }
        .stage-active {
            background: #e7f3ed;
            color: #206a4f;
            border-color: #b5d7c7;
        }
        .stage-pending {
            background: #f8f0dd;
            color: #8a6427;
            border-color: #e5d1a2;
        }
        .stage-cold {
            background: #edf0eb;
            color: #5f6d60;
            border-color: #ced4cd;
        }
        .tag-chip {
            background: #eef3ec;
            border: 1px solid #d6ddd4;
            color: #435446;
            font-size: 0.74rem;
            border-radius: 999px;
            padding: 0.22rem 0.55rem;
        }
        .keyword-chip {
            background: #edf4ff;
            border: 1px solid #cfdbf3;
            color: #37506f;
            font-size: 0.72rem;
            border-radius: 999px;
            padding: 0.16rem 0.5rem;
            line-height: 1.15rem;
            white-space: nowrap;
        }
        .keyword-chip-muted {
            background: #f2f4f1;
            border: 1px solid #d7ddd4;
            color: #708070;
        }
        .item-row {
            border: 1px solid var(--line);
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.74);
            transition: all 0.15s ease;
        }
        .item-row:hover {
            border-color: #b7c1b6;
            background: #ffffff;
            transform: translateY(-1px);
        }
        .tree-node { transition: all 0.15s ease; }
        .tree-node:hover { background: transparent; }
        .content-preview {
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        .fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
        .fade-enter-from, .fade-leave-to { opacity: 0; }
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: #e6e9e3; }
        ::-webkit-scrollbar-thumb { background: #c1c9bd; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #adb6a8; }
    </style>
</head>
<body>
    <div id="app" v-cloak class="app-shell">
        <!-- Header -->
        <header class="header-bar px-6 py-4 sticky top-0 z-50">
            <div class="flex items-center justify-between flex-wrap gap-3 max-w-7xl mx-auto">
                <div class="flex items-center gap-3">
                    <h1 class="brand-title text-2xl font-semibold">SemaFS Viewer</h1>
                </div>
                <!-- Search -->
                <div class="order-3 w-full md:order-2 md:flex-1 md:max-w-xl md:mx-8">
                    <div class="relative">
                        <input
                            v-model="searchQuery"
                            @keyup.enter="search"
                            type="text"
                            placeholder="Search nodes... (Enter)"
                            class="soft-input"
                        >
                        <svg class="absolute left-3 top-2.5 w-5 h-5 icon-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
                        </svg>
                    </div>
                </div>
                <!-- Stats -->
                <div class="hidden xl:flex gap-2 text-sm order-2 md:order-3" v-if="stats">
                    <span class="stat-pill">
                        <strong>{{ formatNumber(stats.total) }}</strong> nodes
                    </span>
                    <span class="stat-pill">
                        <strong>{{ formatNumber(stats.categories) }}</strong> categories
                    </span>
                    <span class="stat-pill">
                        <strong>{{ formatNumber(stats.leaves) }}</strong> leaves
                    </span>
                </div>
            </div>
        </header>

        <div class="flex flex-col lg:flex-row max-w-7xl mx-auto gap-4 px-4 py-5">
            <!-- Sidebar: Tree Navigation -->
            <aside class="w-full lg:w-80 panel h-[45vh] lg:h-[calc(100vh-110px)] overflow-y-auto lg:sticky lg:top-[92px]">
                <div class="p-4">
                    <h2 class="text-sm font-semibold section-label uppercase mb-3">Tree</h2>
                    <!-- Tree Root -->
                    <div v-if="rootNode">
                        <tree-node
                            :node="rootNode"
                            :depth="0"
                            :selected-id="selectedNode?.id"
                            @select="selectNode"
                        />
                    </div>
                    <div v-else class="path-text text-sm">Loading...</div>
                </div>
            </aside>

            <!-- Main Content -->
            <main class="flex-1 h-[calc(100vh-110px)] overflow-y-auto">
                <!-- Breadcrumb -->
                <nav v-if="breadcrumb.length" class="flex items-center gap-2 text-sm mb-6 flex-wrap path-text">
                    <template v-for="(item, idx) in breadcrumb" :key="item.id">
                        <span v-if="idx > 0" class="path-text">/</span>
                        <button
                            @click="selectNode(item)"
                            class="transition-colors"
                            :class="idx === breadcrumb.length - 1 ? 'text-accent font-medium' : 'text-subtle breadcrumb-link'"
                        >
                            {{ item.name }}
                        </button>
                    </template>
                </nav>

                <!-- Search Results -->
                <div v-if="searchResults" class="mb-6">
                    <div class="flex items-center justify-between mb-4">
                        <h2 class="text-lg font-semibold">
                            Search: "{{ searchResults.query }}"
                            <span class="path-text font-normal">({{ searchResults.total }} results)</span>
                        </h2>
                        <button @click="clearSearch" class="text-sm btn-ghost">Clear</button>
                    </div>
                    <div class="space-y-2">
                        <div
                            v-for="item in searchResults.items"
                            :key="item.id"
                            @click="selectNode(item); clearSearch()"
                            class="p-3 item-row cursor-pointer"
                        >
                            <div class="flex items-center gap-2">
                                <span>{{ item.type === 'category' ? '📂' : '📄' }}</span>
                                <span class="font-medium">{{ item.name }}</span>
                                <span class="text-xs path-text mono">{{ item.path }}</span>
                            </div>
                            <p class="text-sm path-text mt-1 content-preview">{{ item.content }}</p>
                            <div v-if="item.type === 'category'" class="flex flex-wrap gap-1 mt-2">
                                <span
                                    v-if="item.keywords?.length"
                                    v-for="kw in item.keywords.slice(0, 6)"
                                    :key="kw"
                                    class="keyword-chip"
                                >{{ kw }}</span>
                                <span v-else class="keyword-chip keyword-chip-muted">no keywords</span>
                            </div>
                        </div>
                    </div>
                    <!-- Pagination -->
                    <div v-if="searchResults.total > searchResults.limit" class="flex justify-center gap-2 mt-4">
                        <button
                            @click="searchPage(searchResults.offset - searchResults.limit)"
                            :disabled="searchResults.offset === 0"
                            class="btn"
                        >Prev</button>
                        <span class="px-3 py-1 path-text mono">
                            {{ Math.floor(searchResults.offset / searchResults.limit) + 1 }} /
                            {{ Math.ceil(searchResults.total / searchResults.limit) }}
                        </span>
                        <button
                            @click="searchPage(searchResults.offset + searchResults.limit)"
                            :disabled="searchResults.offset + searchResults.limit >= searchResults.total"
                            class="btn"
                        >Next</button>
                    </div>
                </div>

                <!-- Selected Node Detail -->
                <div v-else-if="selectedNode" class="space-y-6">
                    <!-- Node Header -->
                    <div class="section-card p-6">
                        <div class="flex items-start justify-between">
                            <div>
                                <div class="flex items-center gap-3 mb-2">
                                    <span class="text-3xl">{{ selectedNode.type === 'category' ? '📂' : '📄' }}</span>
                                    <h1 class="text-2xl font-bold">{{ selectedNode.name }}</h1>
                                    <span
                                        class="status-badge"
                                        :class="{
                                            'stage-active': selectedNode.stage === 'active',
                                            'stage-pending': selectedNode.stage === 'pending',
                                            'stage-cold': selectedNode.stage === 'cold',
                                        }"
                                    >{{ selectedNode.stage }}</span>
                                </div>
                                <p class="path-text mono text-sm">{{ selectedNode.path }}</p>
                            </div>
                            <div class="text-right text-sm path-text mono">
                                <div>ID: {{ selectedNode.id.slice(0, 8) }}</div>
                            </div>
                        </div>
                        <!-- Tags -->
                        <div v-if="selectedNode.tags?.length" class="flex gap-2 mt-4">
                            <span
                                v-for="tag in selectedNode.tags"
                                :key="tag"
                                class="tag-chip"
                            >#{{ tag }}</span>
                        </div>
                        <div v-if="selectedNode.type === 'category'" class="mt-4">
                            <div class="text-xs font-semibold section-label uppercase mb-2">Keywords</div>
                            <div class="flex flex-wrap gap-2">
                                <span
                                    v-if="selectedNode.keywords?.length"
                                    v-for="kw in selectedNode.keywords"
                                    :key="kw"
                                    class="keyword-chip"
                                >{{ kw }}</span>
                                <span v-else class="keyword-chip keyword-chip-muted">no keywords</span>
                            </div>
                        </div>
                    </div>

                    <!-- Content -->
                    <div v-if="selectedNode.content" class="section-card p-6">
                        <h2 class="text-sm font-semibold section-label uppercase mb-3">Content</h2>
                        <div class="max-w-none">
                            <p class="whitespace-pre-wrap content-text leading-relaxed">{{ selectedNode.content }}</p>
                        </div>
                    </div>

                    <!-- Children (for categories) -->
                    <div v-if="selectedNode.type === 'category'" class="section-card p-6">
                        <div class="flex items-center justify-between mb-4">
                            <h2 class="text-sm font-semibold section-label uppercase">
                                Children
                                <span v-if="children" class="text-accent">({{ children.total }})</span>
                            </h2>
                        </div>
                        <div v-if="children?.items.length" class="space-y-2">
                            <div
                                v-for="child in children.items"
                                :key="child.id"
                                @click="selectNode(child)"
                                class="flex items-center gap-3 p-3 item-row cursor-pointer group"
                            >
                                <span>{{ child.type === 'category' ? '📂' : '📄' }}</span>
                                <div class="flex-1 min-w-0">
                                    <div class="font-medium node-hover-accent transition-colors">{{ child.name }}</div>
                                    <p class="text-sm path-text truncate">{{ child.content }}</p>
                                    <div v-if="child.type === 'category'" class="flex flex-wrap gap-1 mt-2">
                                        <span
                                            v-if="child.keywords?.length"
                                            v-for="kw in child.keywords.slice(0, 4)"
                                            :key="kw"
                                            class="keyword-chip"
                                        >{{ kw }}</span>
                                        <span v-else class="keyword-chip keyword-chip-muted">no keywords</span>
                                    </div>
                                </div>
                                <svg class="w-5 h-5 path-text node-hover-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
                                </svg>
                            </div>
                        </div>
                        <div v-else class="path-text text-sm">No children</div>
                        <!-- Children Pagination -->
                        <div v-if="children?.total > children?.limit" class="flex justify-center gap-2 mt-4">
                            <button
                                @click="loadChildren(children.offset - children.limit)"
                                :disabled="children.offset === 0"
                                class="btn"
                            >Prev</button>
                            <span class="px-3 py-1 path-text mono">
                                {{ Math.floor(children.offset / children.limit) + 1 }} /
                                {{ Math.ceil(children.total / children.limit) }}
                            </span>
                            <button
                                @click="loadChildren(children.offset + children.limit)"
                                :disabled="children.offset + children.limit >= children.total"
                                class="btn"
                            >Next</button>
                        </div>
                    </div>
                </div>

                <!-- Empty State -->
                <div v-else class="section-card flex flex-col items-center justify-center h-full path-text">
                    <span class="text-6xl mb-4">🌳</span>
                    <p>Select a node from the tree</p>
                </div>
            </main>
        </div>
    </div>

    <script>
    const { createApp, ref, computed, watch, onMounted } = Vue;

    // Tree Node Component
    const TreeNode = {
        name: 'TreeNode',
        props: ['node', 'depth', 'selectedId'],
        emits: ['select'],
        template: `
            <div class="tree-node">
                <div
                    @click="toggle"
                    class="flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer select-none"
                    :class="node.id === selectedId ? 'node-selected' : 'node-default'"
                    :style="{ paddingLeft: (depth * 16 + 8) + 'px' }"
                >
                    <span
                        v-if="node.type === 'category'"
                        class="w-4 path-text text-xs"
                        @click.stop="toggleExpand"
                    >{{ expanded ? '▼' : '▶' }}</span>
                    <span v-else class="w-4"></span>
                    <span>{{ node.type === 'category' ? '📂' : '📄' }}</span>
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2 min-w-0">
                            <span class="truncate text-sm" :class="node.type === 'category' ? 'text-accent font-medium' : 'text-main'">
                                {{ node.name }}
                            </span>
                            <span v-if="node.type === 'category' && childCount !== null" class="text-xs path-text mono">
                                ({{ childCount }})
                            </span>
                        </div>
                        <div v-if="node.type === 'category'" class="flex flex-wrap gap-1 mt-1">
                            <span
                                v-if="node.keywords?.length"
                                v-for="kw in node.keywords.slice(0, 2)"
                                :key="kw"
                                class="keyword-chip"
                            >{{ kw }}</span>
                            <span v-else class="keyword-chip keyword-chip-muted">no keywords</span>
                        </div>
                    </div>
                </div>
                <div v-if="expanded && children.length">
                    <tree-node
                        v-for="child in children"
                        :key="child.id"
                        :node="child"
                        :depth="depth + 1"
                        :selected-id="selectedId"
                        @select="$emit('select', $event)"
                    />
                </div>
                <div v-if="expanded && loading" class="text-xs path-text py-1" :style="{ paddingLeft: ((depth + 1) * 16 + 24) + 'px' }">
                    Loading...
                </div>
                <div v-if="expanded && hasMore" class="py-1" :style="{ paddingLeft: ((depth + 1) * 16 + 24) + 'px' }">
                    <button @click.stop="loadMore" class="text-xs text-accent hover:underline">
                        Load more ({{ childCount - children.length }} remaining)
                    </button>
                </div>
            </div>
        `,
        data() {
            return {
                expanded: this.depth === 0,
                children: [],
                childCount: null,
                loading: false,
                offset: 0,
            };
        },
        computed: {
            hasMore() {
                return this.childCount !== null && this.children.length < this.childCount;
            }
        },
        methods: {
            toggle() {
                this.$emit('select', this.node);
            },
            async toggleExpand() {
                if (this.node.type !== 'category') return;
                this.expanded = !this.expanded;
                if (this.expanded && this.children.length === 0) {
                    await this.loadChildren();
                }
            },
            async loadChildren() {
                this.loading = true;
                try {
                    const res = await fetch(`/api/node/${this.node.id}/children?offset=${this.offset}&limit=20`);
                    const data = await res.json();
                    this.children = data.items;
                    this.childCount = data.total;
                    this.offset = data.offset + data.items.length;
                } finally {
                    this.loading = false;
                }
            },
            async loadMore() {
                this.loading = true;
                try {
                    const res = await fetch(`/api/node/${this.node.id}/children?offset=${this.offset}&limit=20`);
                    const data = await res.json();
                    this.children.push(...data.items);
                    this.offset = this.offset + data.items.length;
                } finally {
                    this.loading = false;
                }
            }
        },
        async mounted() {
            if (this.depth === 0 && this.node.type === 'category') {
                await this.loadChildren();
            }
        }
    };

    createApp({
        components: { TreeNode },
        setup() {
            const stats = ref(null);
            const rootNode = ref(null);
            const selectedNode = ref(null);
            const breadcrumb = ref([]);
            const children = ref(null);
            const searchQuery = ref('');
            const searchResults = ref(null);

            const formatNumber = (n) => n?.toLocaleString() ?? '0';

            const loadStats = async () => {
                const res = await fetch('/api/stats');
                stats.value = await res.json();
            };

            const loadRoot = async () => {
                const res = await fetch('/api/root');
                rootNode.value = await res.json();
                selectNode(rootNode.value);
            };

            const selectNode = async (node) => {
                selectedNode.value = node;
                // Load breadcrumb
                const res = await fetch(`/api/node/${node.id}/ancestors`);
                breadcrumb.value = await res.json();
                // Load children if category
                if (node.type === 'category') {
                    await loadChildren(0);
                } else {
                    children.value = null;
                }
            };

            const loadChildren = async (offset = 0) => {
                if (!selectedNode.value) return;
                const res = await fetch(`/api/node/${selectedNode.value.id}/children?offset=${offset}&limit=20`);
                children.value = await res.json();
            };

            const search = async () => {
                if (!searchQuery.value.trim()) return;
                const res = await fetch(`/api/search?q=${encodeURIComponent(searchQuery.value)}&limit=20`);
                searchResults.value = await res.json();
            };

            const searchPage = async (offset) => {
                if (offset < 0) return;
                const res = await fetch(`/api/search?q=${encodeURIComponent(searchQuery.value)}&offset=${offset}&limit=20`);
                searchResults.value = await res.json();
            };

            const clearSearch = () => {
                searchResults.value = null;
                searchQuery.value = '';
            };

            onMounted(() => {
                loadStats();
                loadRoot();
            });

            return {
                stats, rootNode, selectedNode, breadcrumb, children,
                searchQuery, searchResults,
                formatNumber, selectNode, loadChildren, search, searchPage, clearSearch
            };
        }
    }).mount('#app');
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
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"Database not found: {args.db}")
        return 1

    global db
    db = NodeDB(args.db)

    print(f"SemaFS Viewer starting at http://{args.host}:{args.port}")
    print(f"Database: {args.db}")
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(view())
