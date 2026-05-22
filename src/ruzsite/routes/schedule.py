"""Schedule routes."""

import logging
from collections.abc import Mapping

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

from ruzsite.logging_config import setup_logging
from ruzsite.services.schedule_service import build_page, schedule_state

setup_logging()
logger = logging.getLogger(__name__)
router = APIRouter()


def _detect_request_platform(request: Request) -> str:
    """Infer the request platform from Telegram params, client hints, or UA."""
    query_platform = request.query_params.get("tgWebAppPlatform")
    if query_platform:
        return query_platform

    header_platform = request.headers.get("sec-ch-ua-platform")
    if header_platform:
        return header_platform.strip('"')

    user_agent = request.headers.get("user-agent", "").lower()
    platform_markers: Mapping[str, tuple[str, ...]] = {
        "tdesktop": ("telegramdesktop", "tdesktop", "telegram desktop"),
        "macos": ("macintosh", "mac os", "macos"),
        "ios": ("iphone", "ipad", "ios"),
        "android": ("android",),
        "windows": ("windows", "win64", "win32"),
        "linux": ("linux", "x11"),
    }
    for platform_name, markers in platform_markers.items():
        if any(marker in user_agent for marker in markers):
            return platform_name

    return "unknown"


@router.get("/schedule", response_class=HTMLResponse, response_model=None)
async def schedule_page(request: Request) -> Response:
    """Render the authenticated user's schedule page."""
    logger.info(
        "Schedule request platform=%s tg_platform=%s sec_ch_ua_platform=%s user_agent=%s",
        _detect_request_platform(request),
        request.query_params.get("tgWebAppPlatform"),
        request.headers.get("sec-ch-ua-platform"),
        request.headers.get("user-agent"),
    )
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
