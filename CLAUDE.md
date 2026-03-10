# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SemaFS is a semantic filesystem that uses LLM-powered strategies to automatically organize and maintain a hierarchical tree of knowledge fragments. It implements a clean architecture with ports & adapters pattern, supporting multiple storage backends and organization strategies.

**Core Concept**: Users write memory fragments to categories, and SemaFS automatically reorganizes them using either rule-based or LLM-based strategies (merge, group, move operations) to keep the knowledge tree well-structured and semantically coherent.

## Commands

### Testing
```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_semafs.py -v

# Run with detailed output
python -m pytest tests/ -v -s

```

### Running SemaFS

```bash
# Mock mode (no API key required) - uses RuleOnlyStrategy
python -m semafs.run

# OpenAI mode (requires OPENAI_API_KEY)
python -m semafs.run --openai

# Stream mode (shuffled order with random delays)
python -m semafs.run --stream

# Custom database path
python -m semafs.run --db ./custom.db

# Export database to Markdown
python -m semafs.run --export
python -m semafs.run --export -o output.md

# Verbose logging
python -m semafs.run -v
```

## Architecture

### Core Flow (Write → Maintain Loop)

1. **Write Phase**: `SemaFS.write(path, content, payload)`
   - Resolves the target category path
   - Creates a FRAGMENT node with status=PENDING_REVIEW
   - Marks parent category as dirty
   - Commits to database via UnitOfWork

2. **Maintain Phase**: `SemaFS.maintain()`
   - Fetches all dirty categories (deepest first)
   - For each dirty category:
     - Captures `UpdateContext` snapshot (parent, active_nodes, pending_nodes)
     - Calls `Strategy.create_plan(context)` to get a `RebalancePlan`
     - `Executor.execute(plan, context, uow)` applies the plan
     - Updates parent category content/name based on plan results
     - Commits all changes atomically

3. **Read Phase**: Views & Renderers (Elegant Separation)
   - **Core Methods** (4 elegant read operations):
     - `SemaFS.read(path)` → Returns `NodeView` (single node + navigation context)
     - `SemaFS.list(path)` → Returns `List[NodeView]` (direct children only)
     - `SemaFS.view_tree(path, max_depth)` → Returns `TreeView` (recursive tree structure)
     - `SemaFS.get_related(path)` → Returns `RelatedNodes` (navigation map)
     - `SemaFS.stats()` → Returns `StatsView` (knowledge base statistics)

   - **View Layer** (`views.py`): Frozen dataclasses containing only data
     - `NodeView`: Single node + navigation context
     - `TreeView`: Recursive tree structure
     - `RelatedNodes`: Navigation map (parent/siblings/children/ancestors)
     - `StatsView`: Knowledge base statistics

   - **Renderer Layer** (`renderer.py`): Pure functions for format conversion
     - `TextRenderer`: Terminal-friendly tree output
     - `MarkdownRenderer`: Export to Markdown documents
     - `LLMRenderer`: Minimalist format optimized for LLM context (lowest token cost)
     - `JSONRenderer`: Structured data for APIs

**Design Philosophy**: Data is data, presentation is presentation—never mix them.

### Key Architectural Patterns

#### Ports & Adapters (Hexagonal Architecture)

- **Ports** (interfaces in `semafs/ports/`):
  - `NodeRepository`: Storage operations (get, list, stage, commit, rollback)
  - `Strategy`: Create reorganization plans from context
  - `BaseLLMAdapter`: Abstract LLM API calls
  - `UoWFactory`: Create UnitOfWork instances with transaction management

- **Adapters** (implementations):
  - Storage: `SQLiteRepository` (in `semafs/storage/sqlite/`)
  - Strategies: `RuleOnlyStrategy`, `HybridStrategy` (in `semafs/strategies/`)
  - LLM: `OpenAIAdapter`, `AnthropicAdapter` (in `semafs/infra/llm/`)

#### Unit of Work Pattern

`UnitOfWork` (`semafs/uow.py`) acts as a transactional "shopping cart":
- `register_new(node)`: Stage new nodes
- `register_dirty(node)`: Stage modified nodes
- `register_cascade_rename(old_path, new_path)`: Stage path renames
- `commit()`: Persist all changes atomically
- `rollback()`: Discard all staged changes

The Executor never commits directly - it only registers changes to UoW, letting the caller control transaction boundaries.

#### Domain Model (Core Layer)

**TreeNode** (`semafs/core/node.py`):
- Immutable path composition via `NodePath` value object
- Two node types: CATEGORY (directory) and LEAF (content)
- Four statuses: ACTIVE, PENDING_REVIEW, PROCESSING, ARCHIVED
- Rich domain behaviors: `receive_fragment()`, `archive()`, `start_processing()`, `finish_processing()`, `request_semantic_rethink()`

**Operations** (`semafs/core/ops.py`):
- Frozen dataclasses (pure data, no execution logic)
- `MergeOp`: Combine multiple leafs into one
- `GroupOp`: Create new category and move leafs into it
- `MoveOp`: Move leaf to existing category
- `PersistOp`: Convert PENDING_REVIEW fragment to ACTIVE leaf (rule-only)
- `RebalancePlan`: Contains ops sequence + updated parent content/name

**Executor** (`semafs/executor.py`):
- Executes `RebalancePlan` operations sequentially
- Zero direct SQL - all changes via UoW registration
- Uses context snapshot for node lookup (no mid-execution DB reads)
- Handles LLM hallucinations gracefully (skip invalid IDs, missing paths)

### Strategy Decision Logic

**HybridStrategy** (production mode):
1. No pending fragments + within threshold → Return `None` (skip maintenance)
2. Has pending but total nodes < max_nodes → Use rule-based fallback (no LLM call)
3. Exceeds threshold OR `_force_llm=True` in payload → Call LLM
4. LLM failure → Fallback to rule strategy

**RuleOnlyStrategy** (mock/test mode):
- Always uses fallback: Convert PENDING_REVIEW to ACTIVE via `PersistOp`
- Appends new content to parent's summary
- Never calls LLM

### Database Schema

Single table `semafs_nodes` in SQLite with:
- Unique constraint: `(parent_path, name)` for non-ARCHIVED nodes
- Path composition: `parent_path + "." + name`
- Root node: `parent_path=""`, `name="root"`
- JSON fields: `payload`, `tags`
- Dirty tracking: `is_dirty` flag for maintenance queue

### UpdateContext Enhancement

**New Context Fields** (added to prevent naming conflicts and provide hierarchical semantics):

- `sibling_categories`: Tuple of sibling CATEGORY nodes at the same level as parent
  - Used by LLM to avoid renaming conflicts when updating parent name
  - Only includes ACTIVE status categories, excludes parent itself
  - Empty tuple for root node

- `ancestor_categories`: Tuple of ancestor CATEGORY chain from parent to root
  - Ordered from nearest to farthest (parent's parent, grandparent, ..., root)
  - Limited to 3 levels by default for token efficiency
  - Provides hierarchical semantic context for smarter LLM decisions

**Helper Properties**:
- `sibling_category_names`: Quick access to sibling names as strings
- `ancestor_path_chain`: Full path chain from root to parent

**Performance**: Both fields are fetched in parallel using `asyncio.gather` during context construction in `SemaFS._maintain_one()`.

## Important Implementation Details

### Path Handling

- `NodePath` is a frozen value object that normalizes paths
- Always lowercase, only allows `[a-z0-9_.]`
- Root is represented as `"root"` (no parent_path)
- Child path: `parent_path.child_name`
- Use `NodePath.from_parent_and_name(parent, name)` for safe construction

### ID Resolution in Executor

The Executor supports both full UUIDs and 8-character short IDs:
- LLM may return shortened IDs from prompts
- `resolve(node_id)` checks both full ID and first 8 chars
- Non-existent IDs are gracefully skipped (no errors thrown)

### Transaction Safety

- All mutations go through UnitOfWork transaction
- Executor doesn't commit - caller controls when to commit
- Failed LLM calls trigger `rollback()` to restore PROCESSING nodes
- Status transitions: PENDING_REVIEW → PROCESSING → ACTIVE (on success) or PENDING_REVIEW (on failure)

### Concurrency & Dirty Flags

- `is_dirty=True` marks categories needing maintenance
- `maintain()` processes deepest categories first (leaf-to-root)
- Nodes entering PROCESSING state are locked from concurrent edits
- Parent categories can request `semantic_rethink()` to force LLM reorganization

### Testing Patterns

Tests are located in `tests/` directory:
- `conftest.py`: Pytest fixtures
- `memory_repo.py`: In-memory NodeRepository for fast tests
- `fixtures.py`: Test data (PREFERENCE_FRAGMENTS, TEST_CATEGORIES)
- Test files use async/await with `pytest-asyncio`

Run tests from project root with `pytest tests/` or `./run_tests.sh`.

## Project Structure

```
semafs/
├── core/           # Domain model (Node, Ops, Enums, Exceptions)
├── ports/          # Interfaces (Repository, Strategy, LLM, Factory)
├── strategies/     # Strategy implementations (Rule, Hybrid)
├── infra/          # Infrastructure adapters (OpenAI, Anthropic)
├── storage/        # Storage implementations (SQLite)
├── executor.py     # Plan execution engine
├── uow.py          # Unit of Work implementation
├── semafs.py       # Main facade (write/read/maintain API)
└── export.py       # Database export to Markdown

tests/              # Test suite
vault/              # Example test data (personal knowledge fragments)
```

## Configuration

Environment variables:
- `OPENAI_API_KEY`: Required for OpenAI mode
- No other config needed for mock mode

Key parameters:
- `max_children`: Threshold for triggering LLM reorganization (default: 10)
- `max_nodes`: Strategy-level threshold (default: 8 for HybridStrategy)

## Common Workflows

### Adding a New Operation Type

1. Define frozen dataclass in `semafs/core/ops.py`
2. Add enum value to `OpType` in `semafs/core/enums.py`
3. Implement execution logic in `Executor._do_<operation>()`
4. Update `HybridStrategy._parse_ops()` to parse from LLM output
5. Update LLM prompt in adapter to describe the new operation

### Adding a New Storage Backend

1. Implement `NodeRepository` protocol from `semafs/ports/repo.py`
2. Implement `UoWFactory` protocol from `semafs/ports/factory.py`
3. Ensure atomic transactions (commit/rollback)
4. Handle unique path generation with `ensure_unique_path()`
5. Support cascade rename for path updates

### Debugging LLM Plans

- Use `python -m semafs.run -v` for detailed logs
- Check `overall_reasoning` field in `RebalancePlan`
- Enable strategy logging: `logging.getLogger("semafs.strategies").setLevel(logging.DEBUG)`
- LLM adapter responses are logged with full JSON
