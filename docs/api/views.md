# View Objects API

Defined in `semafs/core/views.py`.

## 1. `NodeView`

Fields:

- `node`
- `breadcrumb`
- `child_count`
- `sibling_count`

Computed properties:

- `path`
- `is_category`
- `summary`

## 2. `TreeView`

Fields:

- `node`
- `children`
- `depth`

Computed properties:

- `path`
- `total_nodes`
- `leaf_count`

## 3. `RelatedNodes`

Fields:

- `current`
- `parent`
- `siblings`
- `children`
- `ancestors`

Computed property:

- `navigation_summary`

## 4. `StatsView`

Fields:

- `total_categories`
- `total_leaves`
- `max_depth`
- `dirty_categories`
- `top_categories`

Computed properties:

- `total_nodes`
- `summary`

## 5. Renderers

`semafs/renderer.py` maps view objects to output formats:

- `TextRenderer`
- `MarkdownRenderer`
- `LLMRenderer`
- `JSONRenderer`

Renderer layer is presentation-only and does not mutate view/state.
