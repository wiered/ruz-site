"""Schedule routes."""

import logging

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

from ruzsite.logging_config import setup_logging
from ruzsite.services.schedule_service import build_page, schedule_state

setup_logging()
logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/schedule", response_class=HTMLResponse, response_model=None)
async def schedule_page(request: Request) -> Response:
    """Render the authenticated user's schedule page."""
    try:
        state = await schedule_state(request)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_307_TEMPORARY_REDIRECT:
            return RedirectResponse(
                url=(exc.headers or {}).get("Location", "/"),
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            )
        raise

    logger.debug("Rendering schedule page")
    return HTMLResponse(build_page(state))
