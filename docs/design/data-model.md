# Data Model

## 1. Node Entity

`Node` is an immutable dataclass (`frozen=True`) in `core/node.py`.

Key fields:

- identity: `id`, `parent_id`
- naming/path: `name`, `canonical_path`
- shape: `node_type` (`category` or `leaf`)
- content: `content` (leaf), `summary` (category)
- metadata: `category_meta`, `payload`, `tags`
- lifecycle: `stage`
- governance: `skeleton`, `name_editable`

## 2. Invariants

`Node.__post_init__` enforces invariants such as:

- leaf nodes must have `content`
- category nodes must have `summary`
- leaf nodes cannot carry category metadata
- skeleton nodes must be non-editable in name

## 3. Path Value Object

`NodePath` validates and manipulates canonical paths:

- root is exactly `root`
- child segments use `[a-z0-9_]`
- helpers: `parent`, `name`, `depth`, `child(...)`

## 4. Lifecycle Stage Model

`NodeStage` values:

- `PENDING`
- `ACTIVE`
- `COLD`
- `ARCHIVED`

These stages influence maintenance participation.

## 5. Snapshot Model

`Snapshot` captures immutable maintenance context:

- target category
- leaves, pending leaves, subcategories
- siblings and ancestors
- budget and used path set
- optional cold leaves

## 6. Plan Models

Two-layer operation model:

- raw layer: `RawPlan` and raw ops
- executable layer: `Plan` and typed ops

`Plan` may include parent updates:

- `updated_summary`
- `updated_keywords`
- `updated_name`

## 7. View Models

Read APIs return view-specific objects:

- `NodeView`
- `TreeView`
- `RelatedNodes`
- `StatsView`

This separates query representation from storage representation.
