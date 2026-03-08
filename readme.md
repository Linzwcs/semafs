# 📊 SemaFS 全景图谱与数据流向

## 1. 系统总体架构图 (System Architecture)

展示 SemaFS 的分层架构（Clean Architecture），突出“流程控制”、“大模型策略”与“底层存储”的解耦。

```mermaid
graph TD
   
    subgraph External["上游应用层 (Frontend / Agents)"]
        Agent[对话 Agent / 微信 Bot]
        UI[可视化前端 / PKM 工具]
    end


    subgraph Core["SemaFS 应用协调层 (Application)"]
        FS["SemaFS Core write() / read() / maintain()"]
    end

    subgraph Domain["领域与策略层 (Domain & Strategy)"]
        Strategy["NodeUpdateStrategy (LLM 推理大脑)"]
        Op["NodeUpdateOp MERGE / SPLIT / MOVE"]
        Ctx["NodeUpdateContext 局部目录快照"]
    end

    %% 基础设施层 (数据库与锁)
    subgraph Infra["基础设施层 (Infrastructure)"]
        Repo["TreeRepository (PostgreSQL / Ltree)"]
        Lock["Distributed Lock 防并发重入"]
        DB["(统一节点表 nodes)"]
    end

    %% 关联关系
    Agent -- 写入/读取 --> FS
    UI -- 写入/读取 --> FS
   

    FS -- 1. 抓取快照 --> Repo
    Repo -- 2. 返回 Context --> Ctx
    FS -- 3. 喂给大脑 --> Strategy
    Ctx -. 组装 Prompt .-> Strategy
    Strategy -- 4. 产出意图 --> Op
    FS -- 5. 提交执行 --> Repo
    Op -. 翻译为 SQL .-> Repo
    
    Repo <--> DB
    Repo <--> Lock

    classDef core fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef domain fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    classDef infra fill:#f3e5f5,stroke:#4a148c,stroke-width:2px;
    class FS core;
    class Strategy,Op,Ctx domain;
    class Repo,DB,Lock infra;
```

---

## 2. 核心数据流一：双层智能路由与无锁写入 (Write & Active Routing Flow)

展示上游 Agent 如何利用“顶层地图”进行精准投递，以及 SemaFS 如何实现极速写入。

```mermaid
sequenceDiagram
    participant User as 用户 (Human)
    participant Agent as 前端 Agent (LLM)
    participant SemaFS as SemaFS 接口
    participant Repo as 底层 Repo (DB)

    User->>Agent: "下周三和老王核对 A 项目进度"
    
    Note over Agent,SemaFS: 1. 前置感知 (Top-2 Map)
    Agent->>SemaFS: 获取知识库全局骨架 (get_skeleton)
    SemaFS-->>Agent: 返回前两层目录 (如 root.work.project_a)
    
    Note over Agent: Agent 思考: "命中 project_a 目录"
    
    Note over Agent,SemaFS: 2. 极速精准写入 (O(1))
    Agent->>SemaFS: write(path="root.work.project_a", content="...")
    
    SemaFS->>Repo: add_node(VirtualTreeNode)
    Note over Repo: DB 事务:  1. 插入 PENDING_REVIEW 碎片 2. UPDATE parent.is_dirty = True
    Repo-->>SemaFS: 返回 frag_ID
    SemaFS-->>Agent: 写入成功
    Agent-->>User: "已为您记录在 A 项目中！"
```

---

## 3. 核心数据流二：无阻塞合路读取 (Read-Your-Writes Flow)

展示在后台正在整理时，前端依然能够瞬间读取到所有数据（融合了稳定知识与处理中的碎片）。

```mermaid
sequenceDiagram
    participant UI as 前端页面 / Agent
    participant SemaFS as SemaFS 接口
    participant Repo as 底层 Repo (DB)

    UI->>SemaFS: read(path="root.work.project_a")
    SemaFS->>Repo: list_children()
    
    Note over Repo: 执行无锁查询 (No Lock) SELECT * WHERE path ~ '...*'
    
    Repo-->>SemaFS: 返回 List[TreeNode]
    
    Note over SemaFS,UI: 包含三种状态的合路视图
    SemaFS-->>UI: [ACTIVE(旧笔记), PENDING(刚写的), PROCESSING(AI正在整理的)]
    
    Note over UI: 前端渲染: ✅ 旧笔记正常显示 🆕 刚写的带有 "New" 标签 ✨ PROCESSING 带有 "AI整理中..." 动画
```

---

## 4. 核心数据流三：后台记忆重组与自组织 (Maintain & Consolidation Flow)

这是 SemaFS **最核心的壁垒**，展示了系统如何在后台异步利用 LLM 将混沌的数据重新组织化。

```mermaid
sequenceDiagram
    participant Cron as 定时器
    participant SemaFS as SemaFS 协调者
    participant Repo as TreeRepository
    participant LLM as LLM 策略大脑

    Cron->>SemaFS: 触发 maintain()
    SemaFS->>Repo: list_dirty_categories()
    Repo-->>SemaFS: 返回 ['root.work.project_a']

    Note over SemaFS,Repo: 1. 获取锁与防穿透快照
    SemaFS->>Repo: lock_and_get_context()
    Note over Repo: DB: UPDATE status = 'PROCESSING' (将碎片锁定，前端UI变为"整理中")
    Repo-->>SemaFS: 返回 NodeUpdateContext (包含旧节点+碎片)

    Note over SemaFS,LLM: 2. 大脑异步思考 (耗时 10s-30s)
    SemaFS->>LLM: create_update_op(Context)
    Note over LLM: 分析语义冲突 决定执行 MERGE 或 SPLIT
    LLM-->>SemaFS: 返回 NodeUpdateOp (如: MERGE意图)

    Note over SemaFS,Repo: 3. 引擎执行物理变更 (原子操作)
    SemaFS->>Repo: execute(op)
    Note over Repo: DB 事务: 1. 归档/删除 PROCESSING 碎片 2. UPSERT 合并后的新 ACTIVE 节点 3. 清除父目录 is_dirty
    Repo-->>SemaFS: 提交完成，自动释放 Lock
```

---

## 5. 碎片生命周期状态机 (Status State Machine)

展示一条记忆碎片是如何在数据库中流转的，这是并发安全的基石。

```mermaid
stateDiagram-v2
    [*] --> PENDING_REVIEW : 用户 Add 写入碎片
    
    state "PENDING_REVIEW (待审阅)" as PENDING
    state "PROCESSING (AI 整理中)" as PROCESSING
    state "ACTIVE (稳定知识)" as ACTIVE
    state "ARCHIVED (已归档/融合)" as ARCHIVED

    PENDING --> PROCESSING : Maintainer 获取锁并截取快照
    
    PROCESSING --> ARCHIVED : 被 LLM 合并 (MERGE) 或 移动 (MOVE)
    PROCESSING --> ACTIVE : 碎片足够完整，LLM 决定直接转正
    
    PROCESSING --> PENDING : ⚠️ LLM 请求超时 / 报错 (自动回退)
    
    ACTIVE --> ARCHIVED : 后期被其他碎片合并时淘汰
    ACTIVE --> [*]
    ARCHIVED --> [*]
```

---

## 🚀 运行示例

```bash
cd experimental/SemaFS

# Mock 模式（无需 API Key，使用 MockLLMAdapter 模拟 LLM）
python -m semafs.run

# OpenAI 模式（需设置 OPENAI_API_KEY）
export OPENAI_API_KEY=sk-...
python -m semafs.run --openai --model gpt-4o-mini
```

运行流程：创建分类 → 写入 23 条记忆碎片 → 读取合路视图 → `maintain()` 整理（LLM 决策）→ 再次读取整理结果。

测试数据位于 `semafs/run.py` 与 `tests/fixtures.py`，包含工作、个人、学习、想法等多类记忆碎片。

### SQLite 测试与 Markdown 导出

```bash
# 运行 SQLite 测试（含 Markdown 导出）
pip install aiosqlite
python -m pytest tests/test_semafs_sqlite.py -v

# 测试完成后，数据库与 Markdown 位于：
#   tests/output/semafs_test.db   # SQLite 数据库
#   tests/output/vault/*.md        # Markdown 视图（每个分类一个 .md）
```

---

## 💡 汇报时的演讲要点 (Talk Track)

如果你使用这些图进行汇报，可以重点引导听众关注以下几个 **“Aha Moment（顿悟时刻）”**：

1. **图 1 (架构图)**：请注意 `NodeUpdateOp` 和 `Context` 的设计。我们让大模型完全不知道数据库长什么样，它只做纯粹的“语义 Diff（补丁）”计算，这让系统极度安全且易于测试。
2. **图 2 (双层路由)**：为了防止系统“雪崩”，我们把大模型的算力做了拆分。前端的便宜模型（如 GPT-4o-mini）只看最顶层地图做“快递分拣（Add）”，后端的昂贵模型在夜间做“深度提纯（Maintain）”。
3. **图 3 (合路读取)**：这是我们解决“RAG 写入延迟”的必杀技。用户写完瞬间可读，甚至能看到 AI 正在整理的炫酷状态（`PROCESSING`），全程无数据库行锁，体验丝滑。
4. **图 5 (状态机)**：这四个状态构成了 SemaFS 的坚固护城河。即使在 LLM 思考的 30 秒内用户又疯狂发了 10 条新消息，因为状态机的严格管控，我们也**绝对不会丢失任何一条数据，也不会发生覆盖冲突**。