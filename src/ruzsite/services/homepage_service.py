"""Homepage services."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path

from fastapi import HTTPException, Request, status
from fastapi.templating import Jinja2Templates
from ruzclient import ClientConfig, RuzClient
from ruzclient.errors import RuzAuthError, RuzClientError, RuzHttpError

from ruzsite.logging_config import setup_logging
from ruzsite.schemas.auth import TelegramUser
from ruzsite.schemas.homepage import HomepageState
from ruzsite.services.auth_service import SESSION_COOKIE_NAME, decode_session
from ruzsite.settings import ROOT, get_settings

setup_logging()
logger = logging.getLogger(__name__)
settings = get_settings()
templates = Jinja2Templates(directory=Path(ROOT, "src", "ruzsite", "templates"))


async def load_ruz_user(user_id: int) -> Mapping[str, object] | None:
    """Fetch the Ruz user for the authenticated Telegram user."""
    logger.debug("Loading Ruz user by Telegram user ID %s", user_id)
    config = ClientConfig(base_url=settings.api_url, api_key=settings.api_key)
    try:
        async with RuzClient(config=config) as client:
            ruz_user = await client.users.get_by_id(user_id=user_id)
            logger.info("Loaded Ruz user for Telegram user ID %s", user_id)
            return ruz_user
    except RuzHttpError as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            logger.info("No Ruz user found for Telegram user ID %s", user_id)
            return None
        logger.exception("Ruz API error while loading user ID %s", user_id)
        raise


def build_page(state: HomepageState) -> str:
    """Render the homepage template."""
    return templates.get_template("homepage.html").render(
        authenticated=state.authenticated,
        state=state,
    )


async def session_state(request: Request) -> HomepageState:
    """Build homepage state from the current session."""
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie_value:
        logger.debug("Homepage request has no session cookie")
        return HomepageState(authenticated=False, telegram_user=None, ruz_user=None)

    try:
        session_data = decode_session(
            cookie_value,
            secret=settings.session_secret,
            max_age_seconds=settings.session_max_age_seconds,
        )
    except HTTPException:
        logger.warning("Rejected invalid or expired session cookie")
        return HomepageState(
            authenticated=False,
            telegram_user=None,
            ruz_user=None,
            error_message="Your session is invalid or expired. Re-open the Mini App from Telegram.",
        )

    logger.debug(
        "Session cookie accepted for Telegram user ID %s",
        session_data.telegram_user_id,
    )
    telegram_user = TelegramUser(
        id=session_data.telegram_user_id,
        first_name=session_data.first_name,
        last_name=session_data.last_name,
        username=session_data.username,
        language_code=session_data.language_code,
    )
    try:
        ruz_user = await load_ruz_user(session_data.telegram_user_id)
    except RuzAuthError:
        logger.exception(
            "Ruz API authorization failed for Telegram user ID %s", telegram_user.id
        )
        return HomepageState(
            authenticated=True,
            telegram_user=telegram_user,
            ruz_user=None,
            error_message="Ruz API authorization failed. Check the server API key.",
        )
    except RuzClientError as exc:
        logger.exception(
            "Failed to load Ruz user for Telegram user ID %s", telegram_user.id
        )
        return HomepageState(
            authenticated=True,
            telegram_user=telegram_user,
            ruz_user=None,
            error_message=f"Could not load Ruz user: {exc}",
        )

    return HomepageState(
        authenticated=True,
        telegram_user=telegram_user,
        ruz_user=ruz_user,
    )
