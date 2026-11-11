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

入口 `/next/login`，鉴权默认开启。交付账号：`viewer / Lira@View2026`。

本机直跑默认 `LIRA_AUTH=on`、`LIRA_SCHEDULER=thread`；`docker compose` 编排预置
`LIRA_AUTH=off` + Celery/Redis，需要时显式覆盖环境变量。

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
python scripts/gen_golden_cases.py             # 重新生成金标
python scripts/eval_gate.py --tier smoke       # PR 门禁
python scripts/eval_gate.py --tier core        # 核心集
python scripts/eval_gate.py --tier full        # 全量，产出 Markdown 报告
python scripts/eval_gate.py --tier smoke --update-baseline   # 更新基线
```

## 微调

数据、配置、训练全部走 PEFT + TRL，流程与产物见 README「微调（LoRA）」。当前线上
本地模型为 `lira-bid:v1`（Qwen3-4B + 77 条样本 LoRA，q8_0 GGUF），在设置页切换。

## 文档

`README.md` 面向使用者（运行、页面、接口、微调），`HANDOFF.md` 记录当前运行态与已知限制，
本文件约定协作流程。改代码或运行态变化时同步这几份文档，避免口径过期。

## 约定

- 基础设施只用现成组件（FastAPI / LangGraph / MCP / PGVector / PEFT+TRL / Ollama），不自研框架。
- 数据库只有 PostgreSQL 一个来源；`data/`、`web-next/dist`、模型权重与 GGUF 均不入库。
- 定时任务默认走进程内调度器（`LIRA_SCHEDULER=thread`）；启用 Celery 需先起 Redis。
