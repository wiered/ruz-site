"""Settings services."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import HTTPException, Request, status
from fastapi.templating import Jinja2Templates
from ruzclient import ClientConfig, RuzClient, UserCreate, UserUpdate
from ruzclient.errors import RuzAuthError, RuzClientError, RuzHttpError
from ruzclient.http.endpoints.groups import GroupRead, GroupSearchHit
from ruzclient.http.endpoints.users import UserRead

from ruzsite.logging_config import setup_logging
from ruzsite.schemas.auth import SessionData
from ruzsite.schemas.settings import GroupSearchResult, SettingsPageState
from ruzsite.services.auth_service import SESSION_COOKIE_NAME, decode_session
from ruzsite.services.homepage_service import load_ruz_user
from ruzsite.services.rate_limit_service import (
    enforce_rate_limit,
    get_client_ip,
    invalidate_cached_schedule,
)
from ruzsite.settings import ROOT, get_settings

setup_logging()
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory=Path(ROOT, "src", "ruzsite", "templates"))


def _validate_group_query(normalized_query: str) -> str | None:
    """Validate a search query before sending it to the upstream API."""
    settings = get_settings()
    if len(normalized_query) < settings.settings_search_query_min_length:
        return (
            "Enter at least "
            f"{settings.settings_search_query_min_length} characters to search."
        )
    if len(normalized_query) > settings.settings_search_query_max_length:
        return (
            "Search query is too long. Use at most "
            f"{settings.settings_search_query_max_length} characters."
        )
    return None


@asynccontextmanager
async def _ruz_client():
    """Create a short-lived Ruz client for settings operations."""
    settings = get_settings()
    config = ClientConfig(base_url=settings.api_url, api_key=settings.api_key)
    async with RuzClient(config=config) as client:
        yield client


def _normalize_optional_str(value: object) -> str | None:
    """Normalize optional string-like values to a meaningful string or None."""
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _group_hit_for_oid(
    groups: list[GroupSearchHit],
    group_oid: int,
) -> GroupSearchHit | None:
    """Pick the search hit matching the chosen group OID."""
    for group in groups:
        if group["oid"] == group_oid:
            return group
    return None


async def _fetch_group(client: RuzClient, group_oid: int) -> GroupRead | None:
    """Read a full group record by OID, tolerating missing groups."""
    try:
        return await client.groups.get_group(group_oid)
    except (RuzHttpError, ValueError) as exc:
        if (
            isinstance(exc, RuzHttpError)
            and exc.status_code != status.HTTP_404_NOT_FOUND
        ):
            raise
        logger.info("Group OID %s could not be fetched directly", group_oid)
        return None


async def _fetch_user(client: RuzClient, user_id: int) -> UserRead | None:
    """Read a user record, returning None when it does not exist."""
    try:
        return await client.users.get_by_id(user_id)
    except RuzHttpError as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            return None
        raise


def _build_group_results(groups: list[GroupSearchHit]) -> list[GroupSearchResult]:
    """Convert raw group search hits into template state."""
    return [
        GroupSearchResult(
            oid=group["oid"],
            name=group["name"],
            guid=group["guid"],
            faculty_name=group.get("faculty_name"),
        )
        for group in groups
    ]


async def _resolve_current_group_name(
    ruz_user: Mapping[str, object] | None,
) -> str | None:
    """Resolve the current group name, fetching it from RUZ when needed."""
    if ruz_user is None:
        return None

    group_oid_raw = ruz_user.get("group_oid")
    group_oid = group_oid_raw if isinstance(group_oid_raw, int) else None
    group_name = _normalize_optional_str(ruz_user.get("group_name"))
    if group_name is not None or group_oid is None:
        return group_name

    try:
        async with _ruz_client() as client:
            group = await _fetch_group(client, group_oid)
    except (RuzAuthError, RuzClientError, RuzHttpError):
        logger.warning(
            "Failed to resolve current group name for group OID %s",
            group_oid,
            exc_info=True,
        )
        return f"Group #{group_oid}"

    return (
        _normalize_optional_str(group.get("name") if group else None)
        or f"Group #{group_oid}"
    )


async def _base_settings_state(
    *,
    ruz_user: Mapping[str, object] | None,
    group_query: str = "",
    group_results: list[GroupSearchResult] | None = None,
    error_message: str | None = None,
    success_message: str | None = None,
) -> SettingsPageState:
    """Create a page state with current user group metadata."""
    current_group_oid_raw = None if ruz_user is None else ruz_user.get("group_oid")
    current_group_oid = (
        current_group_oid_raw if isinstance(current_group_oid_raw, int) else None
    )
    current_subgroup_raw = None if ruz_user is None else ruz_user.get("subgroup")
    current_subgroup = (
        current_subgroup_raw if isinstance(current_subgroup_raw, int) else None
    )
    current_group_name = await _resolve_current_group_name(ruz_user)
    return SettingsPageState(
        authenticated=True,
        current_group_oid=current_group_oid,
        current_group_name=current_group_name,
        current_subgroup=current_subgroup,
        group_query=group_query,
        group_results=[] if group_results is None else group_results,
        error_message=error_message,
        success_message=success_message,
    )


def build_page(state: SettingsPageState) -> str:
    """Render the settings page template."""
    return templates.get_template("settings.html").render(
        authenticated=state.authenticated,
        state=state,
        current_page="settings",
    )


def _decode_session_from_request(request: Request) -> SessionData:
    """Return a verified session or raise a redirect-style HTTPException."""
    settings = get_settings()
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie_value:
        logger.debug("Settings request has no session cookie")
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/"},
        )

    try:
        return decode_session(
            cookie_value,
            secret=settings.session_secret,
            max_age_seconds=settings.session_max_age_seconds,
        )
    except HTTPException as exc:
        logger.warning("Rejected invalid or expired settings session cookie")
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/"},
        ) from exc


async def settings_state(
    request: Request,
    *,
    group_query: str = "",
    success_message: str | None = None,
) -> SettingsPageState:
    """Build settings page state from the current session and optional search."""
    session_data = _decode_session_from_request(request)
    ruz_user = await load_ruz_user(session_data.telegram_user_id)
    normalized_query = group_query.strip()
    if not normalized_query:
        return await _base_settings_state(
            ruz_user=ruz_user,
            success_message=success_message,
        )

    query_error = _validate_group_query(normalized_query)
    if query_error is not None:
        return await _base_settings_state(
            ruz_user=ruz_user,
            group_query=normalized_query,
            error_message=query_error,
            success_message=success_message,
        )

    settings = get_settings()
    client_ip = get_client_ip(request)
    await enforce_rate_limit(
        scope="settings:search:ip",
        subject=client_ip,
        limit=settings.settings_search_ip_rate_limit,
        window_seconds=settings.settings_search_ip_rate_window_seconds,
        detail="Too many settings search requests from this IP address.",
    )
    await enforce_rate_limit(
        scope="settings:search:user",
        subject=str(session_data.telegram_user_id),
        limit=settings.settings_search_user_rate_limit,
        window_seconds=settings.settings_search_user_rate_window_seconds,
        detail="Too many settings search requests for this Telegram user.",
    )

    try:
        async with _ruz_client() as client:
            groups = await client.groups.search_groups_by_name(normalized_query)
    except ValueError:
        return await _base_settings_state(
            ruz_user=ruz_user,
            group_query=normalized_query,
            error_message="Enter a group name to search.",
            success_message=success_message,
        )
    except RuzAuthError:
        logger.exception("RUZ API authorization failed during group search")
        return await _base_settings_state(
            ruz_user=ruz_user,
            group_query=normalized_query,
            error_message="RUZ API authorization failed. Check the server API key.",
            success_message=success_message,
        )
    except (RuzClientError, RuzHttpError):
        logger.exception("Failed to search groups for query %s", normalized_query)
        return await _base_settings_state(
            ruz_user=ruz_user,
            group_query=normalized_query,
            error_message="Could not search groups right now.",
            success_message=success_message,
        )

    return await _base_settings_state(
        ruz_user=ruz_user,
        group_query=normalized_query,
        group_results=_build_group_results(groups),
        success_message=success_message,
    )


async def change_group(
    request: Request,
    *,
    group_oid: int,
    group_label: str,
) -> SettingsPageState:
    """Apply a group change for the authenticated user."""
    session_data = _decode_session_from_request(request)
    settings = get_settings()
    await enforce_rate_limit(
        scope="settings:group:user",
        subject=str(session_data.telegram_user_id),
        limit=settings.settings_group_change_rate_limit,
        window_seconds=settings.settings_group_change_rate_window_seconds,
        detail="Too many group change attempts for this Telegram user.",
    )
    ruz_user = await load_ruz_user(session_data.telegram_user_id)
    normalized_label = group_label.strip()

    try:
        async with _ruz_client() as client:
            server_group = await _fetch_group(client, group_oid)
            group_guid = _normalize_optional_str(
                server_group.get("guid") if server_group else None
            )
            group_name = _normalize_optional_str(
                server_group.get("name") if server_group else None
            )
            faculty_name = _normalize_optional_str(
                server_group.get("faculty_name") if server_group else None
            )

            if server_group is None:
                hits = await client.groups.search_groups_by_name(normalized_label)
                hit = _group_hit_for_oid(hits, group_oid)
                if group_guid is None:
                    group_guid = _normalize_optional_str(
                        hit.get("guid") if hit else None
                    )
                if group_name is None:
                    group_name = _normalize_optional_str(
                        hit.get("name") if hit else normalized_label
                    )
                if faculty_name is None:
                    faculty_name = _normalize_optional_str(
                        hit.get("faculty_name") if hit else None
                    )

            if group_guid is None or group_name is None:
                return await _base_settings_state(
                    ruz_user=ruz_user,
                    group_query=normalized_label,
                    error_message=(
                        "Could not resolve the selected group metadata. Try searching again."
                    ),
                )

            existing_user = await _fetch_user(client, session_data.telegram_user_id)
            if existing_user is None:
                await client.users.create_user(
                    UserCreate(
                        id=session_data.telegram_user_id,
                        username=session_data.username or "",
                        group_oid=group_oid,
                        subgroup=None,
                        group_guid=group_guid,
                        group_name=group_name,
                        faculty_name=faculty_name,
                    )
                )
            else:
                await client.users.update_user(
                    session_data.telegram_user_id,
                    UserUpdate(
                        group_oid=group_oid,
                        group_guid=group_guid,
                        group_name=group_name,
                        faculty_name=faculty_name,
                    ),
                )
    except RuzAuthError:
        logger.exception("RUZ API authorization failed during group change")
        return await _base_settings_state(
            ruz_user=ruz_user,
            group_query=normalized_label,
            error_message="RUZ API authorization failed. Check the server API key.",
        )
    except (RuzClientError, RuzHttpError):
        logger.exception("Failed to change group to OID %s", group_oid)
        return await _base_settings_state(
            ruz_user=ruz_user,
            group_query=normalized_label,
            error_message="Could not change the group right now.",
        )

    await invalidate_cached_schedule(session_data.telegram_user_id)
    updated_user = await load_ruz_user(session_data.telegram_user_id)
    return await _base_settings_state(
        ruz_user=updated_user,
        success_message="Group updated successfully.",
    )


async def change_subgroup(
    request: Request,
    *,
    subgroup: int,
) -> SettingsPageState:
    """Apply a subgroup change for the authenticated user."""
    session_data = _decode_session_from_request(request)
    settings = get_settings()
    await enforce_rate_limit(
        scope="settings:subgroup:user",
        subject=str(session_data.telegram_user_id),
        limit=settings.settings_subgroup_change_rate_limit,
        window_seconds=settings.settings_subgroup_change_rate_window_seconds,
        detail="Too many subgroup change attempts for this Telegram user.",
    )
    ruz_user = await load_ruz_user(session_data.telegram_user_id)

    if subgroup not in {0, 1, 2}:
        return await _base_settings_state(
            ruz_user=ruz_user,
            error_message="Subgroup must be one of 0, 1, or 2.",
        )

    try:
        async with _ruz_client() as client:
            existing_user = await _fetch_user(client, session_data.telegram_user_id)
            if existing_user is None:
                return await _base_settings_state(
                    ruz_user=ruz_user,
                    error_message="Select a group before choosing a subgroup.",
                )

            await client.users.update_user(
                session_data.telegram_user_id,
                UserUpdate(subgroup=subgroup),
            )
    except RuzAuthError:
        logger.exception("RUZ API authorization failed during subgroup change")
        return await _base_settings_state(
            ruz_user=ruz_user,
            error_message="RUZ API authorization failed. Check the server API key.",
        )
    except (RuzClientError, RuzHttpError):
        logger.exception("Failed to change subgroup to %s", subgroup)
        return await _base_settings_state(
            ruz_user=ruz_user,
            error_message="Could not change the subgroup right now.",
        )

    await invalidate_cached_schedule(session_data.telegram_user_id)
    updated_user = await load_ruz_user(session_data.telegram_user_id)
    return await _base_settings_state(
        ruz_user=updated_user,
        success_message="Subgroup updated successfully.",
    )
