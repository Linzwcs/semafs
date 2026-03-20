# Maintenance Pipeline

`Keeper.reconcile(...)` is the central maintenance operation.

## 1. Inputs

- `node_id`: target category
- `signal`: propagation signal
- `cause`: optional triggering event

## 2. Phase Breakdown

### 2.1 Rebalance Phase

- evaluate zone and terminal policy
- draft raw plan via strategy
- guard validation/sanitization
- resolve to executable plan
- execute operations into UoW staging

### 2.2 Rollup Phase

For terminal categories that exceed thresholds:

- pick oldest active leaves
- summarize into rollup leaf
- mark source leaves as `COLD`

### 2.3 Post-Rebalance Phases

- lifecycle promotion (`PENDING -> ACTIVE`)
- summary/meta refresh
- optional upward propagation

## 3. Transaction Boundary

Most phase actions execute inside one UoW transaction.

- commit happens after phase work is staged
- publish of resulting events occurs after lock release

## 4. Concurrency Control

Keeper maintains per-node async locks.

- same node: serialized reconcile
- different nodes: can reconcile independently

## 5. Sweep Mode

`sweep(limit)` finds overloaded categories and runs reconcile per match.

Use this for backlog recovery and scheduled maintenance windows.
