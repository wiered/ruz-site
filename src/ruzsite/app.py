"""Application module."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from ruzsite.logging_config import setup_logging
from ruzsite.routes.auth import router as auth_router
from ruzsite.routes.health import router as health_router
from ruzsite.routes.homepage import router as homepage_router
from ruzsite.routes.schedule import router as schedule_router
from ruzsite.services.redis_service import close_redis
from ruzsite.settings import ROOT, get_settings

setup_logging()
get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Close shared resources when the app shuts down."""
    yield
    await close_redis()


app = FastAPI(lifespan=lifespan)
settings = get_settings()

app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))


@app.middleware("http")
async def apply_security_headers(request, call_next) -> Response:
    """Attach baseline security headers to every response."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "frame-ancestors 'none'; base-uri 'self'; object-src 'none'",
    )
    if settings.cookie_secure:
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    return response


app.mount(
    "/static",
    StaticFiles(directory=Path(ROOT, "src", "ruzsite", "static")),
    name="static",
)
app.include_router(health_router)
app.include_router(homepage_router)
app.include_router(auth_router)
app.include_router(schedule_router)
