# Design Philosophy

SemaFS 的设计目标不是“再做一个向量检索层”，而是构建一个可演进、可治理、可审计的语义记忆系统。

## 核心理念

### 1. 语义记忆要有结构，而不是纯相似度

- 记忆以树组织（`root.*`），支持从抽象到细节的层级导航。
- 父节点是子节点的语义摘要，而不是简单拼接。
- 读侧返回结构化视图（`NodeView/TreeView/RelatedNodes`），便于 Agent 做路径决策。

### 2. 写入优先可靠，维护异步治理

- 写入接口 `write(content, hint, payload)` 追求低延迟、强一致。
- 结构优化由 reconcile/sweep 完成，避免把慢操作塞进写路径。
- 通过事件总线（`Placed/Persisted/Moved`）驱动局部维护，减少全局重算。

### 3. LLM 是增强器，不是单点真相

- LLM 负责提出重组建议（RawPlan），不是直接改库。
- 计划必须经过 `Resolver + PlanGuard + Executor` 才会落地。
- LLM 失败时系统仍可运行（跳过本轮或规则回退），保证可用性。

### 4. 身份与路径解耦

- 节点主身份是 `id`，`canonical_path` 是可变投影。
- `node_paths` 维护路径索引投影，支持 rename/move 后的一致读取。
- 这样可以在结构重排时避免“路径即身份”的连锁风险。

### 5. 事务边界优先于“看起来简单”

- 所有写操作通过 Unit of Work staging 后一次提交。
- 写流程关键读取优先使用事务内 reader（`uow.reader`）。
- 目标是减少 stale snapshot 决策与并发下的语义漂移。

### 6. 默认可解释（Explainable by default）

- 每次重组都可追溯到：输入快照、策略决策、守卫拒绝原因、落地事件。
- 关键指标统一在 `ReconcileMetrics` 暴露，便于运维与回归。

## 设计取舍

| 取舍点 | 选择 | 原因 |
|---|---|---|
| 延迟 vs 质量 | 写快 + 后台治理 | 在线体验稳定，重组可批处理 |
| 结构化 vs 自由文本 | 树结构优先 | 便于导航、压缩和治理 |
| 完全自动 vs 可控 | Guard + 显式策略 | 生产系统需要可审计与可回滚 |
| Path-first vs ID-first | ID-first | 降低 rename/move 的一致性风险 |

## 对外定位

SemaFS 适合作为 Agent 系统的“记忆治理层（Memory Governance Layer）”：

- 向上对接编排框架（如 LangGraph）
- 向下对接存储和模型能力
- 中间提供可解释、可演进的语义结构与维护机制
