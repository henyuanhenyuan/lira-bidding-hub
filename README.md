# 电商竞品情报 Agent（最小可运行版）

单机、单进程、单端口；本地 SQLite、生产 PostgreSQL，Ollama 可选。跑通四件事：
**采集导入 → 到手价估算 → 规则检测 → AI 归因与证据校验**。

## 快速开始

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

打开 http://127.0.0.1:8010 ，到「数据导入」点「载入演示数据」。

新版工作台（React + TS，灰度入口 `/next`）需要先构建：

```bash
cd web-next && npm install && npm run build
```

前端只有一个 React 工作台；未构建时 `/` 返回提示页，API 仍可用。

生产或多进程部署用 PostgreSQL（compose 已带数据库）：

```bash
docker compose up -d db
```

```bash
export LIRA_DATABASE_URL="postgresql://lira:lira@127.0.0.1:5432/lira"
```

从旧 SQLite 数据搬迁（先备份）：

```bash
python scripts/migrate_sqlite_to_pg.py --truncate
```

脚本会逐表核对行数，不一致时以非零状态退出。

本地模型（可选）：

```bash
ollama pull qwen3:4b
```

未安装或不可用时，系统自动走确定性模板，功能不受影响。
可用 `LIRA_LLM=off` 强制关闭，`LIRA_LLM=on` 强制启用。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `LIRA_DATA_DIR` | `./data` | 文件目录（SQLite、inbox、备份、密钥） |
| `LIRA_DATABASE_URL` | 空 | 设置后使用 PostgreSQL；不设则用本地 SQLite |
| `LIRA_OLLAMA_URL` | `http://127.0.0.1:11434` | 本地模型地址 |
| `LIRA_OLLAMA_MODEL` | `qwen3:4b` | 模型名 |
| `LIRA_LLM_TIMEOUT` | `20` | 单次调用超时（秒） |
| `LIRA_LLM` | `auto` | `auto / off / on` |
| `LIRA_SCHEDULER` | `celery` | `celery / thread / off`；`thread` 仅为离线兜底，已弃用 |
| `LIRA_REDIS_URL` | `redis://127.0.0.1:6379/0` | Celery broker 与 Redis 限流计数 |
| `LIRA_CELERY_EAGER` | `0` | 测试用：`1` 时任务同步执行，不连 broker |
| `LIRA_TZ` | `Asia/Shanghai` | Celery 时区 |
| `LIRA_COLLECT_INTERVAL` | `15` | 采集调度间隔（秒） |
| `LIRA_RL_RATE` | `0.2` | 令牌桶每秒补充数 |
| `LIRA_RL_CAPACITY` | `1` | 令牌桶容量（突发上限） |
| `LIRA_COLLECT_ACCOUNT` | `default` | 未在任务上指定账号时的默认值 |
| `LIRA_COLLECT_SHOP` | `default` | 未在任务上指定店铺时的默认值 |
| `LIRA_RISK_THRESHOLD` | `3` | 连续失败多少次触发熔断 |
| `LIRA_RISK_COOLDOWN` | `600` | 熔断冷却秒数，到期放行一次探测 |
| `LIRA_COLLECT_STALE` | `900` | 超过多少秒仍停在 running 的任务放回待下发 |
| `LIRA_QDRANT_URL` | 空 | 设置后连 Qdrant 服务；不设则用 `data/qdrant` 本地目录模式 |
| `LIRA_RERANK_URL` | 空 | 模型重排地址（TEI / Jina 兼容）；不设则走规则重排 |
| `LIRA_RERANK_MODEL` | `bge-reranker-v2-m3` | 重排模型名 |
| `LIRA_RERANK_TIMEOUT` | `5` | 重排超时（秒），超时自动降级 |
| `LIRA_STEWARD_ENFORCE` | `off` | `on` 时采集过期会把 L3 降为 L2，并标注 `downgraded_by_freshness` |
| `LIRA_INBOX_INTERVAL` | `15` | 收件箱轮询间隔（秒） |
| `LIRA_DIGEST_AT` | `09:00` | 每日摘要触发时间（本地时区） |
| `LIRA_WEBHOOK` | 空 | 企业微信/钉钉机器人地址 |
| `LIRA_AUTH` | `off` | `on` 时启用登录（首次自动创建 admin/admin123，请立刻改密） |
| `LIRA_INGEST_TOKEN` | 空 | 采集端服务令牌（`Authorization: Bearer`）。**启用鉴权时必须配置**，否则 RPA 写入会被拒绝 |
| `LIRA_COOKIE_SECURE` | `off` | HTTPS 部署时设为 `on`，Cookie 加 Secure |
| `LIRA_LOGIN_MAX_ATTEMPTS` | `5` | 每 IP 每分钟登录尝试上限，超出返回 429 |
| `LIRA_FRESH_SLA_HOURS` | `12` | 采集新鲜度 SLA，超时在事件页与系统页标红 |
| `LIRA_AGENT_LLM_PLANNER` | `off` | `on` 时让模型选择工具；失败自动回退确定性计划 |
| `LIRA_AGENT_LLM_CRITIC` | `off` | `on` 时增加一道 LLM 复核；驳回后回退模板并重新校验 |
| `LIRA_EXECUTOR_MODE` | `off` | `off` 仅记录 / `preview` 预演 / `webhook` 调外部执行 |
| `LIRA_EXECUTOR_URL` | 空 | 外部执行地址（POST 执行计划 JSON） |
| `LIRA_EXECUTOR_ROLLBACK_URL` | 空 | 外部回滚地址 |
| `LIRA_EXECUTOR_TOKEN` | 空 | 外部执行 Bearer Token |
| `LIRA_COST_PER_1K_TOKENS` | `0` | 每千 token 成本，本地 Ollama 通常为 0 |
| `LIRA_DAILY_TOKEN_BUDGET` | `0` | 24 小时 token 预算，0 表示不限制 |
| `LIRA_GATE_MIN_ACCURACY` | `0.8` | 上线门禁要求的最低评测通过率 |
| `LIRA_GATE_MAX_FALLBACK_RATE` | `0.6` | 回退率告警阈值 |
| `LIRA_GATE_ENFORCE` | `off` | `on` 时门禁未通过会拦截研判 |
| `LIRA_CONNECTOR_URL` | 空 | 三方数据 API 地址（返回 ingest 契约 JSON） |
| `LIRA_CONNECTOR_TOKEN` | 空 | 连接器 Bearer Token |
| `LIRA_CONNECTOR_RPM` | `60` | 连接器限流（次/分钟） |
| `LIRA_BACKUP_AT` | `03:30` | 每日备份时间 |
| `LIRA_BACKUP_KEEP` | `7` | 保留备份份数 |

## 目录结构

```
app/
  config.py      配置
  db.py          双后端 schema、连接与方言层
  migrate.py     SQLite → PostgreSQL 数据搬迁
  collectors.py  采集健康度与数据新鲜度
  stream.py      SSE 进程内广播
  contracts.py   Pydantic 契约（只收原始观测）
  pricing.py     到手价模型（区间 + 置信度 + 缺失字段）
  events.py      规则引擎（幅度 / 价格带 / 来源分级）
  evidence.py    证据闭包
  agent.py       LLM 归因 + 模板回退 + 动作策略
  agent_graph.py LangGraph 状态机（加载/计划/工具/归因/校验/建议）
  tools.py       MCP 工具注册表（站内与外部共用）
  mcp_server.py  MCP Server（stdio）
  docs.py        规则文档切片、向量检索与引用
  skills.py      Skill 注册表（触发条件/剧本/工具白名单）
  eval.py        评测金标集与运行器
  executor.py    执行适配器（记录/预演/Webhook + 回滚）
  gates.py       上线门禁（评测通过率 + 预算/回退告警）
  ingest.py      导入、幂等、事件落库
  api.py         REST 接口
  main.py        应用入口与静态托管
web-next/        React + TS + Vite 工作台（唯一前端）
web-next/        新版前端（React + TS + Vite）
tests/           pytest
data/            SQLite 与日志（运行时生成）
```

## 核心约束

1. **只收原始观测，不收最终价** —— 到手价由服务端算，口径才可比。
2. **缺失显式记录，绝不填 0** —— `missing_fields` 会拉低置信度并收窄结论。
3. **L3 只允许 T0/T1 数据源触发** —— 其余自动降级为 L2 并标注 `downgraded_by_tier`。
4. **换源抑制差值告警** —— `collector` 变化时只发 `source_switch`。
5. **证据闭包** —— LLM 输出的每个 `evidence_id` 必须存在于本次允许集合，否则整条作废、回退模板。
6. **AI 不做决策** —— 动作由确定性策略给出，模型只负责解释与措辞。

## 自动化与运维

**后台调度**（Celery beat，`LIRA_SCHEDULER=celery`）：

本地不带容器时，需要先起 Redis，再分别启动 worker 与 beat；Windows 上 worker 只能用 `--pool=solo`：

```bash
celery -A app.celery_app worker --loglevel=info --pool=solo
```

```bash
celery -A app.celery_app beat --loglevel=info
```

| 任务 | 频率 | 作用 |
|---|---|---|
| `inbox_scan` | 15 秒 | 扫描 `data/inbox/`，消费后移到 `processed/`，失败移到 `failed/` |
| `mapping_suggest` | 1 小时 | 为新竞品目标生成 SKU 对齐候选 |
| `outcome_review` | 15 分钟 | 找出采纳 7 天仍未回收结果的建议 |
| `digest` | 每日 09:00 | 汇总当日事件，配置 `LIRA_WEBHOOK` 时推送到群机器人 |

空转任务不写日志，避免日志表膨胀；`job_run` 只保留最近 500 条。

**文件收件箱**：把影刀导出的 CSV/JSON 丢进 `data/inbox/` 即可，
按内容哈希判重，同名同内容不会重复入库。手动扫描：`POST /api/ops/inbox-scan`。

**采集通道与风控**：

| 通道 | 实现 | tier | 说明 |
|---|---|---|---|
| `api` | 官方 / 授权接口 | T0 / T1 | 配置 `LIRA_CONNECTOR_URL` 后按任务下发 |
| `rpa` | 影刀 | T2 | 写工单到 `data/collect_outbox/`，由影刀计划任务消费 |
| `manual` | 人工文件 | T2 / T3 | 等待投递到 `data/inbox/` |

调度每 15 秒领取到期任务，顺序固定为 **熔断 → 令牌桶 → 下发**：

- 令牌桶按「通道 × 账号 × 店铺」三维；`LIRA_RL_RATE` 每秒补充、`LIRA_RL_CAPACITY` 为容量
- 连续失败达到阈值即熔断；冷却后放行一次探测，成功即闭合
- 熔断期间的任务进入人工复核队列，不会被静默丢弃
- 每次请求写入 `collect_log`：`GET /api/collect/logs`、`GET /api/collect/summary`
- 复核队列：`GET /api/collect/reviews`、`POST /api/collect/reviews/{id}/resolve?decision=released|discarded`

任务生命周期止于「下发完成」；采集结果仍通过 ingest 契约回来，按 target 与时间对齐。

## SKU 对齐

竞品链接与我方 SKU 的关系不是猜的，是算出来再人工确认的：

```
标题向量（bge-m3）余弦 × 0.75  +  价格接近度 × 0.25  → 每个竞品取 Top 3 候选
```

确认后自动把 `my_sku` / `my_price` 写回目标，价格带击穿才真正生效。
入口：UI「SKU 对齐」页，或 `POST /api/mappings/suggest` → `POST /api/mappings/{id}/decide`。

## 三方连接器与备份

**连接器**：配置 `LIRA_CONNECTOR_URL` 后，后台每 30 分钟拉取一次，
按 ingest 契约入库（`source_tier` 由数据本身决定，通常为 1）。滑动窗口限流 60 次/分钟。
也可手动触发：`POST /api/ops/run?kind=connector_sync`。

**备份**：每日 03:30 自动执行 `VACUUM INTO` 式在线备份（SQLite backup API），
同时打包 `inbox/`，默认保留 7 份。手动：`python scripts/backup.py`。

## 可观测性

每次模型调用记录到 `model_call`（kind / 模型 / 耗时 / 是否回退）。
`GET /api/metrics?hours=24` 返回调用数、回退率、P95 延迟、按任务拆分；
「系统」页直接展示 24 小时概览。

## 图像指纹

主图比对前先对 URL 做归一化：去掉 `width/quality/format/x-oss-*` 等 CDN 变换参数，
只保留决定图片内容的路径与必要参数。采集端若已提供 `main_image_hash`，优先使用它。
这样换尺寸不会误报为"主图更换"。

## 语义变化检测

除价格外，还监控**标题**与**主图**的变化（`app/semantic.py`）：

| 变化 | 判定 | 事件 |
|---|---|---|
| 标题 | 向量余弦相似度；提取新增/删除的说法 | `title_change`（相似度 <60% 记 L2，否则 L1） |
| 主图 | `main_image_url` 变化 | `image_change`（L1） |

标题差异会指出**具体改了什么**，例如"标题变化（相似度 54%）：新增 买一送一、限时"。
两侧都有数据才比较，首次采集不产生语义事件。

## 评论洞察

```
评论入库（内容哈希去重） → 领域词典分类 7 类话题 → 统计话题占比与负面占比
→ 负面集中的话题生成机会点 → 与上一次洞察对比，负面占比跃升 ≥15pt 触发 review_spike
```

- 话题：物流发货 / 质量成分 / 价格性价比 / 包装 / 客服售后 / 使用效果 / 味道气味
- 负面判定优先用评分（≤2 星），无评分时用关键词
- **负向突增**会生成 L2 事件并推送群机器人（配置 `LIRA_WEBHOOK` 时）
- 摘要由模型生成，但**只让模型选话题 + 给建议，数字由程序拼**，防止小模型编造统计

后台每 6 小时对近 7 天有评论的目标自动跑一次洞察。

## 自然语言问数

**永远不会拼 SQL**：问题只被用来选模板和填参数，SQL 全部预置、参数一律绑定。

```
问题 → 关键词匹配模板 → 正则抽参数（天数/级别/竞品名）
     → 参数校验与钳制 → 执行预置 SQL（LIMIT 50）→ 回答 + 结果表
```

内置模板（`app/nlq.py`）：

| 模板 | 示例问法 | 参数 |
|---|---|---|
| 最近降价 | 最近 7 天有哪些降价？ | days |
| 按级别查事件 | 最近的 L3 事件 | severity, days |
| 价格带击穿 | 最近有没有价格带被击穿？ | days |
| 待提交建议 | 现在有哪些待提交的建议？ | — |
| 被护栏拦截 | 哪些建议被毛利护栏拦截了？ | — |
| 已执行建议 | 最近 30 天执行了哪些建议？ | days |
| 结果回收 | 最近的结果回收怎么样？ | days |
| 竞品价格走势 | 竞品A 最近的价格走势 | target, days |
| 监控概览 | 现在监控了哪些竞品？ | — |
| 负面话题 | 竞品评论里最大的问题是什么？ | days |

安全约束：`days` 钳制在 1–180，`severity` 只接受 L1/L2/L3 枚举，竞品名只用于 `LIKE ?` 绑定，
无法匹配时返回候选问法而不是报错。界面会显示**用了哪个模板、什么参数、几行结果**，便于判断答案是否可信。

## holdout 实验

把部分竞品标记为实验组（`PATCH /api/targets/{id}` 传 `holdout: true`）：
它们**照常生成建议，但状态直接是 `holdout`**——不能提交、不进审批箱、不推送，
只观察 7 日后的真实结果。

`GET /api/experiments/holdout?days=30` 对比两组的改善率：

```
treatment（已执行） vs control（holdout 只观察）
```

样本量小时结论不可信，接口返回值里也写了这句话。

## 毛利护栏与审批

**护栏规则**：`毛利率 = (目标价 − 成本) / 目标价`，每个商品可设 `margin_floor`（默认 15%）。

| 判定 | 条件 | 后果 |
|---|---|---|
| `ok` | 毛利率 ≥ 下限 + 5pt | 正常提交 |
| `warning` | 落在下限 ~ 下限+5pt 缓冲带 | 可提交，需审批人确认 |
| `blocked` | 毛利率 < 下限 | **成员无法提交**；管理员须填写理由强制放行 |
| `unknown` | 未设置成本价 | 无法校验，须管理员确认 |

只有 `follow` / `adjust_coupon` 会改变售价、才做护栏校验；`hold` / `no_action` 不校验。
**执行时按实际执行价再校验一次**，防止审批后私自压价。

**审批链路**：

```
pending ──提交──▶ submitted ──批准──▶ approved ──执行──▶ executed
   │                  │                                  │
   └──────驳回────────┴──▶ rejected                    └─▶ 记录 7 日结果 → 沉淀案例
                      └──取消──▶ cancelled
```

- 角色：`member` 可提交/执行；`admin` / `manager` 可批准/驳回
- 开启鉴权（`LIRA_AUTH=on`）后**不能审批自己提交的建议**
- 每次流转写入 `approval_log`，详情页展示完整时间线

## 结果回收与案例沉淀

```
采纳建议 → 7 天后记录结果（改善 / 无变化 / 变差）
        → 自动生成一条案例（category=自动沉淀），进入检索库
```

这是系统唯一的学习回路：真实结果变成下次归因的依据。

## 部署

```bash
# Docker（应用 + worker + beat + PostgreSQL 16 + Redis + Qdrant；镜像内会构建新版前端）
docker compose up -d

# Windows 服务（需先安装 nssm）
.\scripts\install-service.ps1

# 备份（在线备份，不阻塞读写）
python scripts/backup.py D:\backup
```

> `data/` 不要放在 OneDrive / 坚果云同步目录，文件锁会导致 SQLite 损坏。

**Docker 实测**（2026-10-25）：多阶段构建，镜像 `ms-lira:baseline` 约 548 MB，构建约 3 分钟；
容器内验证通过健康检查、`/next` 静态前端、采集入库、Agent 研判与运行轨迹（LLM 关闭时走确定性回退）；
`data/` 通过 bind mount 持久化，容器重建后数据仍在。

> 模型连通性：Windows/macOS 的 Docker Desktop 可直接用 `host.docker.internal` 访问宿主机 Ollama。
> **Linux 服务器上 Ollama 默认只监听 127.0.0.1，容器进不去**，需以 `OLLAMA_HOST=0.0.0.0` 启动，
> 或把 compose 里的模型地址改为局域网内可访问的推理服务。

## 影刀交付包

见 [`integrations/yingdao/`](integrations/yingdao/)：字段契约、采集机要求、失败处理、上传前本地校验脚本。

## 案例库与检索

归因不是凭空写的：每次分析前先检索历史相似案例，模型只能引用检索到的案例。

**四级检索管线**（`app/cases.py`）：

```
1. 结构化预过滤   下推为 Qdrant payload 过滤（category / event_type）
2. 向量召回       Qdrant 余弦，Top 20
3. 关键词召回     FTS5 trigram / pg_trgm，Top 20
4. RRF 融合 + 重排 价格带接近、幅度接近加权 → Top 3
```

**向量存储**：Qdrant。集合按 provider 与维度隔离（`case_embeddings_<provider>_<dim>`），
避免不同 embedding 空间互相比较。生产连服务端（`LIRA_QDRANT_URL`），
本地不配时用 `data/qdrant` 目录模式，单进程可用、多进程必须起服务。

旧库的历史向量不迁移：`case` / `doc_chunk` 的 `embedding` 列在初始化时删除，
重建用 `python scripts/reindex_vectors.py`（按文本重新嵌入，provider 变化也安全）。

**Embedding 双路**：Ollama 可用时走 `bge-m3`（1024 维），不可用时自动退回
字符 n-gram 哈希向量（256 维），检索功能不中断。

案例检索结果会以 `case:<id>` 的形式进入证据链，与 `snap:` / `pp:` 一起参与证据闭包校验。

## Agent 执行与轨迹

一次研判由 LangGraph 状态机完成，按职责拆成四个 Agent：

```
加载事件 → 生成计划 → 工具调用
        → Steward  采集健康：数据过期时禁止 L3（LIRA_STEWARD_ENFORCE=on 才生效）
        → Analyst  归因：只引用工具事实，证据闭包不通过整条作废
        → Risk     毛利护栏与动作可行性
        → 校验     证据 / 动作 / 置信度 / 叙事 / 门禁
        → Writer   组装建议文案与影响区间
        → 写入建议 → 完成
```

路由是确定性的：默认全流水线，Skill 的 `stages` 可以裁掉 Steward，
不做自由路由，避免模型决定流程。

**工具层与 MCP 共用同一份契约**（[app/tools.py](app/tools.py)）：

| 工具 | 作用 |
|---|---|
| `price_history` | 竞品最近 N 天到手价序列 |
| `search_cases` | 历史相似案例检索（RAG） |
| `my_product` | 我方 SKU、成本、毛利下限 |
| `collection_health` | 采集新鲜度与各采集源滞后 |
| `simulate_price` | 模拟目标价下的毛利与护栏 |
| `get_event` | 单条事件的完整事实与证据 |

外部 Agent 可以直接连接 MCP Server：

```bash
python -m app.mcp_server
```

站内默认走同进程工具调用，少一层进程与网络开销；模型选工具默认关闭，
设置 `LIRA_AGENT_LLM_PLANNER=on` 才会让模型出计划，失败自动回退确定性计划。

每次运行写入 `agent_run` / `agent_step`。新版界面「Agent 轨迹」页可以回放：
计划、每个工具的入参/出参、校验结果、耗时与错误。建议详情里也会显示轨迹摘要。
轨迹只记录结构化步骤与工具 I/O，不记录模型自由思维过程。

## 规则文档 RAG

规则文档用 LlamaIndex 做**父子块**切分：父块约 1200 字（按小节），子块约 300 字（按句群）。
子块向量存 Qdrant 用于召回，命中后把父块内容一起返回给模型，避免切片把语义切断。
检索走「向量召回 + 关键词召回 + RRF」，命中子块以 `doc:<chunk_id>` 进入证据链。

- 切片内容与来源都可以回溯：建议详情里会列出引用规则原文
- 站内 Agent 通过 `search_docs` 工具取规则；外部 Agent 通过 MCP 拿同一个工具
- 没有规则文档时工具返回空，不阻塞研判

## Skill 注册表

每个 Skill 是声明式的，决定：触发事件类型、最低级别、分析剧本、允许调用的工具白名单、
执行阶段（`stages`）与输出 schema（`output_schema`）。

- 内置三个：大促价格试探、价格带击穿、评论异动
- 命中 Skill 后，计划只保留白名单内的工具；没有命中则用「通用研判」
- 停用某个 Skill 会立即回退到通用研判
- Skill 版本随每次修改递增，运行轨迹里记录本次使用的 `skill_id`

## LLM Critic

默认关闭。设置 `LIRA_AGENT_LLM_CRITIC=on` 后，校验节点会多一道模型复核：

```
确定性校验 → LLM 复核 → 驳回则回退模板 → 再校验
```

Critic 只能驳回或放行，不能改动作、不能绕过证据闭包；失败时自动跳过，不影响主流程。
轨迹里会记录 `critic` 与 `fallback` 两步。

## 评测金标集

内置 5 条金标：L3 降价、L2 降价、提价、价格带击穿、低置信观察。
每条用例在独立目标上跑完整链路，比对：

- 事件类型是否命中
- 动作是否与金标一致
- 证据链是否非空
- 耗时与护栏状态

评测结束后自动删除本次产生的目标、事件、建议、运行与快照，不污染生产数据。
开启模型时一次评测约数十秒；模型关闭时会走确定性回退，适合 CI。

## 执行联动

建议批准后，执行走 `app/executor.py` 的适配器：

| 模式 | 行为 |
|---|---|
| `off` | 只写执行记录，标记已执行，不调外部 |
| `preview` | 计算并记录执行计划，不写外部 |
| `webhook` | POST 执行计划到 `LIRA_EXECUTOR_URL`，记录外部 ID |

约束：

- 执行前重新校验状态与毛利护栏；拦截至上价必须由管理员操作
- 幂等键为 `建议ID:目标价:模式`，重复执行返回同一条记录
- 每次执行都有请求、响应、操作者与时间
- `webhook` 模式可配置回滚地址；回滚后建议回到 `approved`

## 结果回收

执行或采纳 7 天后进入待回收列表：

- 展示执行的 SKU、执行价、到期时间与逾期天数
- 附带**观察到的竞品价格变化**（执行时 → 7 天后），只作参考，不自动判定成败
- 人工记录改善/无变化/变差后自动沉淀案例
- 调度器每 15 分钟检查一次，群机器人提醒按 20 小时去重

## 成本与预算

- 每次模型调用记录 prompt/completion token 与成本（成本系数可配，本地模型默认为 0）
- `agent_run` 汇总本次运行的 token 与成本，轨迹页可见
- `LIRA_DAILY_TOKEN_BUDGET` 限制 24 小时 token 用量；用尽后模型调用回退模板
- 系统页展示 24 小时 token、成本与预算占比

## 上线门禁

门禁以最近一次评测批次为准：

```
最近评测通过率 >= LIRA_GATE_MIN_ACCURACY
```

- `LIRA_GATE_ENFORCE=on` 时，门禁未通过会拦截新的研判（HTTP 423）
- 回退率过高、token 预算用尽会作为告警展示，不单独阻断
- 评测页展示门禁状态、阈值、最近评测与用量

## 主要接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/v1/ingest/snapshots` | 批量导入（JSON） |
| POST | `/v1/ingest/validate` | JSON 干跑校验（不落库） |
| POST | `/v1/import/csv` | CSV 导入 |
| POST | `/v1/import/validate` | CSV 干跑校验 |
| GET | `/api/events` | 事件列表（可 `?severity=L3`） |
| GET | `/api/events/{id}` | 事件详情 + 最新建议 |
| POST | `/api/events/{id}/analyze` | 执行一次 Agent 研判并生成建议 |
| GET | `/api/agent/runs` | Agent 运行列表（可按 `event_id` 过滤） |
| GET | `/api/agent/runs/{id}` | 运行详情：计划、每步输入输出、耗时、错误 |
| GET/POST | `/api/docs` | 规则文档列表 / 入库（自动切片与向量化） |
| GET | `/api/docs/{id}` | 文档详情与切片 |
| GET | `/api/doc-chunks/{id}` | 单个切片，可用于证据回溯 |
| GET/POST | `/api/skills` | Skill 列表 / 新建 |
| PATCH | `/api/skills/{id}` | 启停、改剧本或工具白名单 |
| GET | `/api/eval/cases` | 金标用例 |
| POST | `/api/eval/run` | 跑一遍评测（临时数据自动清理，结果落库） |
| GET | `/api/suggestions/{id}/execution-preview` | 执行预览：SKU、价格、毛利、模式 |
| GET | `/api/suggestions/{id}/executions` | 执行历史 |
| POST | `/api/executions/{id}/rollback` | 回滚执行（外部模式下先调回滚地址） |
| GET | `/api/outcomes/due` | 7 日结果待回收列表（含观察到的竞品价格变化） |
| GET | `/api/gates` | 上线门禁状态、阈值、最近评测与用量 |
| GET | `/api/targets` | 监控目标 |
| PATCH | `/api/targets/{id}` | 设置我方 SKU / 价格 |
| GET | `/api/targets/{id}/prices` | 价格序列 |
| POST | `/api/suggestions/{id}/decide` | 采纳 / 不采纳 |
| GET | `/api/cases` | 案例列表 |
| POST | `/api/cases` | 新增案例（自动向量化） |
| POST | `/api/cases/seed` | 载入示例案例 |
| GET | `/api/cases/search` | 检索相似案例 |
| POST | `/api/reviews` | 评论批量入库 |
| GET | `/api/reviews` | 评论列表 |
| POST | `/api/reviews/seed` | 载入示例评论 |
| POST | `/api/targets/{id}/insights` | 生成评论洞察 |
| GET | `/api/targets/{id}/insights` | 最新洞察 |
| GET | `/api/ask/templates` | 问数模板列表 |
| POST | `/api/ask` | 自然语言提问 |
| GET | `/api/metrics` | 模型调用指标 |
| GET | `/api/experiments/holdout` | holdout 对比 |
| POST | `/api/users/{name}/password` | 修改密码 |
| PATCH | `/api/users/{name}` | 调整角色 |
| GET/POST | `/api/my-products` | 我方商品库 |
| POST | `/api/my-products/seed` | 载入示例商品 |
| GET | `/api/mappings` | 对齐候选/已确认（`?status=`） |
| POST | `/api/mappings/suggest` | 生成对齐候选 |
| POST | `/api/mappings/{id}/decide` | 确认 / 忽略对齐 |
| POST | `/api/suggestions/{id}/submit` | 提交执行 |
| POST | `/api/suggestions/{id}/approve` | 批准 |
| POST | `/api/suggestions/{id}/reject` | 驳回 |
| POST | `/api/suggestions/{id}/execute` | 标记已执行（记录执行价） |
| POST | `/api/suggestions/{id}/cancel` | 取消 |
| GET | `/api/suggestions/{id}/timeline` | 审批记录 |
| GET | `/api/approvals/inbox` | 待审批列表 |
| POST | `/api/suggestions/{id}/outcome` | 记录 7 日结果 |
| GET | `/api/suggestions/{id}/outcome` | 查询结果 |
| GET | `/api/outcomes/overdue` | 超期未回收 |
| POST | `/api/login` · `/api/logout` | 登录 / 登出 |
| GET | `/api/me` | 当前操作者 |
| GET/POST | `/api/users` | 账号列表 / 创建 |
| GET | `/api/ops` | 调度、收件箱、鉴权状态 |
| POST | `/api/ops/run` | 手动触发任务（`?kind=`） |
| POST | `/api/ops/inbox-scan` | 立即扫描收件箱 |
| GET | `/api/health` | 健康检查（含数据新鲜度） |
| GET | `/api/freshness` | 最新快照时间与滞后小时数 |
| GET | `/api/stream` | SSE：事件 / 建议审批 / 采集入库推送 |
| GET | `/login` | 独立登录页（鉴权开启时未登录访问 `/` 会跳转到这里） |

交互式文档：http://127.0.0.1:8010/docs

## CSV 列

```
target_id, ts, collector, source_tier, list_price,
coupons, promotions, coin_rate, coin_cap,
member_price, live_price, account_tier, title
```

- 空单元格 = 未知（不是 0）
- `coupons` / `promotions` 填 JSON 数组，例如
  `[{"kind":"shop","threshold":299,"discount":30}]`

## 测试

```bash
python -m pytest -q
```

```bash
# PostgreSQL 回归（需先 docker compose up -d db）
LIRA_TEST_DB=postgres python -m pytest -q
```

## 双后端 SQL 约定

- 业务 SQL 统一用 `?` 占位符，以及 `datetime(col)` / `datetime('now', ?)` 写法。
- 由 `app/db.py` 的方言层转换为 PostgreSQL 的 `%s` 与 `::timestamptz`；不要在手写 SQL 里直接用 `%s`。
- 新增方言差异时，先补 `tests/test_migrate.py` 的翻译测试，再改业务代码。

## 界面

两套前端并存，可按需灰度：

| 入口 | 技术 | 定位 |
|---|---|---|
| `/next` | React + TS + Vite | 唯一前端入口 |
| `/next` | React + TS + Vite | 新版工作台，四模块 IA |

新版构建后由 Python 服务自动挂载 `web-next/dist`；未构建时 `/next` 返回 503 提示。

新版信息架构（四模块）：

```
监控任务管理：任务配置（选目标 · 通道 · 频率 · 优先级，可停止）
              数据导入、采集源健康度、失败文件、最近任务
数据看板：    总览（待决策 / L3 / 新鲜度 / 采集源）
              价格趋势（竞品到手价区间 + 我方价格线）
              最新事件、竞品 360、案例库
预警中心：    预警事件（按级别与类型筛选：价格 / 标题主图 / 差评突增 / 换源）
              处置建议 → 详情（毛利护栏 · 执行预览/记录 · 审批时间线 · 7 日结果）
              审批（角色感知）、结果回收
系统设置：    采集日志（请求明细 · 异常类型 · 人工复核队列）
              Agent 轨迹 → 轨迹详情（计划 · 工具 I/O · 校验 · 耗时）
              规则库、问数、Skill 管理、评测、账号
```

鉴权开启后，新版登录页是独立路由 `/next/login`，由前端守卫跳转；API 仍由服务端中间件默认拒绝。
`/login` 由服务端 303 重定向到 `/next/login`。

窄屏（<900px）侧栏自动收成图标栏，新版详情页在 1180px 以下自动改为单列。

## 已知限制（刻意的）

- 主图只做 URL 归一化 + 采集端哈希，不做像素级感知哈希（需要下载图片）
- 评论话题依赖词典，未做语义聚类；新词需要补词典
- 不做自动调价；holdout 已有，但样本量小时结论不可信
- 单租户；上传按整文件读入内存（未做流式）
- 前端只保留 `web-next`，旧版已删除
- MCP SDK 锁定 1.x；升级 2.x 需要把 `FastMCP` 迁移到 `MCPServer`
- 关键词召回按后端分流：SQLite 用 FTS5 trigram，PostgreSQL 用 pg_trgm + ILIKE
- SSE 走进程内广播，只支持单进程；多 worker 需换 Redis pub/sub
- 登录为独立页面 + 服务端守卫；角色化 UI 已在菜单与审批按钮生效，账号管理暂只有接口
- 向量已迁到 Qdrant；模型级 reranker 需自备服务，未配置时走规则重排
- TLS 需外置反向代理（Caddy/Nginx），应用本身只监听 HTTP
- 4B 模型的叙事质量一般，事实与数字仍由工具保证

## 评测与模型网关（P5–P10）

### 评测

```bash
python scripts/gen_golden_cases.py          # 生成 120 条金标
python scripts/eval_gate.py --tier smoke    # PR 门禁（确定性，~5s）
python scripts/eval_gate.py --tier full     # 全量（~16s）
```

- 金标：`app/evaluation/golden/agent_cases.jsonl`，五个场景（价格事件 / 护栏 / 注入对抗 / 低置信 / SOP 边界）。
- 指标：动作准确率、证据闭包率、轨迹完整率；按 segment / difficulty 切片。
- 坏例自动归档到 `eval_badcase`，接口 `GET /api/eval/badcases`。
- 评测默认关闭模型（确定性），需要模型参与时传 `use_llm=True`。

### 多 Provider 网关

```bash
export LIRA_LLM_BACKEND=gateway          # legacy（默认）| gateway
export LIRA_OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export LIRA_OPENAI_API_KEY=sk-xxx
export LIRA_OPENAI_MODEL=qwen-plus
export LIRA_LLM_ROUTE=auto               # auto | ollama | openai
export LIRA_LLM_RPM=60
```

按任务类型路由，失败自动降级（退避 + 熔断 + 每请求限流），全部不可用时回落模板。
调用记录写入 `model_call`，含 provider / prompt 版本 / token / 成本。

### Agent 能力

- 有界 ReAct：`LIRA_AGENT_LOOP=on`（默认），上限 `LIRA_AGENT_MAX_STEPS` / `LIRA_AGENT_MAX_SECONDS`。
- 记忆：`agent_memory` 表，会话级 + 长期级，召回注入 facts。
- 多 Agent 交接：`agent_step.kind='handoff'`，每次运行最多 2 次。
- SOP 校验：`POST /api/skills/{id}/validate`。

### 安全与可观测

- 注入隔离：外部内容包 `<untrusted>`，上下文被污染时只保留只读工具（`LIRA_TAINT_ENFORCE=on`）。
- PII 脱敏：手机号 / 身份证 / 银行卡 / 邮箱 / 地址，出站与日志均生效。
- 审批分级：`GET /api/suggestions/{id}/risk`；`LIRA_HITL_STRICT=on` 时高风险动作需 admin。
- 追踪：`GET /api/observability/traces`、`/{trace_id}`，前端「观测」页可视化 span 树。
