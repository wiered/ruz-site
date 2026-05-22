"""Homepage routes."""

import logging

from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from ruzsite.logging_config import setup_logging
from ruzsite.services.homepage_service import build_page, session_state

setup_logging()
logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def homepage(request: Request) -> HTMLResponse:
    """Render the homepage."""
    logger.debug("Rendering homepage")
    return HTMLResponse(build_page(await session_state(request)))


@router.get("/login")
async def login_page() -> RedirectResponse:
    """Redirect login requests to the homepage."""
    return RedirectResponse(url="/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
