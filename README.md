# Lira 电商 — 竞品情报 Agent

单机可运行的竞品定价情报系统：**采集 → 到手价 → 事件 → 多 Agent 研判 → 人工审批 → 结果回收**，
每一步都有证据与轨迹，模型只负责解释，动作由确定性策略给出。

## 快速开始

```bash
docker compose up -d db          # PostgreSQL 16 + pgvector，监听 127.0.0.1:5432
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

打开 http://127.0.0.1:8011/next/login 。

鉴权默认开启，5 个交付账号：

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `Lira@Admin2026` | 管理员 |
| `manager` | `Lira@Manager2026` | 主管 |
| `analyst` | `Lira@Analyst2026` | 主管（分析师） |
| `operator` | `Lira@Ops2026` | 成员（运营） |
| `viewer` | `Lira@View2026` | 成员（只读） |

本地免登录开发可设 `LIRA_AUTH=off`。端口：应用 **8011**，PostgreSQL **5432**，Vite 开发 **5173**；Redis 只在 compose 网络内。

## 界面

采用 `D:\lirav1` 的前端设计系统（极光玻璃、顶栏 + 三段导航、Panel/KPI/seg）；只保留商品货架模块：深蓝霓虹自动贩卖机 + 彩色笑脸袋。

- **智能竞价分析** `/`：18 个竞品 SKU 的自动贩卖机货架（9 个/排），我方价置顶；AI 解读、事件与处置、AI 研判、价格带、SKU 对齐、结果回收、研判漏斗同屏。
- **Agent 模型** `/agent`：运行轨迹、能力矩阵、工具与 Skill、知识/案例、评测门禁、LoRA/SFT 微调链路。问答不占主区，收进右下角小窗。
- **设置** `/settings`：一个 API 集成 + 一个本地集成（两者都建议 `qwen-plus`）、三个接入通道、接入令牌、账户权限、运行环境。
- **大屏** `/screen`：100vh 霸屏不滚动；同款 6×3 货架、我方价大号置顶、实时指标、AI 解读、评测与执行脉冲，60s 刷新。
- **登录** `/next/login`：5 个真实账号，登录页不展示账号列表。

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
- **RAG**：父子块切分（LlamaIndex）+ PostgreSQL/pgvector + 向量 / 关键词 RRF + 重排；检索侧含查询改写与二跳。
- **MCP**：`python -m app.mcp_server` 暴露与站内一致的 7 个工具，支持令牌校验。
- **评测**：120 条分层金标 + 检索金标 + floor/delta 门禁 + 判官校准。
- **可观测**：span 追踪、token / 成本、P50 / P95 / P99。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `LIRA_DATA_DIR` | `./data` | 数据目录（上传、备份、运行时设置） |
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
| `LIRA_AUTH` | `on` | 登录与角色；采集端可用 Bearer 令牌 |
| `LIRA_SCHEDULER` | `celery` | `celery / thread / off` |
| `LIRA_MCP_SECRET` | 空 | 设置后 MCP 客户端需提供相同 `LIRA_MCP_TOKEN` |

接云端模型示例：

```bash
export LIRA_LLM=on LIRA_LLM_BACKEND=gateway LIRA_LLM_ROUTE=auto
export LIRA_OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export LIRA_OPENAI_API_KEY=sk-xxx
export LIRA_OPENAI_MODEL=qwen-plus
```

## 模型与微调

- **一个 API 集成**：OpenAI 兼容通道，默认建议 `qwen-plus`（DashScope）。设置页保存后写入 `data/settings.json`，Key 只落本地。
- **一个本地集成**：Ollama，默认 `qwen3:4b`，仅测试与离线演示；生产建议本地部署或代理 `qwen-plus`。
- API 集成接口：`GET/POST /api/settings/providers`、`POST /api/settings/providers/{id}/probe`；旧的 `POST /api/settings/models` 继续可用。
- 当前状态：本机 4B 测试通道在线；`qwen-plus` 只预置配置，不在本轮主动拉取。
- **LoRA / SFT**：`POST /api/finetune/dataset` 从真实研判与金标导出 chat JSONL；`POST /api/finetune/jobs` 生成 PEFT + TRL 配置；`POST /api/finetune/jobs/{id}/validate` 校验数据与配置。训练依赖未安装不影响线上推理，GPU 机器执行生成的 `data/finetune/train_lora.py` 即可。

## 数据接入

设置页顶部三个通道：**淘宝开放平台 / 影刃八爪鱼 / 文件导入**。另有推送 API 与接入令牌：

- `POST /v1/ingest/snapshots`（Bearer 令牌）
- `POST /v1/ingest/validate`（干跑校验）
- `POST /api/integration/tokens` 创建令牌（只显示一次）、`DELETE /api/integration/tokens/{id}` 吊销
- `POST /api/integration/test-push` 走真实摄取链路；`GET /api/integration/logs` 查看写入日志

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
- 评测会写入数据库，门禁建议用独立库：
  `LIRA_DATABASE_URL=postgresql://lira:lira@127.0.0.1:5432/lira_eval python scripts/eval_gate.py --tier smoke`。

## 运维脚本

| 脚本 | 用途 |
| --- | --- |
| `scripts/reindex_vectors.py` | 换 embedding 模型后重建 PGVector 索引 |
| `scripts/backup.py` | 在线备份（pg_dump，失败时逻辑导出） |
| `scripts/install-service.ps1` | 用 NSSM 把服务注册为 Windows 服务 |

## 主要接口

| 分组 | 接口 |
| --- | --- |
| 采集 | `POST /v1/ingest/snapshots`、`POST /v1/ingest/validate` |
| 事件 | `GET /api/events`、`GET /api/events/{id}`、`POST /api/events/{id}/analyze` |
| 建议与审批 | `/api/suggestions*`、`/api/approvals/inbox`、`/api/executions/{id}/rollback` |
| 知识库 | `GET/POST /api/docs`、`GET /api/docs/search` |
| 数据接入 | `POST /api/import/file`（CSV/JSON）、`/api/settings/sources` |
| 接入服务 | `/api/integration/overview`、`/api/integration/tokens`、`/api/integration/test-push`、`/api/integration/logs` |
| 模型通道 | `GET/POST /api/settings/providers`、`POST /api/settings/providers/{id}/probe` |
| 微调 | `/api/finetune/dataset`、`/api/finetune/stack`、`/api/finetune/jobs*` |
| AI 能力 | `GET /api/agent/insights`、`POST /api/agent/chat`、`POST /api/llm/stream` |
| 工具 | `GET /api/tools`、`POST /api/llm/stream`（SSE） |
| 评测 | `/api/eval/*`、`GET /api/observability/traces[/{trace_id}]` |
| 运维 | `GET /api/health`、`/api/metrics`、`/api/ops`、`/api/stream`（SSE） |

## 测试

```bash
pytest -q                            # 后端 376 项（需先 docker compose up -d db）
cd web-next && npx playwright test   # 前端 e2e 12 项（本机 Edge；可用 PLAYWRIGHT_PORT 换端口）
```

## 目录

```
app/                       后端（FastAPI + LangGraph + Celery）
app/routers/               17 个领域路由（含 integration / finetune）
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

统一 PostgreSQL 16 + pgvector（`docker compose up -d db`）。
首次启动自动创建 `vector`、`pg_trgm` 扩展与 HNSW 索引。
