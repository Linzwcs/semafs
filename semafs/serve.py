"""SemaFS web server entrypoint.

Provides:
- FastAPI app factory for node browsing/search
- `python -m semafs.serve` runnable server
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Optional


HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SemaFS Server</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>
  <style>
    [v-cloak] { display: none; }
    body {
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      background: #f7f8f5;
      color: #1f2a20;
    }
    .panel {
      background: #fff;
      border: 1px solid #d9dfd3;
      border-radius: 12px;
    }
    .muted { color: #718072; }
  </style>
</head>
<body>
  <div id="app" v-cloak class="max-w-7xl mx-auto p-4 md:p-6">
    <header class="mb-4 md:mb-6">
      <div class="flex flex-wrap items-center gap-3 justify-between">
        <h1 class="text-2xl font-semibold">SemaFS Server</h1>
        <div v-if="stats" class="text-sm muted">
          {{ stats.total }} nodes · {{ stats.categories }} categories · {{ stats.leaves }} leaves
        </div>
      </div>
    </header>

    <div class="grid grid-cols-1 lg:grid-cols-12 gap-4">
      <aside class="lg:col-span-4 panel p-3 overflow-y-auto max-h-[70vh]">
        <div class="mb-3">
          <input
            v-model="searchQuery"
            @keyup.enter="search"
            class="w-full border border-[#d9dfd3] rounded px-3 py-2 text-sm"
            placeholder="Search (name/content/summary), press Enter"
          />
        </div>
        <div v-if="searchResults" class="mb-3">
          <div class="flex items-center justify-between mb-2">
            <div class="text-sm font-medium">Search results ({{ searchResults.total }})</div>
            <button @click="clearSearch" class="text-sm muted hover:text-black">Clear</button>
          </div>
          <div class="space-y-2">
            <button
              v-for="item in searchResults.items"
              :key="item.id"
              class="w-full text-left border border-[#e3e8df] rounded p-2 hover:bg-[#f5f8f2]"
              @click="selectNode(item); clearSearch()"
            >
              <div class="font-medium text-sm">{{ item.name }}</div>
              <div class="text-xs muted">{{ item.path }}</div>
            </button>
          </div>
        </div>

        <div v-if="rootNode">
          <tree-node :node="rootNode" :depth="0" :selected-id="selectedNode?.id" @select="selectNode" />
        </div>
      </aside>

      <main class="lg:col-span-8 space-y-4">
        <section v-if="selectedNode" class="panel p-4">
          <div class="text-sm muted mb-1">{{ selectedNode.path }}</div>
          <h2 class="text-xl font-semibold">{{ selectedNode.name }}</h2>
          <div class="text-sm muted mt-1">Type: {{ selectedNode.type }} · Stage: {{ selectedNode.stage }}</div>
          <p v-if="selectedNode.content" class="mt-4 whitespace-pre-wrap leading-relaxed text-sm">{{ selectedNode.content }}</p>
        </section>

        <section v-if="children?.items?.length" class="panel p-4">
          <h3 class="font-semibold mb-3">Children ({{ children.total }})</h3>
          <div class="space-y-2">
            <button
              v-for="child in children.items"
              :key="child.id"
              class="w-full text-left border border-[#e3e8df] rounded p-2 hover:bg-[#f5f8f2]"
              @click="selectNode(child)"
            >
              <div class="font-medium text-sm">{{ child.name }}</div>
              <div class="text-xs muted">{{ child.path }}</div>
            </button>
          </div>
        </section>
      </main>
    </div>
  </div>

  <script>
    const { createApp, ref, onMounted } = Vue;

    const TreeNode = {
      name: "TreeNode",
      props: ["node", "depth", "selectedId"],
      emits: ["select"],
      template: `
        <div>
          <div
            class="flex items-center gap-2 rounded px-2 py-1.5 cursor-pointer hover:bg-[#f5f8f2]"
            :class="node.id === selectedId ? 'bg-[#e8f2eb]' : ''"
            :style="{ paddingLeft: (8 + depth * 16) + 'px' }"
            @click="toggleSelect"
          >
            <button
              v-if="node.type === 'category'"
              class="text-xs muted w-4 text-left"
              @click.stop="toggleExpand"
            >{{ expanded ? '▼' : '▶' }}</button>
            <span v-else class="w-4"></span>
            <span class="text-sm">{{ node.name }}</span>
          </div>
          <div v-if="expanded && loading" class="text-xs muted px-2 py-1" :style="{ paddingLeft: (24 + depth * 16) + 'px' }">Loading...</div>
          <tree-node
            v-for="child in children"
            v-if="expanded"
            :key="child.id"
            :node="child"
            :depth="depth + 1"
            :selected-id="selectedId"
            @select="$emit('select', $event)"
          />
        </div>
      `,
      data() {
        return {
          expanded: this.depth === 0,
          loading: false,
          children: [],
        };
      },
      methods: {
        toggleSelect() {
          this.$emit("select", this.node);
        },
        async toggleExpand() {
          this.expanded = !this.expanded;
          if (this.expanded && this.children.length === 0) {
            await this.loadChildren();
          }
        },
        async loadChildren() {
          if (this.node.type !== "category") return;
          this.loading = true;
          try {
            const resp = await fetch(`/api/node/${this.node.id}/children?offset=0&limit=50`);
            const data = await resp.json();
            this.children = data.items || [];
          } finally {
            this.loading = false;
          }
        },
      },
      async mounted() {
        if (this.expanded && this.node.type === "category") {
          await this.loadChildren();
        }
      },
    };

    createApp({
      components: { TreeNode },
      setup() {
        const stats = ref(null);
        const rootNode = ref(null);
        const selectedNode = ref(null);
        const children = ref(null);
        const searchQuery = ref("");
        const searchResults = ref(null);

        const loadStats = async () => {
          const res = await fetch("/api/stats");
          stats.value = await res.json();
        };
        const loadRoot = async () => {
          const res = await fetch("/api/root");
          rootNode.value = await res.json();
          await selectNode(rootNode.value);
        };
        const selectNode = async (node) => {
          selectedNode.value = node;
          if (node.type === "category") {
            const res = await fetch(`/api/node/${node.id}/children?offset=0&limit=20`);
            children.value = await res.json();
          } else {
            children.value = null;
          }
        };
        const search = async () => {
          if (!searchQuery.value.trim()) return;
          const res = await fetch(`/api/search?q=${encodeURIComponent(searchQuery.value)}&offset=0&limit=20`);
          searchResults.value = await res.json();
        };
        const clearSearch = () => {
          searchResults.value = null;
          searchQuery.value = "";
        };

        onMounted(async () => {
          await Promise.all([loadStats(), loadRoot()]);
        });

        return {
          stats,
          rootNode,
          selectedNode,
          children,
          searchQuery,
          searchResults,
          selectNode,
          search,
          clearSearch,
        };
      },
    }).mount("#app");
  </script>
</body>
</html>
"""


class NodeDB:
    """SQLite query helper for server browsing APIs."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _active_where() -> str:
        return "COALESCE(is_archived, 0) = 0 AND stage != 'archived'"

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "parent_id": row["parent_id"],
            "name": row["name"],
            "path": row["canonical_path"],
            "type": row["node_type"],
            "stage": row["stage"],
            "content": row["content"] or row["summary"] or "",
            "tags": json.loads(row["tags"] or "[]"),
            "skeleton": bool(row["skeleton"]),
        }

    def get_root(self) -> Optional[dict]:
        with self._conn() as conn:
            cur = conn.execute("SELECT * FROM nodes WHERE canonical_path = 'root'")
            row = cur.fetchone()
            return self._row_to_dict(row) if row else None

    def get_node(self, node_id: str) -> Optional[dict]:
        with self._conn() as conn:
            cur = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,))
            row = cur.fetchone()
            return self._row_to_dict(row) if row else None

    def get_node_by_path(self, path: str) -> Optional[dict]:
        with self._conn() as conn:
            cur = conn.execute("SELECT * FROM nodes WHERE canonical_path = ?", (path,))
            row = cur.fetchone()
            return self._row_to_dict(row) if row else None

    def get_children(self, parent_id: str, offset: int = 0, limit: int = 50) -> dict:
        active = self._active_where()
        with self._conn() as conn:
            cur = conn.execute(
                f"SELECT COUNT(*) FROM nodes WHERE parent_id = ? AND {active}",
                (parent_id,),
            )
            total = cur.fetchone()[0]

            cur = conn.execute(
                f"""SELECT * FROM nodes
                    WHERE parent_id = ? AND {active}
                    ORDER BY node_type DESC, name ASC
                    LIMIT ? OFFSET ?""",
                (parent_id, limit, offset),
            )
            items = [self._row_to_dict(r) for r in cur.fetchall()]
            return {
                "items": items,
                "total": total,
                "offset": offset,
                "limit": limit,
            }

    def get_ancestors(self, node_id: str) -> list[dict]:
        ancestors: list[dict] = []
        with self._conn() as conn:
            current_id = node_id
            while current_id:
                cur = conn.execute("SELECT * FROM nodes WHERE id = ?", (current_id,))
                row = cur.fetchone()
                if not row:
                    break
                ancestors.insert(0, self._row_to_dict(row))
                current_id = row["parent_id"]
        return ancestors

    def search(self, query: str, offset: int = 0, limit: int = 50) -> dict:
        active = self._active_where()
        pattern = f"%{query}%"
        with self._conn() as conn:
            cur = conn.execute(
                f"""SELECT COUNT(*) FROM nodes
                    WHERE {active}
                    AND (name LIKE ? OR content LIKE ? OR summary LIKE ?)""",
                (pattern, pattern, pattern),
            )
            total = cur.fetchone()[0]

            cur = conn.execute(
                f"""SELECT * FROM nodes
                    WHERE {active}
                    AND (name LIKE ? OR content LIKE ? OR summary LIKE ?)
                    ORDER BY canonical_path ASC
                    LIMIT ? OFFSET ?""",
                (pattern, pattern, pattern, limit, offset),
            )
            items = [self._row_to_dict(r) for r in cur.fetchall()]
            return {
                "items": items,
                "total": total,
                "offset": offset,
                "limit": limit,
                "query": query,
            }

    def get_stats(self) -> dict:
        active = self._active_where()
        with self._conn() as conn:
            cur = conn.execute(f"SELECT COUNT(*) FROM nodes WHERE {active}")
            total = cur.fetchone()[0]
            cur = conn.execute(
                f"SELECT COUNT(*) FROM nodes WHERE node_type = 'category' AND {active}"
            )
            categories = cur.fetchone()[0]
            cur = conn.execute(
                f"SELECT COUNT(*) FROM nodes WHERE node_type = 'leaf' AND {active}"
            )
            leaves = cur.fetchone()[0]
            cur = conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE stage = 'pending' AND COALESCE(is_archived, 0) = 0"
            )
            pending = cur.fetchone()[0]
            cur = conn.execute(
                "SELECT MAX(LENGTH(canonical_path) - LENGTH(REPLACE(canonical_path, '.', ''))) FROM nodes"
            )
            max_depth = cur.fetchone()[0] or 0
            return {
                "total": total,
                "categories": categories,
                "leaves": leaves,
                "pending": pending,
                "max_depth": max_depth,
            }


def create_app(db_path: str):
    """Create FastAPI app for a specific database path."""
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import HTMLResponse
    except ImportError as exc:
        raise RuntimeError(
            "Missing server dependencies. Install with: pip install 'semafs[server]'"
        ) from exc

    app = FastAPI(title="SemaFS Server")
    node_db = NodeDB(db_path=db_path)

    @app.get("/api/stats")
    def api_stats():
        return node_db.get_stats()

    @app.get("/api/root")
    def api_root():
        root = node_db.get_root()
        if not root:
            raise HTTPException(404, "Root not found")
        return root

    @app.get("/api/node/{node_id}")
    def api_node(node_id: str):
        node = node_db.get_node(node_id)
        if not node:
            raise HTTPException(404, "Node not found")
        return node

    @app.get("/api/node/{node_id}/children")
    def api_node_children(node_id: str, offset: int = 0, limit: int = 50):
        return node_db.get_children(node_id, offset, limit)

    @app.get("/api/node/{node_id}/ancestors")
    def api_node_ancestors(node_id: str):
        return node_db.get_ancestors(node_id)

    @app.get("/api/path")
    def api_path(path: str):
        node = node_db.get_node_by_path(path)
        if not node:
            raise HTTPException(404, "Path not found")
        return node

    @app.get("/api/search")
    def api_search(q: str, offset: int = 0, limit: int = 50):
        return node_db.search(q, offset, limit)

    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTML_PAGE

    return app


def run_server(
    db: str = "data/semafs_real_llm.db",
    host: str = "127.0.0.1",
    port: int = 8080,
    reload: bool = False,
) -> None:
    """Run uvicorn server."""
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError(
            "Missing uvicorn. Install with: pip install 'semafs[server]'"
        ) from exc

    db_path = Path(db)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    app = create_app(str(db_path))
    uvicorn.run(app, host=host, port=port, reload=reload, log_level="warning")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run SemaFS web server")
    parser.add_argument("--db", default="data/semafs_real_llm.db", help="SQLite database path")
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument("--reload", action="store_true", help="Enable autoreload")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        run_server(db=args.db, host=args.host, port=args.port, reload=args.reload)
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"Error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
