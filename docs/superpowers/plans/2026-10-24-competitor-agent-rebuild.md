# 电商竞品监控 Agent 改造计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把“事件看板 + 单次 LLM 调用”改造成“可审计、人在环上的竞品定价 Agent”。

**Architecture:** 采集层（RPA）→ 数据层（PostgreSQL + 向量）→ Agent 层（LangGraph：Plan/Act/Verify/Propose/Human/Learn）→ 交付层（React + SSE + RBAC）。

**Tech Stack:** Python/FastAPI、PostgreSQL、LangGraph、MCP tool servers、pgvector/Milvus、React+TS、SSE、Ollama（开发）/vLLM（生产）。

**Spec:** 本次会话中的架构评审与目标方案（2026-10-24）。

## Global Constraints

- 只收原始观测，到手价由服务端计算；缺失字段显式记录，绝不填 0。
- 数字必须来自工具或确定性代码；模型只做解释与方案措辞。
- 所有建议必须带证据 ID；证据闭包不通过则整条作废。
- 人工审批是唯一执行入口；Agent 不自主改价。
- 单机内网优先，默认不引入外部 SaaS。
- 每个阶段结束必须能独立运行、测试全绿。

## Review Focus

- 鉴权开启后，RPA 采集仍能通过服务令牌写入（不能因为加登录把采集打断）。
- 未登录用户不能读到竞品数据、账号列表或触发任务。
- 采集新鲜度可见：超过 SLA 必须能被看到，而不是静默无事件。
- 角色切换后 UI 不展示无权操作的按钮（不能只靠后端 403）。
- 数据库迁移期间旧数据可完整搬迁，事件与证据链不能断。

---

## 阶段路线

### P1 信任底座（进行中）

**已完成（2026-10-24）：** P1-A 鉴权收口与独立登录、P1-B 采集治理与新鲜度、P1-C SSE、P1-D PostgreSQL 迁移、P1-E React 工作台（`/next` 灰度，旧前端保留）。
**下一阶段：** P2 Agent 核心（LangGraph + MCP 工具 + Trace）。

目标：让系统“可信、可登录、可运维”，不改 Agent 逻辑。

- **P1-A 鉴权收口 + 独立登录（本次）**
- **P1-B 采集治理与数据新鲜度（本次）**
- **P1-C SSE 事件通道**
- **P1-D PostgreSQL 迁移（含数据搬迁与双跑测试）**
- **P1-E React 骨架与路由（独立目录，灰度切流）**

### P2 Agent 核心（已完成 2026-10-25）

LangGraph 状态机、6 个 MCP 工具、确定性计划 + 可选模型选工具、证据校验、
Agent Trace（运行/步骤）、新版轨迹页与建议详情轨迹摘要。

### P3 知识与多 Agent（已完成 2026-10-25）

文档 RAG（500/80 切片 + 向量/关键词/RRF + doc 引用）、Skill 注册表（触发/剧本/工具白名单）、
LLM Critic（默认关闭，驳回回退模板）、评测金标集（5 条，自清理）。

### P4 执行与评测闭环（已完成 2026-10-25）

执行适配器（off/preview/webhook + 幂等 + 回滚）、7 日结果回收（到期/逾期 + 观察价 + 去重提醒）、
token/成本与预算、上线门禁（评测通过率 + 告警 + 可选强制）。

---

## P1-A 任务

### Task 1: 修复用户接口提权

**Files:** `app/api.py`, `tests/test_auth.py`

- [ ] 写失败测试：member 调 `POST /api/users` 返回 403；admin 返回 200。
- [ ] 运行确认失败。
- [ ] 给 `list_users` / `create_user` 加 `Depends(auth.require_role("admin"))`，校验 role 枚举。
- [ ] 运行确认通过。

### Task 2: 保护读取与运维接口

**Files:** `app/api.py`, `app/auth.py`, `tests/test_auth.py`

- [ ] 写失败测试：鉴权开启后，未登录 `GET /api/events` 返回 401。
- [ ] 给数据读取接口加 `Depends(auth.current_user)`；`/api/ops*`、`/api/metrics`、`/api/experiments/*` 加 admin/manager。
- [ ] 采集入口支持 `Authorization: Bearer $LIRA_INGEST_TOKEN`，避免打断 RPA。
- [ ] 运行确认通过。

### Task 3: 独立登录页

**Files:** `app/main.py`, `web/login.html`, `web/index.html`, `web/app.js`

- [ ] 写失败测试：未登录 `GET /` 303 到 `/login`；`GET /login` 200。
- [ ] `main.py` 增加 `/login` 与服务端守卫。
- [ ] 新建 `web/login.html`，登录成功 `location.replace('/')`。
- [ ] 移除 index.html 的遮罩登录框。
- [ ] 运行确认通过。

### Task 4: 角色化 UI 与退出

**Files:** `web/index.html`, `web/app.js`, `app/api.py`

- [ ] `/api/me` 返回 role；本地模式返回 admin。
- [ ] 侧栏增加用户信息与退出按钮。
- [ ] member 不显示审批按钮、不显示系统菜单。
- [ ] 浏览器实测：admin 可审批，member 只读。

### Task 5: 登录风控

**Files:** `app/auth.py`, `app/api.py`, `tests/test_auth.py`

- [ ] 写失败测试：同 IP 连续 6 次失败登录返回 429。
- [ ] 进程内滑动窗口限流；Cookie 支持 `secure` 开关。
- [ ] 畸形 exp 的 token 返回 None 而不是 500。

---

## P1-B 任务（采集治理）

- 持久化 `screenshot_ref`；补 `collection_health()`。
- `/api/ops` 返回失败文件与每个采集源的最后成功时间、滞后小时数。
- 系统页展示采集健康度；事件页展示“数据截至 X 小时前”。
- 超过 SLA 在总览显示告警。

## P1-C 任务（SSE）

- `/api/stream` 推送 event_created / suggestion_updated / approval_updated。
- 前端 EventSource 更新角标与事件列表；断线重连与心跳。

## P1-D 任务（PostgreSQL）

- 新增 `psycopg`、schema.sql、连接层；保留 SQLite 作为测试后端。
- 数据搬迁脚本 + 行数校验 + 回归测试。

## P1-E 任务（React）

- `web-next/`：Vite + React + TS + Router。
- 登录、总览、事件、竞品 360、建议详情、审批详情、采集健康、Agent Trace。
