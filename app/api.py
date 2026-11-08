"""路由聚合：各领域路由在 app/routers/ 下。"""

from __future__ import annotations

from fastapi import APIRouter

from .routers import ingest
from .routers import targets
from .routers import products
from .routers import events
from .routers import cases
from .routers import docs
from .routers import skills
from .routers import evaluation
from .routers import suggestions
from .routers import auth_users
from .routers import collect
from .routers import ops
from .routers import stream

router = APIRouter()
for sub in (
    ingest.router,
    targets.router,
    products.router,
    events.router,
    cases.router,
    docs.router,
    skills.router,
    evaluation.router,
    suggestions.router,
    auth_users.router,
    collect.router,
    ops.router,
    stream.router,
):
    router.include_router(sub)
