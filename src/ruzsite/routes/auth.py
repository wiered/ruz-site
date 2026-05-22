"""Authentication routes."""

import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ruzsite.logging_config import setup_logging
from ruzsite.schemas.auth import SessionData
from ruzsite.services.auth_service import (
    SESSION_COOKIE_NAME,
    encode_session,
    extract_init_data,
    validate_same_origin,
    verify_telegram_init_data,
)
from ruzsite.services.rate_limit_service import enforce_rate_limit, get_client_ip
from ruzsite.settings import get_settings

setup_logging()
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth")
settings = get_settings()


@router.post("/telegram")
async def telegram_auth(request: Request) -> JSONResponse:
    """Verify Telegram Mini App init data and create a signed app session."""
    validate_same_origin(request)
    client_ip = get_client_ip(request)
    await enforce_rate_limit(
        scope="auth:ip",
        subject=client_ip,
        limit=settings.auth_ip_rate_limit,
        window_seconds=settings.auth_ip_rate_window_seconds,
        detail="Too many Telegram auth attempts from this IP address.",
    )
    init_data = await extract_init_data(request)
    telegram_user = verify_telegram_init_data(
        init_data,
        bot_token=settings.telegram_bot_token,
        max_age_seconds=settings.telegram_auth_max_age_seconds,
    )
    await enforce_rate_limit(
        scope="auth:user",
        subject=str(telegram_user.id),
        limit=settings.auth_user_rate_limit,
        window_seconds=settings.auth_user_rate_window_seconds,
        detail="Too many Telegram auth attempts for this Telegram user.",
    )
    logger.info("Telegram auth verified for user ID %s", telegram_user.id)
    session = SessionData(
        telegram_user_id=telegram_user.id,
        first_name=telegram_user.first_name,
        last_name=telegram_user.last_name,
        username=telegram_user.username,
        language_code=telegram_user.language_code,
        issued_at=int(time.time()),
    )
    response = JSONResponse(
        {
            "ok": True,
            "telegram_user_id": telegram_user.id,
            "username": telegram_user.username,
        }
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=encode_session(session, secret=settings.session_secret),
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    logger.debug("Issued session cookie for Telegram user ID %s", telegram_user.id)
    return response


@router.post("/logout")
async def logout() -> RedirectResponse:
    """Clear the signed app session."""
    logger.info("Clearing session cookie")
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return response
