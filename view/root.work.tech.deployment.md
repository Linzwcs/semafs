---

### deployment

<!-- 类型: CATEGORY | 路径: root.work.tech.deployment | 状态: ACTIVE | ID: 1b7bffde-ab0d-4ee0-adfe-ed27d52aa556 | 版本: v1 | 创建: 2026-03-10 07:18 | 更新: 2026-03-10 07:18 | 名称: deployment -->

<sub>类型: CATEGORY | 路径: root.work.tech.deployment | 状态: ACTIVE | ID: 1b7bffde-ab0d-4ee0-adfe-ed27d52aa556 | 版本: v1 | 创建: 2026-03-10 07:18 | 更新: 2026-03-10 07:18 | 名称: deployment</sub>

**摘要:**

Deployment strategies include refusing downtime deployments, employing blue-green or canary releases based on K8s, and ensuring the ability to roll back to a stable version within 3 minutes upon detection of issues. A graceful shutdown is emphasized as rejecting new requests and freeing resources after completing ongoing tasks within a 30-second window upon receiving a SIGTERM signal.

---

## 内容 (LEAF)


---

### 节点 1 · leaf_bb49a2

<!-- 类型: LEAF | 路径: root.work.tech.deployment.leaf_bb49a2 | 状态: ACTIVE | ID: a80e5cab-652c-45dc-a28f-04a9d4c4ebaf | 版本: v1 | 创建: 2026-03-10 07:18 | 更新: 2026-03-10 07:18 | 名称: leaf_bb49a2 -->

生产环境部署策略：拒绝停机发布，全面采用蓝绿部署或基于 K8s 的金丝雀灰度发布。一旦监控探针发现异常，必须保证能在 3 分钟内一键回滚到上一个稳定版本。

<sub>类型: LEAF | 路径: root.work.tech.deployment.leaf_bb49a2 | 状态: ACTIVE | ID: a80e5cab-652c-45dc-a28f-04a9d4c4ebaf | 版本: v1 | 创建: 2026-03-10 07:18 | 更新: 2026-03-10 07:18 | 名称: leaf_bb49a2</sub>


---

### 节点 2 · leaf_e9d7ed

<!-- 类型: LEAF | 路径: root.work.tech.deployment.leaf_e9d7ed | 状态: ACTIVE | ID: 4631f55e-5f23-4e13-982f-846972cac801 | 版本: v1 | 创建: 2026-03-10 07:18 | 更新: 2026-03-10 07:18 | 名称: leaf_e9d7ed -->

服务的优雅下线（Graceful Shutdown）：在接收到 SIGTERM 信号后，必须先拒绝新的请求，并等待最多 30 秒处理完当前正在执行的线程任务后，再释放资源退出进程。

<sub>类型: LEAF | 路径: root.work.tech.deployment.leaf_e9d7ed | 状态: ACTIVE | ID: 4631f55e-5f23-4e13-982f-846972cac801 | 版本: v1 | 创建: 2026-03-10 07:18 | 更新: 2026-03-10 07:18 | 名称: leaf_e9d7ed</sub>

---

<sub>导出于 2026-03-10 07:19 UTC</sub>
