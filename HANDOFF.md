# Lira 电商 · 交接说明

> 更新于 2026-11-09。当前版本按 `D:\lirav1` 的前端设计系统重做，只保留一个自定义模块：商品货架/自动贩卖机。

## 一句话

单机可运行的电商竞品情报 Agent：**采集 → 到手价 → 事件 → 多 Agent 研判 → 人工审批 → 结果回收**。模型只解释，动作由确定性策略给出，证据与轨迹全程可查。

## 当前状态

| 项目 | 状态 |
| --- | --- |
| 后端测试 | **376 项全绿** |
| 前端 e2e | **12 项全过**（Playwright + Edge） |
| 端口 | 应用 **8011**；PostgreSQL **5432**；Vite 预览 **5173** |
| 数据层 | PostgreSQL 16 + pgvector（唯一后端） |
| 鉴权 | 默认开启；5 个交付账号 |
| 核心模型 | API 集成建议 `qwen-plus`（本轮未拉取，配置已预置） |
| 测试模型 | 本机 `qwen3:4b`（Ollama），仅回归/演示 |
| 演示数据 | 18 个竞品目标（t1–t18），货架 9 个/排 |
| 工作树 | 本轮改动未提交 |

## 怎么跑

```bash
docker compose up -d db
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

登录：http://127.0.0.1:8011/next/login

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `Lira@Admin2026` | 管理员 |
| `manager` | `Lira@Manager2026` | 主管 |
| `analyst` | `Lira@Analyst2026` | 主管（分析师） |
| `operator` | `Lira@Ops2026` | 成员（运营） |
| `viewer` | `Lira@View2026` | 成员（只读） |

本地免登录开发：`LIRA_AUTH=off`。前端：`cd web-next && npm run dev`（5173，代理 8011）。

## 界面（与 lirav1 统一）

- 设计系统：`D:\lirav1\frontend\src\styles.css` 原样作为基座——极光背景、毛玻璃 Panel、顶栏、三段导航、KPI 磁贴、seg 切换、driver 行、timeline、QA 小窗。
- **登录** `/next/login`：左右分栏，极光玻璃登录卡，不展示账号列表。
- **智能竞价分析** `/`：顶栏 + `seg` 筛选；6 个 KPI（我方价置顶）；**整行自动贩卖机货架**（18 个彩色笑脸袋，9 个/排，深蓝霓虹外壳、白色价签）；AI 市场解读；事件与处置；AI 研判；价格带；SKU 对齐；结果回收；研判漏斗。
- **Agent 模型** `/agent`：运行轨迹、能力矩阵、知识与案例、评测门禁、LoRA/SFT 五个 `seg` 页签，全部 Panel/table/timeline 结构。
- **设置** `/settings`：接入模块（三个通道 + 令牌 + 测试推送）、模型路由（一个 API + 一个本地）、账号、我的账号、采集队列、运行环境、健康门禁、写入日志。
- **大屏** `/screen`：固定 `100vh` 霸屏不滚动；左侧核心指标 + AI 解读，中间 6×3 笑脸袋贩卖机（我方价大号置顶），右侧评测/执行脉冲/最近运行，底部跑马灯。

## 本轮新增/改动

1. **前端照搬 lirav1**：样式、Shell、Login、Panel/KPI/seg/表格式布局与交互统一；删除旧的 Workspace/Data/Knowledge/viz。
2. **货架组件**：`web-next/src/ui/shelf.tsx`。深蓝霓虹外壳、自动贩卖机头/玻璃/层板/投币口；彩色笑脸袋、白色价签、严重度贴纸、我方价醒目。
3. **18 个竞品演示数据**：t1–t18，含价格点与事件，货架可铺满 2–3 排。
4. **账号**：5 个真实账号，启动幂等写入；`display_name`/角色文案。
5. **接入服务**：令牌创建/吊销（只存哈希）、Bearer 写入、干跑、真实测试推送、写入日志；三个通道置顶。
6. **模型**：一个 API（OpenAI 兼容，建议 qwen-plus）+ 一个本地（Ollama qwen3:4b）；`/api/settings/providers` 存取/探测。
7. **LoRA/SFT**：导出 SFT JSONL、生成 PEFT + TRL 配置与训练脚本、校验。
8. **性能**：首屏不等 LLM 解读；健康检查向量计数缓存；SSE 刷新去抖；大屏 100vh。

## 测试

```bash
docker compose up -d db
pytest -q                                   # 376 项
cd web-next && npm run build                # TS + Vite
PLAYWRIGHT_PORT=8012 npx playwright test    # 12 项，避开 8011 正在运行的服务
```

e2e 会向开发库写入 `demo-sku-001` 和 `e2e-token`；本轮结束后已清理。重复跑 e2e 后可按同样方式清理。

## 已知限制

- `qwen-plus` 本轮未拉取；API 集成需填 Key 才能真实调用，当前默认走本机 4B。
- 训练依赖（torch/transformers/peft/trl）未安装；微调链路已能导出与校验，训练在 GPU 机器执行 `data/finetune/train_lora.py`。
- 4B 偶发输出思考过程；解读/问答已有 JSON 约束与规则兜底。
- 评测写库；门禁建议用独立库 `lira_eval`。
- 本轮改动未提交。

## 关键文件

```
app/auth.py                     5 个账号、令牌校验
app/routers/integration.py      接入服务
app/routers/settings.py         模型/数据源/探测
app/finetune.py                 LoRA/SFT 数据、配置、校验
app/llm/service.py              多 Provider 网关
app/routers/ops.py              健康检查（向量计数缓存）
web-next/src/styles.css         lirav1 设计系统 + 货架
web-next/src/ui/shell.tsx       顶栏 + 三段导航
web-next/src/ui/shelf.tsx       自动贩卖机货架
web-next/src/ui/kit.tsx         Panel/KPI/seg/QA 基础组件
web-next/src/pages/Bidding.tsx  智能竞价分析
web-next/src/pages/AgentHub.tsx Agent 模型
web-next/src/pages/Settings.tsx 设置
web-next/src/pages/BigScreen.tsx 大屏
web-next/src/pages/Login.tsx    登录
```

## 常用命令

```bash
docker compose up -d db
pytest -q
cd web-next && npm run build
PLAYWRIGHT_PORT=8012 npx playwright test
python scripts/eval_gate.py --tier smoke
python scripts/reindex_vectors.py
```
