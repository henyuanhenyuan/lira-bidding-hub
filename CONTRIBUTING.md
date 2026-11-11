# 参与贡献

## 本地运行

```bash
docker compose up -d db        # PostgreSQL 16 + pgvector，127.0.0.1:5432
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

前端：

```bash
cd web-next && npm install && npm run build   # 产物由后端在 /next 提供
```

## 提交前自检

```bash
pytest -q
ruff check --select E9,F63,F7,F82 app tests
```

测试依赖 PostgreSQL + pgvector，请先启动 `docker compose up -d db`。CI 会额外跑评测冒烟门禁。

## 提 PR

- 一个 PR 只做一件事，说明改动动机与验证方式。
- 新增行为请补测试；修复缺陷先写能复现问题的用例。
- 遵循仓库现有代码风格与目录结构，不引入新的框架层。
- 改动运行态或文档口径时，同步更新 `README.md` 与 `HANDOFF.md`。

## 提交信息

采用 `feat:` / `fix:` / `docs:` / `chore:` 前缀，正文说明「为什么」而非「做了什么」。
