# Quick Start

Get SemaFS up and running in 5 minutes.

## Installation

::: code-group

```bash [pip]
# Basic installation (rule-based only)
pip install semafs

# With OpenAI support
pip install semafs[openai]

# With Anthropic support
pip install semafs[anthropic]

# All providers
pip install semafs[all]
```

```bash [poetry]
poetry add semafs

# With extras
poetry add semafs[openai]
```

```bash [from source]
git clone https://github.com/linzwcs/semafs.git
cd semafs
pip install -e ".[dev]"
```

:::

## Minimal Example (No LLM)

This example uses rule-based maintenance—no API key required.

```python
import asyncio
from semafs import SemaFS
from semafs.storage.sqlite import SQLiteUoWFactory
from semafs.strategies.rule import RuleOnlyStrategy

async def main():
    # 1. Initialize storage
    factory = SQLiteUoWFactory("knowledge.db")
    await factory.init()

    # 2. Create SemaFS instance
    semafs = SemaFS(
        uow_factory=factory,
        strategy=RuleOnlyStrategy()
    )

    # 3. Write some knowledge fragments
    await semafs.write("root.work", "Completed sprint planning today")
    await semafs.write("root.work", "Updated API documentation")
    await semafs.write("root.personal", "Need to buy coffee beans")

    # 4. Run maintenance (organizes fragments)
    processed = await semafs.maintain()
    print(f"Processed {processed} categories")

    # 5. Read back the organized knowledge
    tree = await semafs.view_tree("root", max_depth=3)
    print(tree)

    # 6. Read a specific node
    work = await semafs.read("root.work")
    if work:
        print(f"Work summary: {work.content}")

    # Cleanup
    await factory.close()

asyncio.run(main())
```

## With OpenAI (Smart Maintenance)

For intelligent reorganization, add an LLM:

```python
import asyncio
from openai import AsyncOpenAI
from semafs import SemaFS
from semafs.storage.sqlite import SQLiteUoWFactory
from semafs.infra.llm.openai import OpenAIAdapter
from semafs.strategies.hybrid import HybridStrategy

async def main():
    # Setup storage
    factory = SQLiteUoWFactory("knowledge.db")
    await factory.init()

    # Setup LLM adapter
    client = AsyncOpenAI()  # Uses OPENAI_API_KEY env var
    adapter = OpenAIAdapter(client, model="gpt-4o-mini")

    # Create hybrid strategy (LLM + rule fallback)
    strategy = HybridStrategy(
        llm_adapter=adapter,
        max_nodes=8  # Trigger LLM when category has >8 children
    )

    # Create SemaFS
    semafs = SemaFS(factory, strategy)

    # Write fragments
    await semafs.write("root.food", "I love dark roast coffee")
    await semafs.write("root.food", "Ethiopian beans are my favorite")
    await semafs.write("root.food", "No sugar in my coffee")
    await semafs.write("root.food", "Sometimes I add oat milk")

    # Maintain - LLM will merge these into a single "coffee_preferences" node
    await semafs.maintain()

    # See the organized result
    tree = await semafs.view_tree("root.food", max_depth=2)
    print(tree)

asyncio.run(main())
```

## CLI Usage

SemaFS includes a command-line interface:

```bash
# Run in mock mode (no LLM)
python -m semafs.run

# Run with OpenAI
export OPENAI_API_KEY="sk-..."
python -m semafs.run --openai

# Use custom database
python -m semafs.run --db my_knowledge.db

# Export to Markdown
python -m semafs.run --export -o output.md

# Verbose logging
python -m semafs.run -v
```

## Project Structure

After running, you'll have:

```
your_project/
├── knowledge.db      # SQLite database
└── your_script.py    # Your application
```

The database contains a single table `semafs_nodes` with your entire knowledge tree.

## What's Next?

- [Core Concepts](./concepts) - Understand nodes, paths, and lifecycle
- [Writing Memories](./writing) - Deep dive into the write API
- [Maintenance](./maintenance) - How automatic organization works
- [LLM Integration](./llm-integration) - Configure different LLM providers
