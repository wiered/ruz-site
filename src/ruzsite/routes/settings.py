"""Settings routes."""

import logging

from fastapi import APIRouter, Form, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

from ruzsite.logging_config import setup_logging
from ruzsite.services.auth_service import validate_same_origin_or_referer
from ruzsite.services.settings_service import (
    build_page,
    change_group,
    change_subgroup,
    settings_state,
)

setup_logging()
logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/settings", response_class=HTMLResponse, response_model=None)
async def settings_page(
    request: Request,
    q: str = Query(default="", alias="q"),
) -> Response:
    """Render the authenticated user's settings page."""
    try:
        state = await settings_state(request, group_query=q)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_307_TEMPORARY_REDIRECT:
            return RedirectResponse(
                url=(exc.headers or {}).get("Location", "/"),
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            )
        raise

    logger.debug("Rendering settings page")
    return HTMLResponse(build_page(state))


@router.post("/settings/group", response_class=HTMLResponse, response_model=None)
async def update_group(
    request: Request,
    group_oid: int = Form(...),
    group_label: str = Form(...),
) -> Response:
    """Update the authenticated user's group selection."""
    validate_same_origin_or_referer(request)
    try:
        state = await change_group(
            request,
            group_oid=group_oid,
            group_label=group_label,
        )
    except HTTPException as exc:
        if exc.status_code == status.HTTP_307_TEMPORARY_REDIRECT:
            return RedirectResponse(
                url=(exc.headers or {}).get("Location", "/"),
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            )
        raise

    logger.debug("Rendering settings page after group update")
    return HTMLResponse(build_page(state))


@router.post("/settings/subgroup", response_class=HTMLResponse, response_model=None)
async def update_subgroup(
    request: Request,
    subgroup: int = Form(...),
) -> Response:
    """Update the authenticated user's subgroup selection."""
    validate_same_origin_or_referer(request)
    try:
        state = await change_subgroup(request, subgroup=subgroup)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_307_TEMPORARY_REDIRECT:
            return RedirectResponse(
                url=(exc.headers or {}).get("Location", "/"),
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            )
        raise

    logger.debug("Rendering settings page after subgroup update")
    return HTMLResponse(build_page(state))
