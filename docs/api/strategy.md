# Strategies and Adapters API

Based on protocols in `semafs/ports/*` and implementations in `semafs/algo/*` and `semafs/infra/llm/*`.

## 1. `Strategy`

```python
async def draft(snapshot: Snapshot) -> RawPlan | None
```

Default implementation: `HybridStrategy`.

## 2. `Placer`

```python
async def place(content: str, start_path: str = "root") -> PlacementRoute
```

Default implementations:

- `LLMRecursivePlacer`
- `HintPlacer`

## 3. `Summarizer`

```python
async def summarize(snapshot: Snapshot) -> tuple[str, tuple[str, ...] | None]
```

Default implementations:

- `LLMSummarizer`
- `RuleSummarizer`

## 4. `Policy` (Propagation)

```python
def seed(event: TreeEvent, target_path: str) -> Signal
def step(ctx: Context) -> Step
```

Default implementation: `DefaultPolicy`.

Decorator variants:

- `ZoneAwarePolicy`
- `DepthAwarePolicy`

## 5. `LLMAdapter`

```python
async def call(snapshot) -> dict
async def call_summary(snapshot) -> dict
async def call_placement(...) -> dict
```

Default implementations:

- `OpenAIAdapter`
- `AnthropicAdapter`
