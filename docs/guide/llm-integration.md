# LLM Integration

Configure LLM providers for intelligent knowledge organization.

## Supported Providers

| Provider | Adapter | Recommended Model |
|----------|---------|-------------------|
| OpenAI | `OpenAIAdapter` | `gpt-4o-mini` |
| Anthropic | `AnthropicAdapter` | `claude-3-haiku-20240307` |

## OpenAI Setup

### Installation

```bash
pip install semafs[openai]
# or
pip install openai
```

### Configuration

```python
from openai import AsyncOpenAI
from semafs.infra.llm.openai import OpenAIAdapter
from semafs.strategies.hybrid import HybridStrategy

# Option 1: Environment variable
# export OPENAI_API_KEY="sk-..."
client = AsyncOpenAI()

# Option 2: Explicit API key
client = AsyncOpenAI(api_key="sk-...")

# Create adapter
adapter = OpenAIAdapter(
    client=client,
    model="gpt-4o-mini",     # Cost-effective default
    temperature=0.7          # Creativity level
)

# Use with strategy
strategy = HybridStrategy(adapter, max_nodes=8)
semafs = SemaFS(factory, strategy)
```

### Model Selection

| Model | Speed | Cost | Quality |
|-------|-------|------|---------|
| `gpt-4o-mini` | Fast | Low | Good |
| `gpt-4o` | Medium | High | Excellent |
| `gpt-4-turbo` | Slow | High | Excellent |

## Anthropic Setup

### Installation

```bash
pip install semafs[anthropic]
# or
pip install anthropic
```

### Configuration

```python
from anthropic import AsyncAnthropic
from semafs.infra.llm.anthropic import AnthropicAdapter
from semafs.strategies.hybrid import HybridStrategy

# Environment variable: ANTHROPIC_API_KEY
client = AsyncAnthropic()

adapter = AnthropicAdapter(
    client=client,
    model="claude-3-haiku-20240307"
)

strategy = HybridStrategy(adapter, max_nodes=8)
```

### Model Selection

| Model | Speed | Cost | Quality |
|-------|-------|------|---------|
| `claude-3-haiku-*` | Fast | Low | Good |
| `claude-3-sonnet-*` | Medium | Medium | Great |
| `claude-3-opus-*` | Slow | High | Excellent |

## How LLM Is Used

### Context Sent to LLM

```yaml
System Prompt:
  - Role: Knowledge organization expert
  - Available operations: MERGE, GROUP, MOVE
  - Constraints: Lossless merging, existing paths only

User Prompt:
  - Current category path and content
  - Active children (stable nodes)
  - Pending fragments (new content)
  - Available move targets
  - Sibling categories (naming context)
  - Ancestor chain (hierarchy context)
```

### Tool Calling

LLM is forced to use the `tree_ops` function:

```json
{
  "name": "tree_ops",
  "parameters": {
    "ops": [
      {
        "op_type": "MERGE",
        "ids": ["abc123", "def456"],
        "content": "Merged content...",
        "reasoning": "Both about coffee preferences"
      }
    ],
    "updated_content": "New category summary",
    "should_dirty_parent": false,
    "overall_reasoning": "Strategy explanation"
  }
}
```

## Custom LLM Adapter

Implement the `BaseLLMAdapter` protocol:

```python
from semafs.ports.llm import BaseLLMAdapter
from semafs.core.ops import RebalancePlan, UpdateContext

class MyLLMAdapter(BaseLLMAdapter):
    async def call(
        self,
        context: UpdateContext,
        max_children: int
    ) -> RebalancePlan:
        # Build your prompt
        prompt = self._build_prompt(context, max_children)

        # Call your LLM
        response = await my_llm_call(prompt)

        # Parse response into RebalancePlan
        return self._parse_response(response)

    def _build_prompt(self, context, max_children) -> str:
        # Use base class helpers
        return self._format_system_prompt() + self._format_user_prompt(context)

    def _parse_response(self, response) -> RebalancePlan:
        # Parse JSON into operations
        ...
```

## Error Handling

### LLM Failures

The HybridStrategy automatically falls back to rules:

```python
try:
    plan = await adapter.call(context, max_children)
except LLMAdapterError as e:
    logger.warning(f"LLM failed: {e}, using fallback")
    plan = strategy.create_fallback_plan(context, max_children)
```

### Retry Logic

Add retries for transient failures:

```python
from tenacity import retry, stop_after_attempt, wait_exponential

class RetryingAdapter(OpenAIAdapter):
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def call(self, context, max_children):
        return await super().call(context, max_children)
```

### Rate Limiting

```python
import asyncio

class RateLimitedAdapter(OpenAIAdapter):
    def __init__(self, *args, calls_per_minute=60, **kwargs):
        super().__init__(*args, **kwargs)
        self.semaphore = asyncio.Semaphore(calls_per_minute)

    async def call(self, context, max_children):
        async with self.semaphore:
            result = await super().call(context, max_children)
            await asyncio.sleep(1)  # Rate limit
            return result
```

## Cost Optimization

### 1. Tune Thresholds

```python
# Higher threshold = fewer LLM calls
strategy = HybridStrategy(adapter, max_nodes=15)
```

### 2. Use Cheaper Models

```python
# gpt-4o-mini is 10-20x cheaper than gpt-4o
adapter = OpenAIAdapter(client, model="gpt-4o-mini")
```

### 3. Batch Writes

```python
# One LLM call instead of many
for note in notes:
    await semafs.write("root.work", note)
await semafs.maintain()  # Single call
```

### 4. Monitor Usage

```python
class MonitoredAdapter(OpenAIAdapter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.total_calls = 0
        self.total_tokens = 0

    async def call(self, context, max_children):
        self.total_calls += 1
        result = await super().call(context, max_children)
        # Track tokens if available
        return result
```

## Testing Without LLM

Use `RuleOnlyStrategy` for development:

```python
# No API key needed
from semafs.strategies.rule import RuleOnlyStrategy

strategy = RuleOnlyStrategy()
semafs = SemaFS(factory, strategy)

# Test your code without LLM costs
await semafs.write("root.test", "content")
await semafs.maintain()
```

## Mock Adapter for Tests

```python
from unittest.mock import AsyncMock
from semafs.core.ops import RebalancePlan, PersistOp

# Create mock adapter
mock_adapter = AsyncMock()
mock_adapter.call.return_value = RebalancePlan(
    ops=(PersistOp(id="test", reasoning="mock"),),
    updated_content="mock content",
    is_llm_plan=True
)

strategy = HybridStrategy(mock_adapter, max_nodes=8)
```

## Next Steps

- [Strategies](./strategies) - Strategy configuration
- [Maintenance](./maintenance) - When LLM is called
- [API Reference](/api/strategy) - Full adapter API
