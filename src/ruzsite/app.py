"""Application module."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ruzsite.logging_config import setup_logging
from ruzsite.routes.auth import router as auth_router
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
app.mount(
    "/static",
    StaticFiles(directory=Path(ROOT, "src", "ruzsite", "static")),
    name="static",
)
app.include_router(homepage_router)
app.include_router(auth_router)
app.include_router(schedule_router)
