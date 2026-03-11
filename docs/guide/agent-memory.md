# Agent Memory Integration

Build LLM Agents with persistent, self-organizing memory using SemaFS.

## Overview

SemaFS provides an ideal memory backend for LLM Agents. Unlike flat key-value stores or vector databases, SemaFS offers:

- **Hierarchical context**: Agents understand where memories live in a semantic tree
- **Automatic organization**: New memories are merged and grouped intelligently
- **Token-efficient views**: `LLMRenderer` outputs minimize context window usage
- **Structured navigation**: Agents can browse and explore the knowledge tree

```
Traditional Agent Memory:          SemaFS Agent Memory:
┌─────────────────────┐            root/
│ memory_1: "..."     │            ├── user_preferences/
│ memory_2: "..."     │   vs       │   ├── food (merged notes)
│ memory_3: "..."     │            │   └── work_style
│ ... (no structure)  │            └── conversations/
└─────────────────────┘                └── project_alpha
```

## Defining Agent Tools

Expose SemaFS operations as tools for your LLM Agent:

```python
from semafs import SemaFS
from semafs.renderer import LLMRenderer

# Tool definitions for function calling
SEMAFS_TOOLS = [
    {
        "name": "memory_read",
        "description": "Read a specific memory location and its content",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Memory path like 'root.preferences.food'"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "memory_tree",
        "description": "View the memory tree structure from a given path",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Starting path (default: 'root')"
                },
                "depth": {
                    "type": "integer",
                    "description": "How many levels deep (default: 2)"
                }
            }
        }
    },
    {
        "name": "memory_search",
        "description": "Search memories for a keyword or phrase",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "path": {
                    "type": "string",
                    "description": "Search under this path (default: 'root')"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "memory_write",
        "description": "Store a new memory in the knowledge base",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Target category path"
                },
                "content": {
                    "type": "string",
                    "description": "Memory content to store"
                },
                "source": {
                    "type": "string",
                    "description": "Source of this memory (e.g., 'user', 'conversation')"
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "memory_stats",
        "description": "Get statistics about the memory knowledge base",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
]
```

## Tool Implementation

Implement the tool handlers that connect to SemaFS:

```python
class AgentMemory:
    """Memory interface for LLM Agents."""

    def __init__(self, semafs: SemaFS):
        self.semafs = semafs

    async def handle_tool(self, name: str, args: dict) -> str:
        """Route tool calls to appropriate handlers."""
        handlers = {
            "memory_read": self.read,
            "memory_tree": self.view_tree,
            "memory_search": self.search,
            "memory_write": self.write,
            "memory_stats": self.stats,
        }
        handler = handlers.get(name)
        if not handler:
            return f"Unknown tool: {name}"
        return await handler(**args)

    async def read(self, path: str) -> str:
        """Read a single memory location."""
        view = await self.semafs.read(path)
        if not view:
            return f"No memory found at: {path}"
        return LLMRenderer.render_node(view)

    async def view_tree(self, path: str = "root", depth: int = 2) -> str:
        """View memory tree structure."""
        tree = await self.semafs.view_tree(path, max_depth=depth)
        if not tree:
            return f"Path not found: {path}"
        return LLMRenderer.render_tree(tree)

    async def search(self, query: str, path: str = "root") -> str:
        """Search memories by content."""
        tree = await self.semafs.view_tree(path, max_depth=10)
        if not tree:
            return f"Path not found: {path}"

        results = []
        self._search_tree(tree, query.lower(), results)

        if not results:
            return f"No memories found matching: {query}"

        lines = [f"Found {len(results)} memories matching '{query}':"]
        for node in results[:10]:  # Limit to top 10
            preview = node.content[:80].replace("\n", " ")
            lines.append(f"- [{node.path}] {preview}...")
        return "\n".join(lines)

    def _search_tree(self, tree, query: str, results: list):
        """Recursively search tree for matching content."""
        if query in tree.node.content.lower():
            results.append(tree.node)
        for child in tree.children:
            self._search_tree(child, query, results)

    async def write(self, path: str, content: str, source: str = "agent") -> str:
        """Write a new memory."""
        fragment_id = await self.semafs.write(
            path=path,
            content=content,
            payload={"source": source}
        )
        return f"Memory saved (id: {fragment_id[:8]}...) at {path}"

    async def stats(self) -> str:
        """Get memory statistics."""
        stats = await self.semafs.stats()
        return (
            f"Memory Stats:\n"
            f"- Total nodes: {stats.total_nodes}\n"
            f"- Categories: {stats.total_categories}\n"
            f"- Leaves: {stats.total_leaves}\n"
            f"- Max depth: {stats.max_depth}"
        )
```

## Reading Memories

### Single Node Read

Get detailed information about a specific memory location:

```python
# Agent requests: memory_read(path="root.preferences.food")

view = await semafs.read("root.preferences.food")
output = LLMRenderer.render_node(view)

# Output (token-efficient format):
# [DIR] root.preferences.food
#   Contains: 3 items
#   User prefers dark roast coffee, especially Ethiopian single-origin...
```

### Tree Navigation

Explore the memory structure:

```python
# Agent requests: memory_tree(path="root", depth=2)

tree = await semafs.view_tree("root", max_depth=2)
output = LLMRenderer.render_tree(tree)

# Output:
# root/ (3)
#   preferences/ (2)
#     food/ (3)
#     work/ (2)
#   conversations/ (5)
#   projects/ (1)
```

### Related Nodes

Get navigation context:

```python
# For orientation within the tree
related = await semafs.get_related("root.preferences.food")
output = LLMRenderer.render_related(related)

# Output:
# Current: root.preferences.food
# Parent: root.preferences
# Siblings: work
# Children: coffee, cuisine, dietary
```

## Searching Memories

### Content Search

```python
async def search_memories(semafs: SemaFS, query: str, root: str = "root") -> list:
    """Search all memories for matching content."""
    tree = await semafs.view_tree(root, max_depth=10)
    results = []

    def search(t):
        if query.lower() in t.node.content.lower():
            results.append(t.node)
        for child in t.children:
            search(child)

    search(tree)
    return results

# Usage
matches = await search_memories(semafs, "coffee")
for node in matches:
    print(f"[{node.path}] {node.content[:50]}...")
```

### Path-Based Search

```python
# Find all memories under a specific category
tree = await semafs.view_tree("root.preferences", max_depth=5)

# Get all leaf nodes
def get_leaves(t) -> list:
    from semafs.core.enums import NodeType
    if t.node.node_type == NodeType.LEAF:
        return [t.node]
    leaves = []
    for child in t.children:
        leaves.extend(get_leaves(child))
    return leaves

all_preferences = get_leaves(tree)
```

### Context-Aware Retrieval

For RAG-style retrieval, combine with the stats view:

```python
async def get_relevant_context(semafs: SemaFS, topic: str) -> str:
    """Get relevant context for a topic."""
    stats = await semafs.stats()

    # Find most relevant category
    best_path = None
    for path, count in stats.top_categories:
        if topic.lower() in path.lower():
            best_path = path
            break

    if best_path:
        tree = await semafs.view_tree(best_path, max_depth=3)
        return LLMRenderer.render_tree(tree, max_content_len=150)

    # Fallback to root overview
    tree = await semafs.view_tree("root", max_depth=2)
    return LLMRenderer.render_tree(tree)
```

## Writing Memories

### Basic Write

```python
# Agent decides to remember something
await semafs.write(
    path="root.preferences",
    content="User prefers morning meetings before 10am",
    payload={"source": "conversation", "confidence": 0.9}
)
```

### Contextual Writing

Write with rich metadata:

```python
await semafs.write(
    path="root.conversations.project_alpha",
    content="User decided to use PostgreSQL for the database",
    payload={
        "source": "conversation",
        "timestamp": "2024-03-15T10:30:00Z",
        "topic": "database_decision",
        "confidence": 1.0
    }
)
```

### Background Maintenance

For best performance, batch writes and maintain periodically:

```python
class AgentMemoryWithMaintenance:
    def __init__(self, semafs: SemaFS):
        self.semafs = semafs
        self.pending_writes = 0

    async def write(self, path: str, content: str, payload: dict = None):
        """Write with automatic maintenance."""
        await self.semafs.write(path, content, payload or {})
        self.pending_writes += 1

        # Maintain every 5 writes or on important memories
        if self.pending_writes >= 5 or payload.get("important"):
            await self.semafs.maintain()
            self.pending_writes = 0

    async def flush(self):
        """Force maintenance of all pending writes."""
        if self.pending_writes > 0:
            await self.semafs.maintain()
            self.pending_writes = 0
```

## Complete Agent Example

Here's a full example integrating SemaFS with an OpenAI-style agent:

```python
import asyncio
from openai import AsyncOpenAI
from semafs import SemaFS
from semafs.storage.sqlite.factory import SQLiteUoWFactory
from semafs.strategies.hybrid import HybridStrategy
from semafs.infra.llm.openai import OpenAIAdapter
from semafs.renderer import LLMRenderer

class MemoryAgent:
    """LLM Agent with persistent SemaFS memory."""

    def __init__(self, client: AsyncOpenAI, semafs: SemaFS):
        self.client = client
        self.memory = AgentMemory(semafs)
        self.tools = SEMAFS_TOOLS  # Tool definitions from above

    async def chat(self, user_message: str) -> str:
        # Build context with memory stats
        stats = await self.memory.stats()
        tree = await self.memory.view_tree("root", depth=2)

        system_prompt = f"""You are a helpful assistant with persistent memory.

Current memory overview:
{tree}

{stats}

Use the memory tools to:
- memory_read: Get details about a specific memory
- memory_tree: Browse the memory structure
- memory_search: Find relevant memories
- memory_write: Store new information you learn
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        # Call LLM with tools
        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=[{"type": "function", "function": t} for t in self.tools],
            tool_choice="auto"
        )

        # Handle tool calls
        message = response.choices[0].message
        if message.tool_calls:
            for tool_call in message.tool_calls:
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                result = await self.memory.handle_tool(name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })

            # Get final response
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages
            )

        return response.choices[0].message.content


async def main():
    # Setup SemaFS
    factory = SQLiteUoWFactory("agent_memory.db")
    await factory.init()

    client = AsyncOpenAI()
    adapter = OpenAIAdapter(client, model="gpt-4o-mini")
    strategy = HybridStrategy(adapter)
    semafs = SemaFS(factory, strategy)

    # Create agent
    agent = MemoryAgent(client, semafs)

    # Chat loop
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["quit", "exit"]:
            break

        response = await agent.chat(user_input)
        print(f"Agent: {response}")

        # Maintain memories after each conversation
        await semafs.maintain()

    await factory.close()


if __name__ == "__main__":
    asyncio.run(main())
```

## LLMRenderer Output Formats

The `LLMRenderer` is specifically designed for token efficiency:

### Node Format

```
[DIR] root.preferences.food
  Contains: 3 items
  User prefers dark roast coffee, especially Ethiopian...
```

### Tree Format

```
root/ (3)
  preferences/ (2)
    food/ (3)
      - coffee: Loves dark roast, Ethiopian single-origin...
      - cuisine: Enjoys Italian and Japanese food...
    work/ (2)
  projects/ (1)
```

### Related Format

```
Current: root.preferences.food
Parent: root.preferences
Siblings: work
Children: coffee, cuisine, dietary
```

## Best Practices

### 1. Provide Memory Context in System Prompt

```python
# Good: Include memory overview
stats = await semafs.stats()
tree = await semafs.view_tree("root", depth=2)
system_prompt = f"Your memory:\n{LLMRenderer.render_tree(tree)}\n{stats.summary}"
```

### 2. Write Important Learnings Immediately

```python
# When agent learns something important
await semafs.write(
    "root.user_info",
    f"User's name is {name}",
    {"source": "conversation", "important": True}
)
await semafs.maintain()  # Organize immediately
```

### 3. Use Appropriate Depth for Context

```python
# Overview (low token cost)
tree = await semafs.view_tree("root", max_depth=2)

# Detailed context (higher token cost)
tree = await semafs.view_tree("root.preferences", max_depth=4)
```

### 4. Search Before Writing Duplicates

```python
async def remember_if_new(semafs, path, content):
    """Only write if similar content doesn't exist."""
    matches = await search_memories(semafs, content[:50])
    if not matches:
        await semafs.write(path, content, {})
```

### 5. Maintain Periodically, Not After Every Write

```python
# Batch writes
for item in items_to_remember:
    await semafs.write("root.data", item, {})

# Single maintenance pass
await semafs.maintain()
```

## Next Steps

- [Reading & Querying](./reading) - Deep dive into read operations
- [Writing Memories](./writing) - Detailed write patterns
- [LLM Integration](./llm-integration) - Configure LLM providers
- [Maintenance](./maintenance) - Understand auto-organization
