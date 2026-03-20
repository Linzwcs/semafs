# LLM Integration

SemaFS uses LLMs for three independent responsibilities:

- Rebalance planning: `call(snapshot)`
- Placement routing: `call_placement(...)`
- Category summarization: `call_summary(snapshot)`

## 1. Supported Providers

- OpenAI via `OpenAIAdapter`
- Anthropic via `AnthropicAdapter`

CLI and MCP runtime parameters:

- `--provider openai|anthropic`
- `--model ...`
- `--api-key ...` (or env var)
- `--base-url ...` (OpenAI-compatible gateway)

## 2. Default Models

- OpenAI default: `gpt-4o-mini`
- Anthropic default: `claude-haiku-4-5-20251001`

Override with `--model`.

## 3. Prompt and Tool Schema

Prompt builders are defined in `semafs/infra/llm/prompt.py`.

Design highlights:

- strict tool/function-calling schema
- explicit naming and summary contracts
- keyword constraints and placeholder-category rejection

## 4. Failure Behavior

- Rebalance call failure: `HybridStrategy` skips structural changes this round.
- Summary call failure: summarizer falls back to existing summary.
- Placement call failure: exception bubbles up to caller runtime.

## 5. Production Guidance

- tune `placement_max_depth` and `placement_min_confidence`
- tune `Budget(soft, hard)` for workload size
- keep `_placement` payload for route diagnostics
- treat provider/model changes as behavior-impacting config changes
