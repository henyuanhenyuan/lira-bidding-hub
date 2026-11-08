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

默认入口 `/` 会重定向到 `/next`；`/legacy` 保留旧版界面一个版本。

## 测试

```bash
pytest -q                      # SQLite
LIRA_TEST_DB=postgres pytest   # PostgreSQL 回归
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

- 本地开发：Ollama（`LIRA_OLLAMA_MODEL`，默认 `qwen3:4b`；显存够可换 `qwen3:14b`）。
- 演示 / 生产：OpenAI 兼容通道，建议 `qwen-plus`：

```bash
export LIRA_LLM_BACKEND=gateway
export LIRA_OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export LIRA_OPENAI_API_KEY=sk-xxx
export LIRA_OPENAI_MODEL=qwen-plus
```

`LIRA_LLM_ROUTE=auto|ollama|openai` 控制路由优先级；任一通道不可用会自动降级，
全部不可用时回落到确定性模板（与 `LIRA_LLM=off` 行为一致）。

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
| `app/safety/` | 注入隔离与 PII 脱敏 |
| `app/tracing.py` | span 追踪 |
| `scripts/eval_gate.py` | 评测门禁 |
| `tests/golden` → `app/evaluation/golden/` | 金标数据（随代码发布） |
