# Maintenance

`Keeper` orchestrates maintenance to keep category structure healthy and summaries up to date.

## 1. Trigger Paths

### 1.1 Event-Driven Path

After write commit:

```text
Placed -> Pulse.seed -> Keeper.reconcile(...)
```

Pulse subscriptions include `Placed`, `Persisted`, and `Moved`.

### 1.2 Manual Sweep Path

```python
changed = await fs.sweep(limit=20)
```

`sweep` scans overloaded categories and reconciles each.

## 2. Reconcile Phase Pipeline

Implemented in `engine/keeper.py` and `engine/phases.py`:

1. Build immutable snapshot (`SnapshotBuilder`)
2. Rebalance phase (strategy -> guard -> resolver -> executor)
3. Rollup phase (terminal categories only)
4. Lifecycle phase (`PENDING -> ACTIVE`)
5. Summary phase (refresh category summary/meta)
6. Commit transaction
7. Propagation phase (optional parent reconcile)

## 3. Locking Model

Keeper uses per-node `asyncio.Lock`:

- single category reconciles are serialized
- unrelated categories can proceed concurrently
- events are published after lock release to reduce deadlock risk

## 4. Rebalance Conditions

Driven by `Budget(soft, hard)` zone:

- `HEALTHY` with no pending: generally skip rebalancing
- `PRESSURED` or `OVERFLOW`: call strategy (`HybridStrategy` by default)

## 5. Terminal Rollup Conditions

Rollup requires:

- depth at or beyond `terminal_depth`
- active leaves above `rollup_trigger_count`
- batch size at least `min_rollup_batch`

On success, old batch leaves become `COLD` and a `rollup_*` leaf is created.

## 6. Propagation Policy

Default behavior (`DefaultPolicy`):

- seed by event weight
- linear decay per hop
- stop below threshold
- stop at root

## 7. Observability

`ReconcileMetrics` tracks:

- attempted/completed rebalance
- promoted count
- rollup flag
- summary change flag
- propagation flag
- guard reject counts
