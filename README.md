# Lira · 竞价智能中枢

以 Agent 为主、人为辅的电商竞价系统：采集竞品价格 → 事件识别 → 多智能体研判 → 自主调价 →
只有异常进入人工确认台，全流程可观测。

## 技术选型

| 层 | 选型 |
| --- | --- |
| 后端 | Python + FastAPI |
| Agent | LangGraph 编排 ReAct/多智能体，MCP 工具协议 |
| RAG | PGVector（PostgreSQL 16 + pgvector）+ 混合检索 + Rerank |
| 数据库 | PostgreSQL（单一数据源） |
| 调度 | 进程内调度器（thread 模式，默认）/ Celery + Redis（可选） |
| 实时 | SSE（`/api/stream`）+ 轻量 span 追踪 |
| 采集 | 影刃 / 八爪鱼通道、自有爬虫（含 Playwright 直采）、开放 API、文件导入 |
| 模型 | 本地推理通道 + 云端 OpenAI 兼容通道，可在设置页切换；失败自动降级到模板策略 |
| 评测 | 评测集 + LLM-as-Judge + 质量闸门 |
| 前端 | React + TypeScript + Vite，毛玻璃控制台 + 全屏大屏 |

## 运行

```bash
docker compose up -d db          # PostgreSQL 16 + pgvector，127.0.0.1:5432
pip install -r requirements.txt

# 后端（登录开启 / 线程调度 / 模型网关）
LIRA_AUTH=on LIRA_SCHEDULER=thread LIRA_LLM=on \
LIRA_LLM_BACKEND=gateway LIRA_LLM_ROUTE=ollama \
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011

# 前端
cd web-next && npm install && npm run build
```

打开 http://127.0.0.1:8011/next/login 。前端开发模式：`cd web-next && npm run dev`（5173 代理到 8011）。

本机直跑默认 `LIRA_AUTH=on`、`LIRA_SCHEDULER=thread`；`docker compose` 编排预置
`LIRA_AUTH=off` + Celery/Redis，按需改环境变量即可。

## 微调（LoRA）

数据、配置、训练全部走 PEFT + TRL，不自研训练框架：

```bash
curl -X POST http://127.0.0.1:8011/api/finetune/dataset -d '{"limit":400}'
curl -X POST http://127.0.0.1:8011/api/finetune/jobs -d '{"name":"竞价策略 LoRA","method":"lora"}'
python data/finetune/train_lora.py --config data/finetune/config-<job_id>.json
```

本机 8GB 显卡通过 `max_gpu_memory: 7GiB` 完成了 77 条样本 1 epoch 的训练
（20 步，约 30 分钟，train_loss 1.38），产出
`data/finetune/lora-out/adapter_model.safetensors`。显存不足时可把 `"device"` 设为
`"cpu"`，在 32G 内存上跑同一条链路；Windows 下没有 bitsandbytes 轮子，QLoRA 需 Linux。

### 合并并接入推理

```bash
# 1. 合并 adapter 到基座（需 transformers + peft）
python scripts/merge_lora.py data/models/Qwen3-4B data/finetune/lora-out data/models/Qwen3-4B-lora-merged

# 2. 转 GGUF（llama.cpp 的 convert_hf_to_gguf.py，q8_0 约 4.3G）
python data/llama.cpp/convert_hf_to_gguf.py data/models/Qwen3-4B-lora-merged \
  --outfile data/models/qwen3-4b-lora-q8.gguf --outtype q8_0

# 3. 注册进 Ollama（0.40 已移除 ADAPTER，必须先合并权重）
printf 'FROM D:/MS/data/models/qwen3-4b-lora-q8.gguf\n' > data/finetune/Modelfile.q8
ollama create lira-bid:v1 -f data/finetune/Modelfile.q8

# 4. 切成默认本地模型
curl -X POST http://127.0.0.1:8011/api/settings/models \
  -H 'Content-Type: application/json' \
  -d '{"backend":"gateway","route":"ollama","local_model":"lira-bid:v1","local_url":"http://127.0.0.1:11434","api_base_url":"https://dashscope.aliyuncs.com/compatible-mode/v1","api_model":"qwen-plus"}'
```

## 租户账号

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| admin | `Lira@Admin2026` | 负责人 |
| manager | `Lira@Manager2026` | 竞价主管 |
| analyst | `Lira@Analyst2026` | 价格分析师 |
| operator | `Lira@Ops2026` | 运营执行 |
| viewer | `Lira@View2026` | 只读观察 |

## 主要页面

- **调度中枢**：Agent 运行流、区域矩阵、竞价流水、待人工确认、系统脉搏（SSE 实时刷新）
- **竞价台**：目标池、竞品价差、策略切换、单目标即时研判、异常确认、调价流水
- **智能体**：技能包、MCP 工具链、ReAct 执行计划、全链路追踪
- **数据接入**：影刃/八爪鱼与自有爬虫双通道配置、CSV/Excel/JSON 文件导入、推送接口、采集日志
- **评测**：评测批次、质量闸门、Bad Case、模型调用结构
- **设置**：本地/云端模型通道切换、竞价策略与护栏、LoRA 微调、租户成员、运维任务
- **大屏**：`/next/screen`，全屏实时监控

## 关键接口

```
POST /api/import/file              CSV / XLSX / JSON 文件接入
POST /api/crawl/config             影刃 / 自有爬虫配置
POST /api/crawl/run                派发采集
GET  /api/dashboard?days&region    控制台聚合数据
GET  /api/autopilot/exceptions     待人工确认
POST /api/autopilot/exceptions/{id}/resolve
GET  /api/stream                   SSE 实时事件（agent / autopilot / event / approval）
GET  /api/observability/traces     追踪列表与详情
POST /api/settings/models          本地 / 云端通道切换
POST /api/agent/chat               单目标即时研判
GET  /api/agent/runs/{run_id}      研判运行与逐步轨迹
POST /api/finetune/dataset         生成 SFT 数据集
POST /api/finetune/jobs            创建 LoRA 微调任务
POST /api/ops/run                  手动触发备份 / 重索引等运维任务
POST /v1/ingest/validate           采集数据校验
```

采集端可用 Bearer 令牌写入 `/v1/ingest/snapshots`，不影响人工登录。

## 评测

```bash
python scripts/gen_golden_cases.py             # 生成金标用例
python scripts/eval_gate.py --tier smoke       # PR 门禁
python scripts/eval_gate.py --tier full        # 全量并产出 Markdown 报告
```

## 测试

```bash
docker compose up -d db        # 测试依赖 PostgreSQL + pgvector
pytest -q                      # 383 项
```
