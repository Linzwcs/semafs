# Reading and Querying

Read APIs are side-effect free and do not mutate tree structure.

## 1. Python Query Surface

```python
node = await fs.read("root.work")
children = await fs.list("root.work")
tree = await fs.tree("root", max_depth=3)
related = await fs.related("root.work")
stats = await fs.stats()
```

Return types:

- `read` -> `NodeView | None`
- `list` -> `list[NodeView]`
- `tree` -> `TreeView | None`
- `related` -> `RelatedNodes | None`
- `stats` -> `StatsView`

## 2. CLI Query Surface

```bash
semafs read root.work --provider openai --db data/demo.db
semafs list root.work --provider openai --db data/demo.db
semafs tree root --provider openai --db data/demo.db --max-depth 3
semafs stats --provider openai --db data/demo.db --output json
```

## 3. Query Semantics

- `read(path)`: one node plus navigation counters
- `list(path)`: direct children only (non-recursive)
- `tree(path,max_depth)`: recursive tree expansion
- `related(path)`: parent/siblings/children/ancestors neighborhood
- `stats()`: aggregate topology and maintenance pressure view

## 4. JSON Rendering

For automation and integration:

- `read/tree/stats` support JSON output via CLI
- MCP tools return structured dictionaries

## 5. Viewer Query Features

`semafs view` adds:

- full-text-like `LIKE` search over `name/content/summary`
- paginated child browsing
- ancestor chain endpoint for breadcrumbs
