---

### security

<!-- 类型: CATEGORY | 路径: root.work.tech.security | 状态: ACTIVE | ID: dd79af16-3aae-4d98-9d4e-29582afa88ad | 版本: v3 | 创建: 2026-03-10 07:37 | 更新: 2026-03-10 07:39 | 名称: security -->

<sub>类型: CATEGORY | 路径: root.work.tech.security | 状态: ACTIVE | ID: dd79af16-3aae-4d98-9d4e-29582afa88ad | 版本: v3 | 创建: 2026-03-10 07:37 | 更新: 2026-03-10 07:39 | 名称: security</sub>

**摘要:**

Best practices for security and monitoring, including two-factor authentication, alert rules, and unit testing.

---

## 内容 (LEAF)


---

### 节点 1 · leaf_19e21f

<!-- 类型: LEAF | 路径: root.work.tech.security.leaf_19e21f | 状态: ACTIVE | ID: e49ff00d-3baa-45de-b1d7-d02420ecba03 | 版本: v1 | 创建: 2026-03-10 07:37 | 更新: 2026-03-10 07:37 | 名称: leaf_19e21f -->

第三方库依赖升级策略：设定每月最后一个周三为“依赖体检日”，评估并小步升级非破坏性更新包，避免长年不升导致最终跨大版本升级时发生灾难。

<sub>类型: LEAF | 路径: root.work.tech.security.leaf_19e21f | 状态: ACTIVE | ID: e49ff00d-3baa-45de-b1d7-d02420ecba03 | 版本: v1 | 创建: 2026-03-10 07:37 | 更新: 2026-03-10 07:37 | 名称: leaf_19e21f</sub>


---

### 节点 2 · leaf_e99dcb

<!-- 类型: LEAF | 路径: root.work.tech.security.leaf_e99dcb | 状态: ACTIVE | ID: 8a6cb276-e834-402a-b350-f8211644babd | 版本: v1 | 创建: 2026-03-10 07:37 | 更新: 2026-03-10 07:37 | 名称: leaf_e99dcb -->

监控告警规则设定：阈值必须根据业务实际承诺的 SLA 来动态调整，并设置告警收敛（如 5 分钟内同类报错只发一条），极度反感“狼来了”式的无效报警。

<sub>类型: LEAF | 路径: root.work.tech.security.leaf_e99dcb | 状态: ACTIVE | ID: 8a6cb276-e834-402a-b350-f8211644babd | 版本: v1 | 创建: 2026-03-10 07:37 | 更新: 2026-03-10 07:37 | 名称: leaf_e99dcb</sub>


---

### 节点 3 · leaf_d90cce

<!-- 类型: LEAF | 路径: root.work.tech.security.leaf_d90cce | 状态: ACTIVE | ID: 65a2ebba-0447-48f4-aaa7-dee6744d4d28 | 版本: v1 | 创建: 2026-03-10 07:37 | 更新: 2026-03-10 07:37 | 名称: leaf_d90cce -->

身份验证强化：对于 Github、AWS 控制台、云服务器堡垒机等包含敏感资产的核心系统，强制开启 2FA（双因素认证），宁可每次多看一眼验证码也绝不妥协。

<sub>类型: LEAF | 路径: root.work.tech.security.leaf_d90cce | 状态: ACTIVE | ID: 65a2ebba-0447-48f4-aaa7-dee6744d4d28 | 版本: v1 | 创建: 2026-03-10 07:37 | 更新: 2026-03-10 07:37 | 名称: leaf_d90cce</sub>

---

<sub>导出于 2026-03-10 07:42 UTC</sub>
