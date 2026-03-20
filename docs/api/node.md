# Node and Path Model API

Defined in `semafs/core/node.py`.

## 1. Enums

- `NodeType`: `CATEGORY`, `LEAF`
- `NodeStage`: `ACTIVE`, `PENDING`, `COLD`, `ARCHIVED`

## 2. `NodePath`

Capabilities:

- validate canonical path format
- construct root and child paths
- parent/name/depth accessors

Key methods/properties:

- `NodePath.root()`
- `NodePath.from_parent_and_name(...)`
- `.parent`, `.parent_str`, `.name`, `.depth`, `.child(...)`

## 3. `Node`

Immutable entity with strict invariants.

### 3.1 Factory Methods

- `create_root()`
- `create_category(...)`
- `create_leaf(...)`

### 3.2 Immutable Update Methods

- `with_summary(...)`
- `with_category_meta(...)`
- `with_name(...)`
- `with_name_editable(...)`
- `with_skeleton(...)`
- `with_parent(...)`
- `with_path_projection(...)`
- `with_stage(...)`
- `with_payload(...)`

### 3.3 Name Normalization

`Node.normalize_name(raw_name)` normalizes arbitrary input to `[a-z0-9_]+`, with fallback prefix handling.

## 4. Invariant Highlights

- category requires summary
- leaf requires content
- leaf cannot be skeleton
- skeleton nodes are name-locked
