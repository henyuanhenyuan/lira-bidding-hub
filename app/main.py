from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from . import auth, config, db, scheduler, settings_store
from .api import router


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings_store.apply()
    db.init_db()
    with db.get_db() as conn:
        auth.ensure_accounts(conn)
    scheduler.scheduler.start()
    try:
        yield
    finally:
        scheduler.scheduler.stop()


app = FastAPI(title="Lira 电商 · 竞品情报 Agent", version="0.3.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)


class ImmutableStaticFiles(StaticFiles):
    """Vite 产物带内容哈希，可以长期强缓存。"""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            response.headers.setdefault(
                "Cache-Control", "public, max-age=31536000, immutable"
            )
        return response

# 默认拒绝：鉴权开启时，除登录/健康检查/静态资源外一律先验身份。
PUBLIC_PATHS = {
    "/", "/login", "/next", "/api/login", "/api/logout", "/api/health", "/favicon.ico",
}
PUBLIC_PREFIXES = ("/next/",)


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    if auth.AUTH_ENABLED:
        path = request.url.path
        if path not in PUBLIC_PATHS and not path.startswith(PUBLIC_PREFIXES):
            if not auth.verify_token(request.cookies.get(auth.COOKIE)):
                ingest = path.startswith(("/v1/ingest", "/v1/import"))
                if not (ingest and auth.bearer_matches(request)):
                    return JSONResponse({"detail": "login required"}, status_code=401)
    return await call_next(request)


app.include_router(router)

if (config.NEXT_DIR / "assets").exists():
    app.mount(
        "/next/assets",
        ImmutableStaticFiles(directory=config.NEXT_DIR / "assets"),
        name="next-assets",
    )


FALLBACK = """<!doctype html><meta charset="utf-8">
<title>电商竞品情报 Agent</title>
<body style="font-family:system-ui;padding:40px;max-width:640px">
<h2>服务已启动</h2>
<p>前端构建产物缺失，API 可用。</p>
<ul>
  <li><a href="/docs">/docs</a> — API 文档</li>
  <li><a href="/api/health">/api/health</a> — 健康检查</li>
  <li><a href="/api/events">/api/events</a> — 事件列表</li>
</ul>
</body>"""


@app.get("/login", response_class=HTMLResponse)
def login_page() -> Response:
    """登录页由 React 工作台提供。"""
    return RedirectResponse("/next/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> Response:
    if auth.AUTH_ENABLED and not auth.verify_token(request.cookies.get(auth.COOKIE)):
        return RedirectResponse("/next/login", status_code=303)
    if (config.NEXT_DIR / "index.html").exists():
        return RedirectResponse("/next", status_code=303)
    return HTMLResponse(FALLBACK)


@app.get("/next", response_class=HTMLResponse)
@app.get("/next/{path:path}", response_class=HTMLResponse)
def next_app(path: str = "") -> Response:
    """React 工作台。静态资源由 /next/assets 提供，其余路径回落到 SPA。"""
    index = config.NEXT_DIR / "index.html"
    if index.exists():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return HTMLResponse(
        "<h2>前端尚未构建</h2><p>cd web-next && npm install && npm run build</p>",
        status_code=503,
    )


@app.get("/favicon.ico")
def favicon() -> Response:
    icon = config.NEXT_DIR / "favicon.ico"
    if icon.exists():
        return FileResponse(icon)
    return HTMLResponse("", status_code=204)
