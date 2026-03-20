# Value and Limits

This page summarizes practical engineering value and known limits of the current implementation.

## 1. Value

### 1.1 Explainable Memory Shape

- canonical paths are explicit and user-inspectable
- `tree/related/stats` make topology observable

### 1.2 Controlled Automatic Maintenance

- event-driven reconcile after write
- explicit `sweep(limit)` for backlog control

### 1.3 Transactional Structural Integrity

- atomic mutation batches through UoW
- path cascade updates included in commit boundary

### 1.4 Replaceable Components

- storage, strategy, placement, summarization, and propagation are interface-driven

## 2. Limits

### 2.1 Runtime Provider Requirement

Operational CLI commands (except viewer) require provider config.

### 2.2 Single-Node Default Storage

SQLite default is ideal for local/single-service deployments, not high-contention distributed writes.

### 2.3 Model-Dependent Structural Quality

Grouping/renaming/summarization quality depends on prompt + model behavior.

## 3. Good Fit vs Poor Fit

Good fit:

- long-term agent memory
- explainable semantic organization
- systems that need deterministic mutation boundaries

Poor fit:

- ultra-high-throughput low-latency distributed writes
- environments that cannot call external LLMs but still need equivalent auto-organization quality
