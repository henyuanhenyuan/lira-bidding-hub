# Lira 电商 · 交接说明

> 更新于 2026-11-09。面向下一位接手的人（或未来的我）。

## 一句话

单机可运行的电商竞品情报 Agent：**采集 → 到手价 → 事件 → 多 Agent 研判 → 人工审批 → 结果回收**，每一步有证据与轨迹；模型只解释，动作由确定性策略给出。

## 当前状态

| 项目 | 状态 |
| --- | --- |
| 最新提交 | `30b5657 chore: 项目统一命名为 Lira 电商` |
| 工作树 | 干净 |
| 端口 | 统一 **8011** |
| 后端测试 | 370 项，全绿 |
| 评测门禁 | `eval_gate --tier smoke` 通过；动作/证据/轨迹/检索 均 1.0 |
| e2e | Playwright 10 项通过 |
| 模型 | 默认本地 `qwen3:4b`（Ollama）；可在设置页切到云端 `qwen-plus` |
| GitHub | 私有仓库已建：https://github.com/henyuanhenyuan/lira- ，**尚未推送** |

## 怎么跑

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

打开 http://127.0.0.1:8011/next 。默认本地模式无需登录；开启鉴权后从 `/next/login` 进入。

前端构建（dist 不存在时）：

```bash
cd web-next && npm install && npm run build
```

本地模型：

```bash
ollama pull qwen3:4b
```

模型不可用时自动走确定性模板，功能不受影响；`LIRA_LLM=off` 强制关闭。

## 界面结构（只有 4 个一级入口）

- **工作区**：商品货架（竞价对比）+ AI 市场解读 + 事件与处置 + AI 研判 + 问 Agent；右上角「沉浸大屏」
- **大屏**：`/screen`，不在侧栏，自动贩卖机陈列 + 指标 + 评测 + 执行脉冲 + 跑马灯，10s 自动刷新
- **Agent**：研判流水线、工具货架、Skill 货架、流式试跑
- **知识库**：知识货架 + 检索命中 + 新增文档
- **设置**：模型来源（本地/云端）、数据接入（淘宝 / 影刃八爪鱼 / 文件）、账号、运行环境

设计语言：玩具风商品封面、贴纸、价签，货架统一装进玻璃货柜；我方价高亮。

## 能力清单

- 多 Agent：Steward / Analyst / Risk / Writer + 结构化 handoff（≤2 次）+ 有界 ReAct（步数/时长/无进展三重上限）
- RAG：Qdrant + 父子块 + 向量/关键词 RRF + 重排 + 查询改写 + 二跳
- 上下文：`app/context.py` 分层裁剪（L0 指令 / L1 事实 / L2 记忆 / L3 规则），不可信内容统一标记
- 安全：注入隔离 + 污染时只读工具、PII 脱敏、审批风险分级、MCP 令牌
- 评测：120 条金标（价格 40 / 护栏 30 / 注入 15 / 低置信 20 / SOP 15）+ 检索金标 + floor/delta 门禁 + 判官校准（kappa 1.0）
- 观测：span 追踪、token/成本、P50/P95/P99
- 数据接入：CSV/JSON 文件、推送接口 `/v1/ingest/snapshots`、淘宝与八爪鱼配置位

## 待办（按优先级）

1. **P0 推送 GitHub**：仓库已建，缺一次授权。两种方式：
   - 提供带 `repo`（或该仓库 Contents 写）权限的 PAT，用一次性 header 推送；
   - 或在已授权的机器上 `git push -u origin main`。
   远程已配置：`origin https://github.com/henyuanhenyuan/lira-.git`（GitHub 把「电商」转成了 `-`；要纯英文名可改 `lira-ecommerce`）。
2. **P1 判官校准换难例**：现有 24 条都是对错分明样本，kappa=1.0 不代表难题稳定。建议用真实 badcase 重跑 `scripts/calibrate_judge.py`。
3. **P2 报告结论 #2（可选）**：vLLM/SGLang 推理部署、LoRA/SFT/DPO 微调——当前刻意未做，面向 30K+ 岗位时再补。
4. 同类项目差距（可选）：多租户、RAGAS 适配、分层上下文数据库。

## 已知限制

- 评测与运行中的服务共用本地 Qdrant 会抢锁，门禁请用独立数据目录：
  `LIRA_DATA_DIR=$(mktemp -d) python scripts/eval_gate.py --tier smoke`
- 大屏“运行评测”走 `retrieval=false` 的快路径（避免 bge-m3 让评测变慢）；完整检索评测走命令行。
- 4B 模型偶尔输出“思考过程”，已对解读/问答加 JSON 约束与无效回退（规则兜底）。
- 云端模型需要在设置页填 Base URL 与 Key，密钥只写入 `data/settings.json`（`data/` 已 gitignore）。

## 关键文件

```
app/agent.py              归因、证据校验、确定性动作策略
app/agent_graph.py        LangGraph 状态机、有界 ReAct、handoff、记忆注入
app/context.py            分层上下文构建
app/retrieval_service.py  查询改写 + 二跳 + 加权 RRF + trace
app/llm/                  多 Provider 网关（路由/退避/熔断/限流/账本）
app/evaluation/           金标、指标、判官、运行器、门禁
app/safety/               注入隔离、PII 脱敏
app/routers/              15 个领域路由
app/settings_store.py     运行时设置（模型与数据接入）
web-next/src/ui/viz.tsx   货架、货柜、贩卖机、流水线、星图等可视化组件
scripts/eval_gate.py      评测门禁
scripts/calibrate_judge.py 判官校准
```

## 常用命令

```bash
pytest -q
LIRA_TEST_DB=postgres pytest
python scripts/eval_gate.py --tier smoke
python scripts/gen_golden_cases.py
python scripts/calibrate_judge.py
cd web-next && npx playwright test
```

## 今天这轮改了什么（提交记录）

- `f5daba6` 货架式前端、数据接入与实时 AI 解读
- `d629660` 删除被取代的旧路线文档
- `30b5657` 项目统一命名为 Lira 电商

更早两个大提交：`321770a`（前端重写、后端瘦身、端口 8011）、`bebb10e`（评测体系、模型网关、安全与可观测）。
