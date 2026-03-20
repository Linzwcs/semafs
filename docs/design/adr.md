# ADR (Architecture Decision Records)

本页记录 SemaFS 的关键架构决策，便于后续演进保持一致性。

## ADR-001: ID-first Identity, Path as Projection

- Status: Accepted
- Date: 2026-03-20

### Context

路径会因 rename/move 变化，如果把路径当主身份，会导致级联更新风险高、历史追踪困难。

### Decision

- 节点主身份使用 `id`
- `canonical_path` 作为可变投影
- 维护 `node_paths` 做路径索引映射

### Consequences

- rename/move 更安全
- 内部引用稳定
- 存储层需要额外投影刷新逻辑

## ADR-002: Unit of Work + TxReader as Consistency Boundary

- Status: Accepted
- Date: 2026-03-20

### Context

维护流程涉及多步读写，若读写不在同事务视角，容易出现 stale snapshot 决策。

### Decision

- 所有写变更先 staging，再一次 `commit()`
- 关键读取优先通过 `uow.reader`
- 异常触发 rollback，禁止部分提交

### Consequences

- 一致性提升
- 实现复杂度上升（UoW/Reader 契约）

## ADR-003: Phase-based Reconcile Pipeline

- Status: Accepted
- Date: 2026-03-20

### Context

单体维护编排器复杂度过高，难以测试和演进。

### Decision

将维护拆分为：

- `RebalancePhase`
- `RollupPhase`
- `Lifecycle/Summary/Propagation` phases

由 `Keeper` 负责薄编排和锁。

### Consequences

- 复杂度下降，职责更清晰
- 阶段间数据契约需要严格维护

## ADR-004: LLM as Advisor, Guarded Execution as Gatekeeper

- Status: Accepted
- Date: 2026-03-20

### Context

LLM 输出可能不稳定，直接执行会带来数据风险。

### Decision

- LLM 只产出 RawPlan
- 必须经 `PlanGuard -> Resolver -> Executor -> UoW` 链路
- 不合规计划拒绝并记录原因码

### Consequences

- 可靠性与可解释性提升
- 需要维护 guard 规则与拒绝码体系

## ADR Template

后续新增决策可按如下模板追加：

```md
## ADR-XXX: <Title>

- Status: Proposed | Accepted | Deprecated | Superseded
- Date: YYYY-MM-DD

### Context
<为什么要做这个决策>

### Decision
<做了什么选择>

### Alternatives Considered
- A
- B

### Consequences
- Positive
- Negative
```
