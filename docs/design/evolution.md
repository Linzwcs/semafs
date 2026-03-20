# Evolution Roadmap

本文描述 SemaFS 在“架构、能力、工程化”三个维度的演进方向。

## Roadmap Principles

- 优先修复契约漂移（docs/scripts/API）
- 优先降低复杂度（keeper/phases/边界）
- 在保证一致性的前提下扩展能力

## Near Term (v2.1.x)

### 1. 文档与主线 API 持续对齐

- 统一示例到 `write/sweep/tree/related/stats`
- 对历史接口提供迁移说明而不是继续扩散

### 2. 事务内读取收敛

- 写路径关键读取全部走 `uow.reader`
- 降低 stale snapshot 造成的错误决策

### 3. 边界治理

- 继续清理 `infra -> engine` 反向依赖
- 保持 `core/ports` 作为共享语义中心

## Mid Term (v2.2)

### 1. 记忆质量治理

- 引入 memory score / decay / retention policy
- 支持“长期保留 vs 冷却归档”的策略化配置

### 2. 可观测性增强

- 将 `ReconcileMetrics` 指标化（Prometheus/OpenTelemetry）
- 增加守卫拒绝码分布、阶段耗时、重试率看板

### 3. Benchmark 套件

- 延迟：write/read/sweep
- 质量：结构稳定性、摘要一致性
- 成本：LLM token 消耗
- 一致性：并发下可重复性

## Long Term (v3)

### 1. 编排框架互操作

- 提供 LangGraph/LlamaIndex 的官方集成层
- 明确“Memory Governance Layer”定位

### 2. 时间语义扩展

- 在树结构基础上引入时间窗口视图/事件索引
- 支持“事实随时间演化”的追踪与回放

### 3. 多存储后端

- 在不破坏 ports 契约下扩展 Postgres 等后端
- 保持语义行为一致，降低迁移成本

## Engineering Guardrails

每次版本迭代应满足：

1. 文档示例可运行
2. regression + smoke 通过
3. 新增复杂度低于预算（模块/函数）
4. 对外 API 变更给出迁移路径

## Change Discipline

- 小步提交，分阶段回滚
- 先做“结构重构无行为变化”，再引入能力扩展
- 设计文档先行，代码与文档同版本交付
