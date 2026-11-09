# AGENTS.md — AI Coding 工作流

本仓库按「测试先行 → 评测基线 → 提交」的流程演进。任何人（包括 AI 助手）改代码前先读本文件。

## 运行

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

前端（web-next）：

```bash
cd web-next && npm install && npm run build
```

入口 `/next/login`，鉴权默认开启。交付账号：`admin / Lira@Admin2026`、
`manager / Lira@Manager2026`、`analyst / Lira@Analyst2026`、
`operator / Lira@Ops2026`、`viewer / Lira@View2026`。

一级入口只有三个：`/`（智能竞价分析）、`/agent`（Agent 模型）、`/settings`（设置）；
另有 `/screen` 沉浸大屏与 `/next/login`。界面照搬 `D:\lirav1` 设计系统（极光玻璃、顶栏 + 三段导航、Panel/KPI/seg）；唯一自定义模块是商品货架（深蓝霓虹自动贩卖机 + 彩色笑脸袋）。

## 测试

```bash
docker compose up -d db        # 测试依赖 PostgreSQL + pgvector
pytest -q                      # 376 项
cd web-next && npx playwright test   # 12 项；PLAYWRIGHT_PORT=8012 可避开正在运行的服务
```

## 评测

```bash
python scripts/gen_golden_cases.py             # 重新生成金标（120 条）
python scripts/eval_gate.py --tier smoke       # PR 门禁
python scripts/eval_gate.py --tier full        # 全量，产出 Markdown 报告
python scripts/eval_gate.py --tier smoke --update-baseline   # 更新基线
```

门禁规则：floor + delta 双门限。回退超过 2 个百分点即失败。

## 模型配置

- 本机 4B：Ollama（`qwen3:4b`），**只做测试与离线演示**。
- 生产核心：一个 API 集成，默认建议 `qwen-plus`（DashScope），在设置页「模型与通道」保存；
  API 集成写入 `settings_store.api_providers`，本地集成仍是 Ollama。
- 路由：`openai`（API 集成）、`ollama`（本地）、`auto`（API 优先、本地兜底）。
- 微调：`/api/finetune/*` 导出 SFT JSONL、生成 PEFT + TRL 配置并校验；训练依赖未安装不影响推理。

## 新模块

- `app/routers/integration.py`：接入令牌（哈希存储）、推送/干跑、写入日志。
- `app/routers/finetune.py` + `app/finetune.py`：LoRA / SFT 数据与配置。
- `app/routers/settings.py`：单个 API 集成 + 本地集成的读写与真实探测。

## AI Coding 约定

1. **先写失败测试**，再写实现；提交前 `pytest -q` 必须全绿。
2. **Prompt 改动必须带评测用例**：改 `app/agent.py` / `app/reviews.py` 中的提示词，
   同时更新 `app/prompts/registry.py` 的版本号，并在 `scripts/gen_golden_cases.py`
   里补一条对应用例，然后跑 `eval_gate.py --tier core`。
3. **不变量**：动作永远由确定性策略给出（`agent._decide_action`），模型只写解释；
   证据闭包不通过整条作废；人工审批是唯一执行入口。
4. **新增工具**必须在 `app/tools.py` 标注 `risk`（read / reversible_write /
   irreversible_write），写类工具默认不进 MCP 暴露集。
5. **不要**为了让测试通过而放宽校验；改断言要说明业务理由。

## 关键目录

| 路径 | 作用 |
| --- | --- |
| `app/agent.py` | 归因、证据校验、动作策略、LLM 调用 |
| `app/agent_graph.py` | LangGraph 状态机、有界 ReAct、handoff、记忆注入 |
| `app/evaluation/` | 金标集、指标、判官、运行器、报告 |
| `app/llm/` | 多 Provider 网关（路由 / 退避 / 熔断 / 限流 / 账本） |
| `app/routers/integration.py` | 接入令牌、推送、写入日志 |
| `app/finetune.py` | SFT 数据导出、PEFT/TRL 配置、校验 |
| `web-next/src/pages/` | Bidding / AgentHub / Settings / BigScreen / Login |
| `app/safety/` | 注入隔离与 PII 脱敏 |
| `app/tracing.py` | span 追踪 |
| `scripts/eval_gate.py` | 评测门禁 |
| `tests/golden` → `app/evaluation/golden/` | 金标数据（随代码发布） |
