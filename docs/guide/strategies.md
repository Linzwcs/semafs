# Strategies

Configure how SemaFS drafts rebalance plans.

## Current Strategy Interface

```python
class Strategy(Protocol):
    async def draft(self, snapshot: Snapshot) -> RawPlan | None: ...
```

- Return `None` when no structural changes are needed.
- Return `RawPlan` when you want rebalance ops (`MERGE/GROUP/MOVE/RENAME`).

## Built-in Strategy

SemaFS currently ships with:

- `HybridStrategy(adapter, force_threshold=None)`

```python
from semafs.algo import HybridStrategy

strategy = HybridStrategy(adapter)
```

## HybridStrategy Behavior

High-level logic:

- healthy + no pending => skip
- healthy + pending => skip structural rebalance (lifecycle/summary still run)
- pressured/overflow => call LLM adapter and parse plan
- LLM failure => skip rebalance this round (safe no-op)

## Custom Strategy Example

```python
from semafs.core.raw import RawPlan, RawRename


class NoopStrategy:
    async def draft(self, snapshot):
        return None


class RenameOnlyStrategy:
    async def draft(self, snapshot):
        if not snapshot.subcategories:
            return None
        first = snapshot.subcategories[0]
        return RawPlan(
            ops=(
                RawRename(node_id=first.id, new_name="renamed_category"),
            ),
            reasoning="rename first subcategory",
        )
```

## Choosing a Strategy

- local/offline deterministic flow: custom no-op or rule strategy
- production semantic organization: `HybridStrategy` + LLM adapter
- strict governance: custom strategy + stronger guard constraints

## Current vs Old Docs

Use now:

- `Strategy.draft(snapshot)`
- `HybridStrategy`

Old names to avoid:

- `create_plan(...)`
- `RuleOnlyStrategy`

## Next Steps

- [LLM Integration](./llm-integration) - Adapter setup
- [Maintenance](./maintenance) - Reconcile and sweep behavior
- [Operations](./operations) - Plan operation semantics
