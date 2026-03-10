# SemaFS - A Filesystem-Inspired Self-Organizing Memory Architecture for Autonomous Agents

<div align="center">

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*LLM-native filesystem for autonomous knowledge organization*

[Key Concepts](#-key-concepts) • [Architecture](#-architecture) • [Quick Start](#-quick-start) • [Documentation](CLAUDE.md)

</div>

---

## What is SemaFS?

SemaFS is a **filesystem-inspired memory**  that automatically organizes knowledge fragments using LLM-powered strategies. Unlike traditional systems where LLMs manipulate files blindly, SemaFS provides **native LLM integration** through structured views and declarative plans.

**The Innovation**: Separate *querying* (view-based), *writing* (fragments), and *maintenance* (autonomous reorganization) — enabling LLMs to work with rich semantic context instead of raw file paths.

---

## 🎯 Key Concepts

### 1. View-Based Queries
Traditional systems return raw paths. SemaFS returns **structured views** with full context:
- Navigation breadcrumbs and relationship awareness
- Sibling categories (prevents naming conflicts)
- Ancestor chain (defines semantic boundaries)
- Child counts and hierarchical position

**Impact**: LLMs understand *where they are* and *what's around them*, enabling intelligent reorganization.

### 2. Plan-Based Maintenance
Traditional systems execute commands immediately. SemaFS uses **declarative plans**:
- LLM creates a plan (what should happen)
- Executor applies it atomically (how to do it)
- All operations succeed together or roll back

**Impact**: ACID transactions, auditability, graceful error handling, separation of concerns.

### 3. Semantic Snapshots
Traditional systems read-then-write (race conditions). SemaFS captures **frozen context**:
- Consistent state during maintenance
- Parallel processing without interference
- Sibling/ancestor awareness for smart decisions

**Impact**: Snapshot isolation prevents conflicts, enables concurrent maintenance.

### 4. Hybrid Strategy
Traditional systems choose all-LLM (expensive) or no-LLM (dumb). SemaFS is **cost-aware**:
- Under capacity + new items → Simple rules (no cost)
- Over capacity or complex → LLM analysis
- LLM failure → Guaranteed fallback

**Impact**: Cost optimization, guaranteed reliability, graceful degradation.

### 5. Semantic Floating
Traditional systems keep changes local. SemaFS enables **bottom-up emergence**:
- Major reorganizations signal `should_dirty_parent`
- Insights bubble up through hierarchy
- Parent summaries stay synchronized

**Impact**: Adaptive structure, coherent hierarchy, emergent organization.

---

## 🏗️ Architecture

**Hexagonal Architecture (Ports & Adapters)**

```
┌─────────────────────────────────────────────────┐
│  Core Domain (Business Logic)                   │
│  • TreeNode: Rich entities with lifecycle       │
│  • Operations: Merge, Group, Move, Persist      │
│  • UpdateContext: Semantic snapshots            │
│  • Views: Structured read results               │
└─────────────────────────────────────────────────┘
                      ↕
┌─────────────────────────────────────────────────┐
│  Ports (Interfaces)                             │
│  • NodeRepository  • Strategy  • LLMAdapter     │
└─────────────────────────────────────────────────┘
                      ↕
┌─────────────────────────────────────────────────┐
│  Adapters (Implementations)                     │
│  • Storage: SQLite, In-Memory                   │
│  • Strategies: RuleOnly, Hybrid                 │
│  • LLM: OpenAI, Anthropic                       │
└─────────────────────────────────────────────────┘
```

**Write → Maintain → Read Cycle**

1. **Write**: Fragment inserted → Parent marked dirty
2. **Maintain**: Capture context → Strategy creates plan → Executor applies atomically
3. **Read**: Return structured views with full semantic context

---

## 🚀 Quick Start

### Installation

```bash
pip install semafs              # Basic (rule-based)
pip install semafs[openai]      # With OpenAI
pip install semafs[anthropic]   # With Anthropic
pip install semafs[all]         # All providers
```

### Basic Usage

```python
from semafs import SemaFS
from semafs.storage.sqlite import SQLiteUoWFactory
from semafs.strategies.rule import RuleOnlyStrategy

# Initialize
factory = SQLiteUoWFactory("knowledge.db")
await factory.init()
semafs = SemaFS(factory, RuleOnlyStrategy())

# Write fragments
await semafs.write("root.work", "Completed sprint planning", {})
await semafs.write("root.work", "Updated API docs", {})

# Maintain (reorganize)
await semafs.maintain()

# Read with rich context
view = await semafs.read("root.work")
tree = await semafs.view_tree("root", max_depth=3)
```

### With LLM

```python
from openai import AsyncOpenAI
from semafs.infra.llm.openai import OpenAIAdapter
from semafs.strategies.hybrid import HybridStrategy

client = AsyncOpenAI()
adapter = OpenAIAdapter(client, model="gpt-4o-mini")
strategy = HybridStrategy(adapter, max_children=10)

semafs = SemaFS(factory, strategy)
```

### CLI

```bash
semafs init knowledge.db
semafs write knowledge.db root.work "Meeting notes" --maintain
semafs read knowledge.db root.work
semafs maintain knowledge.db --llm openai
semafs export knowledge.db -o output.md
```

---

## 🌍 Why SemaFS?

| Feature | Traditional FS | Vector DB | Knowledge Graph | **SemaFS** |
|---------|---------------|-----------|-----------------|------------|
| LLM Integration | External agent | Embeddings | Query language | **Native views** |
| Context | None | Similarity | Relations | **Hierarchical + semantic** |
| Maintenance | Manual | Re-indexing | Manual | **Autonomous plans** |
| Consistency | File locks | Eventual | ACID | **ACID + snapshots** |
| Fallback | N/A | N/A | N/A | **Guaranteed** |
| Cost | N/A | Always | N/A | **Optimized** |

---

## 📚 Use Cases

- **Personal Knowledge**: Auto-organize notes, ideas, research
- **Team Docs**: Maintain coherent structure as content grows
- **Research**: Categorize papers and findings semantically
- **Code Knowledge**: Organize decisions, patterns, learnings
- **Meeting Notes**: Auto-group and summarize by topic

---

## 🎓 Research Contributions

1. **View-Based LLM Interfaces**: Structured context vs. raw data
2. **Declarative Plan Execution**: Decision/execution separation
3. **Semantic Snapshot Isolation**: Consistent concurrent maintenance
4. **Hybrid Cost-Aware Strategies**: Dynamic LLM/rule selection
5. **Semantic Floating**: Bottom-up knowledge emergence

---

## 📖 Documentation

- **[CLAUDE.md](CLAUDE.md)**: Complete architecture guide
- **[Examples](vault/)**: Sample knowledge fragments
- **[Tests](tests/)**: Comprehensive test suite

---

## 🛠️ Development

```bash
git clone https://github.com/linzwcs/semafs.git
cd semafs
pip install -e ".[dev]"
pytest tests/ -v
```

**Project Structure**

```
semafs/
├── core/          # Domain model (Node, Ops, Views)
├── ports/         # Interfaces (Repository, Strategy, LLM)
├── strategies/    # RuleOnly, Hybrid implementations
├── storage/       # SQLite backend
├── infra/         # LLM adapters (OpenAI, Anthropic)
├── executor.py    # Plan execution engine
├── uow.py         # Unit of Work (transactions)
└── semafs.py      # Main facade
```

---

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.
