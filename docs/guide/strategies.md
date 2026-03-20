# Strategies

SemaFS uses protocol-based strategy injection.

## 1. Protocol Interfaces

- `Strategy.draft(snapshot) -> RawPlan | None`
- `Placer.place(content, start_path) -> PlacementRoute`
- `Summarizer.summarize(snapshot) -> (summary, keywords?)`
- `Policy.seed/step` for propagation

## 2. Default Runtime Stack

- Rebalance strategy: `HybridStrategy`
- Placement strategy: `LLMRecursivePlacer`
- Summarization strategy: `LLMSummarizer`
- Propagation policy: `DefaultPolicy`

## 3. HybridStrategy Behavior

- healthy + no pending -> no plan
- healthy + pending -> usually no structural ops
- pressured/overflow -> call LLM and parse ops
- LLM failure -> skip rebalancing this round

## 4. Placement Strategy Variants

- `HintPlacer`: always stays at start path
- `LLMRecursivePlacer`: decides stay/descend per level

Main config knobs:

- `max_depth`
- `min_confidence`

## 5. Policy Decorators

Additional propagation decorators are available:

- `ZoneAwarePolicy`
- `DepthAwarePolicy`

They wrap a base policy and alter continuation behavior.

## 6. Custom Strategy Pattern

Any class implementing protocol signatures can be injected into `SemaFS(...)`.
