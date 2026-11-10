# Lira · 竞价智能中枢 · 交接说明

> 更新于 2026-11-10，文档已按当前代码与运行态核对。本轮为彻底重构：前端整站重写，后端沿用并补齐自主竞价与微调链路。

## 一句话

以 Agent 为主、人为辅的电商竞价系统：**采集竞品价格 → 事件识别 → 多智能体研判 → 自主调价 →
仅异常进入人工确认台**，全流程 SSE 实时与 span 追踪可查。

## 当前状态

| 项目 | 状态 |
| --- | --- |
| 后端测试 | **383 项全绿**（`pytest -q`，依赖 PostgreSQL + pgvector） |
| 前端 | React + TS + Vite，毛玻璃控制台 + 全屏大屏，`npm run build` 由后端 `/next` 提供 |
| 端口 | 应用 **8011**；PostgreSQL **5432**；Ollama **11434** |
| 数据层 | PostgreSQL 16 + pgvector（唯一后端） |
| 鉴权 | 默认开启；5 个交付账号（见 AGENTS.md） |
| 调度 | 进程内调度器（thread），自主竞价每 120s 巡检；Redis/Celery 未启用 |
| 本地模型 | `lira-bid:v1`（Qwen3-4B + 竞价 LoRA，q8_0 GGUF，4.3G），`data/settings.json` 已设为默认本地模型 |
| 云端通道 | OpenAI 兼容，默认 `qwen-plus`，设置页切换 |
| 微调记录 | 3 个任务：58 条 validated、77 条 ready、77 条 trained 并部署 |
| 演示数据 | 18 个竞品目标（t1–t18），5 个地区 |

## 怎么跑

```bash
docker compose up -d db
pip install -r requirements.txt
cd web-next && npm install && npm run build
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

打开 http://127.0.0.1:8011/next/login 。

## 关键链路

- **采集**：影刃/八爪鱼、自有爬虫（含 Playwright 直采）、开放 API、CSV/XLSX/JSON 文件导入
- **研判**：LangGraph 七阶段（门禁 / 规划 / 工具 / 研判 / 风控 / 校验 / 输出），工具走 MCP
- **执行**：毛利护栏与幅度护栏校验，通过则自动执行，异常转人工确认台
- **观测**：`/api/stream` SSE（agent/autopilot/event/approval）+ `/api/observability/traces`

## 微调

数据 → 配置 → 训练 → 合并 → GGUF → Ollama 全流程见 README「微调（LoRA）」。
最近一次训练（77 条样本）在本机 8GB 显卡上通过 `max_gpu_memory: 7GiB` 完成：
20 步 / 1 epoch / 约 30 分钟，`train_loss 1.3776`，adapter 在
`data/finetune/lora-out/`，合并后 GGUF 为 `data/models/qwen3-4b-lora-q8.gguf`，
已注册为 `lira-bid:v1` 并在设置中切为默认本地模型。

## 已知限制

- Redis 未启动，Celery beat 不生效，用 thread 调度替代。
- `lira-bid:v1` 基于 77 条样本，能力面窄，只作为「对 qwen-plus 微调」的本地替身。
- Windows 下 bitsandbytes 暂无轮子，QLoRA / 4bit 量化需 Linux；纯 CPU 训练可用但更慢。
