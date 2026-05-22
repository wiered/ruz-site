"""App module."""

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse


app = FastAPI()

from ruzclient import RuzClient, ClientConfig
from ruzsite.settings import get_settings

settings = get_settings()


@app.get("/", response_class=PlainTextResponse)
async def homepage() -> str:
    """Homepage."""
    return "Homepage"
