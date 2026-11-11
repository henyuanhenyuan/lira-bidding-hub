# 安全策略

## 报告漏洞

请通过仓库 **Security → Report a vulnerability** 私下提交，不要开公开 issue。
收到后会尽快确认，并在修复完成后与你协商披露时间。

## 部署注意

- `app/auth.py` 内置 5 个演示账号，密码可用 `LIRA_SEED_<用户名大写>_PASSWORD` 覆盖，
  生产部署务必替换默认值。
- `.env` 已被忽略；数据库口令、模型 API Key、`LIRA_INGEST_TOKEN` 只通过环境变量注入。
- 生产环境请置于 HTTPS 之后，并设置 `LIRA_COOKIE_SECURE=on`。
- 采集写入接口使用独立 Bearer 令牌，不要复用登录凭据。
