# AGENTS.md — AI Coding 工作流

本仓库按「测试先行 → 评测基线 → 提交」的流程演进。任何人（包括 AI 助手）改代码前先读本文件。

## 运行

```bash
docker compose up -d db        # PostgreSQL 16 + pgvector，127.0.0.1:5432
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

前端（web-next）：

```bash
cd web-next && npm install && npm run build   # 产物由后端在 /next 提供
```

入口 `/next/login`，鉴权默认开启。交付账号：`admin / Lira@Admin2026`、
`manager / Lira@Manager2026`、`analyst / Lira@Analyst2026`、
`operator / Lira@Ops2026`、`viewer / Lira@View2026`。

## 界面结构

毛玻璃控制台，路由全部挂在 `/next` 下：`/`（调度中枢）、`/bidding`（竞价台）、
`/agents`（智能体）、`/sources`（数据接入）、`/evaluation`（评测）、`/settings`（设置），
另有 `/screen` 全屏大屏。

- 只有异常需要人工确认，其余由 Agent 自动执行；前端不展示「测试模型」字样，
  本地与云端通道统一显示为 **Qwen-Plus · 竞价微调版**。
- 模型通道在设置页切换（本地 Ollama / 云端 OpenAI 兼容），默认走本地。

## 测试

```bash
docker compose up -d db        # 测试依赖 PostgreSQL + pgvector
pytest -q                      # 383 项
```

## 评测

```bash
python scripts/gen_golden_cases.py             # 重新生成金标（120 条）
python scripts/eval_gate.py --tier smoke       # PR 门禁
python scripts/eval_gate.py --tier full        # 全量，产出 Markdown 报告
python scripts/eval_gate.py --tier smoke --update-baseline   # 更新基线
```

## 约定

- 基础设施只用现成组件（FastAPI / LangGraph / MCP / PGVector / PEFT+TRL / Ollama），不自研框架。
- 数据库只有 PostgreSQL 一个来源；`data/`、`web-next/dist`、模型权重与 GGUF 均不入库。
- 定时任务默认走进程内调度器（`LIRA_SCHEDULER=thread`）；启用 Celery 需先起 Redis。
