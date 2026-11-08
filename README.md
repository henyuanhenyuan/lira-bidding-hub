# Lira 电商 — 竞品情报 Agent

单机可运行的竞品定价情报系统：**采集 → 到手价 → 事件 → 多 Agent 研判 → 人工审批 → 结果回收**，
每一步都有证据与轨迹，模型只负责解释，动作由确定性策略给出。

## 快速开始

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

打开 http://127.0.0.1:8011/next 。默认本地模式无需登录；开启鉴权后从 `/next/login` 进入。

前端构建（若 `web-next/dist` 不存在）：

```bash
cd web-next && npm install && npm run build
```

本地模型（可选）：

```bash
ollama pull qwen3:4b          # 显卡够可换 qwen3:14b
```

未安装或不可用时，系统自动退回确定性模板，功能不受影响（`LIRA_LLM=off` 强制关闭）。

## 架构

```
采集适配（api / manual） → 契约校验 → 到手价计算 → 规则事件
  → LangGraph（load → plan → tools → react → steward → analysis → risk → verify → writer → suggest）
  → 人工审批 → 执行适配（off / preview / webhook） → 7 日结果回收
```

- **多 Agent**：Steward（数据门禁）/ Analyst（归因）/ Risk（毛利与护栏）/ Writer（文案），
  节点间结构化 handoff（每次运行 ≤ 2 次）；`react` 节点提供有界 ReAct（步数 / 时长 / 无进展三重上限）。
- **不变量**：动作只由 `agent._decide_action` 决定；证据闭包不通过整条作废；人工审批是唯一执行入口。
- **RAG**：父子块切分（LlamaIndex）+ Qdrant + 向量 / 关键词 RRF + 重排；检索侧含查询改写与二跳。
- **MCP**：`python -m app.mcp_server` 暴露与站内一致的 7 个工具，支持令牌校验。
- **评测**：120 条分层金标 + 检索金标 + floor/delta 门禁 + 判官校准。
- **可观测**：span 追踪、token / 成本、P50 / P95 / P99。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `LIRA_DATA_DIR` | `./data` | 数据目录（SQLite、Qdrant 本地存储、备份） |
| `LIRA_DATABASE_URL` | 空 | 设置后使用 PostgreSQL |
| `LIRA_LLM` | `auto` | `auto / off / on` |
| `LIRA_LLM_BACKEND` | `legacy` | `legacy`（直连 Ollama）/ `gateway`（多 Provider 路由，推荐） |
| `LIRA_LLM_ROUTE` | `auto` | `auto / ollama / openai` |
| `LIRA_OLLAMA_URL` | `http://127.0.0.1:11434` | 本地模型地址 |
| `LIRA_OLLAMA_MODEL` | `qwen3:4b` | 本地模型名 |
| `LIRA_OPENAI_BASE_URL` | 空 | OpenAI 兼容端点（DashScope / DeepSeek 等） |
| `LIRA_OPENAI_API_KEY` | 空 | 对应 API Key |
| `LIRA_OPENAI_MODEL` | `qwen-plus` | 云端模型名 |
| `LIRA_JUDGE_MODEL` | 空 | 判官模型；不配则不启用 LLM 判官 |
| `LIRA_LLM_RPM` | `60` | 每请求限流（次 / 分钟） |
| `LIRA_AGENT_MAX_STEPS` | `6` | 有界 ReAct 步数上限 |
| `LIRA_TAINT_ENFORCE` | `on` | 上下文被污染时只保留只读工具 |
| `LIRA_AUTH` | 关闭 | 开启后需要登录，采集端可用 Bearer 令牌 |
| `LIRA_SCHEDULER` | `celery` | `celery / thread / off` |
| `LIRA_MCP_SECRET` | 空 | 设置后 MCP 客户端需提供相同 `LIRA_MCP_TOKEN` |

接云端模型示例：

```bash
export LIRA_LLM=on LIRA_LLM_BACKEND=gateway LIRA_LLM_ROUTE=auto
export LIRA_OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export LIRA_OPENAI_API_KEY=sk-xxx
export LIRA_OPENAI_MODEL=qwen-plus
```

## 数据接入

设置页可配置三类来源，保存后立即生效：

- **淘宝开放平台**：App Key / App Secret（用于后续对接开放接口）
- **影刃八爪鱼**：API 地址与 Access Token
- **文件导入**：CSV（`target_id,ts,list_price,title,source_tier`）或 JSON 快照数组，
  接口 `POST /api/import/file`；外部系统也可直接推送 `POST /v1/ingest/snapshots`（支持 Bearer 令牌）。

## 评测

```bash
python scripts/gen_golden_cases.py         # 生成 120 条金标
python scripts/eval_gate.py --tier smoke   # PR 门禁（确定性，约 5s）
python scripts/eval_gate.py --tier full    # 全量
python scripts/calibrate_judge.py          # 判官校准（需 LIRA_JUDGE_MODEL）
```

- 指标：动作准确率、证据闭包率、轨迹完整率、检索 Recall@k / MRR。
- 坏例自动入库：`GET /api/eval/badcases`。
- 判官未通过校准（kappa < 0.70）时只作参考，不参与门禁。
- 评测与运行中的服务共用本地 Qdrant 会抢锁，门禁建议用独立数据目录：
  `LIRA_DATA_DIR=$(mktemp -d) python scripts/eval_gate.py --tier smoke`。

## 主要接口

| 分组 | 接口 |
| --- | --- |
| 采集 | `POST /v1/ingest/snapshots`、`POST /v1/ingest/validate` |
| 事件 | `GET /api/events`、`GET /api/events/{id}`、`POST /api/events/{id}/analyze` |
| 建议与审批 | `/api/suggestions*`、`/api/approvals/inbox`、`/api/executions/{id}/rollback` |
| 知识库 | `GET/POST /api/docs`、`GET /api/docs/search` |
| 数据接入 | `POST /api/import/file`（CSV/JSON）、`/api/settings/sources` |
| AI 能力 | `GET /api/agent/insights`、`POST /api/agent/chat`、`POST /api/llm/stream` |
| 工具 | `GET /api/tools`、`POST /api/llm/stream`（SSE） |
| 评测 | `/api/eval/*`、`GET /api/observability/traces[/{trace_id}]` |
| 运维 | `GET /api/health`、`/api/metrics`、`/api/ops`、`/api/stream`（SSE） |

## 测试

```bash
pytest -q                            # 后端
LIRA_TEST_DB=postgres pytest         # PostgreSQL 回归
cd web-next && npx playwright test   # 冒烟 e2e（本机 Edge）
```

## 目录

```
app/                       后端（FastAPI + LangGraph + Celery）
app/routers/               15 个领域路由
app/llm/                   多 Provider 网关（路由 / 退避 / 熔断 / 限流 / 账本）
app/evaluation/            金标、指标、判官、运行器、门禁
app/safety/                注入隔离、PII 脱敏
app/context.py             分层上下文构建（预算 / 优先级 / 不可信标记）
app/retrieval_service.py   查询改写 + 多跳 + 融合 + trace
web-next/                  React + TS 工作台（唯一前端）
scripts/                   评测门禁、金标生成、判官校准、迁移、向量重建
tests/                     后端测试
```

## 数据库

默认 SQLite（`data/lira.db`），生产 PostgreSQL（`docker compose up -d db`）。
从 SQLite 搬迁：`python scripts/migrate_sqlite_to_pg.py --truncate`（逐表核对行数）。
