"""Schedule services."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, time, timedelta
from pathlib import Path

from fastapi import HTTPException, Request, status
from fastapi.templating import Jinja2Templates
from ruzclient import ClientConfig, RuzClient
from ruzclient.errors import RuzAuthError, RuzClientError, RuzHttpError
from ruzclient.http.endpoints.schedule import UserScheduleLesson

from ruzsite.logging_config import setup_logging
from ruzsite.schemas.schedule import (
    ScheduleLessonView,
    SchedulePageState,
    ScheduleRowView,
    ScheduleSlotView,
)
from ruzsite.services.auth_service import SESSION_COOKIE_NAME, decode_session
from ruzsite.services.rate_limit_service import (
    cache_schedule,
    enforce_rate_limit,
    get_cached_schedule,
    get_client_ip,
)
from ruzsite.settings import ROOT, get_settings

setup_logging()
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory=Path(ROOT, "src", "ruzsite", "templates"))

_RUSSIAN_WEEKDAYS = {
    0: "Пн",
    1: "Вт",
    2: "Ср",
    3: "Чт",
    4: "Пт",
    5: "Сб",
    6: "Вс",
}

_KIND_OF_WORK_CLASS_MAP = {
    "лекции": "lesson-card--lecture",
    "практические (семинарские) занятия": "lesson-card--practice",
    "лабораторные работы": "lesson-card--lab",
    "зачеты": "lesson-card--credit",
    "зачёты": "lesson-card--credit",
    "зачет с оценкой": "lesson-card--graded-credit",
    "зачёт с оценкой": "lesson-card--graded-credit",
    "консультации перед экзаменом": "lesson-card--consultation",
    "экзамены": "lesson-card--exam",
    "производственная практика": "lesson-card--internship",
}


def _parse_schedule_date(value: str) -> date:
    """Parse ISO schedule date."""
    return date.fromisoformat(value)


def _parse_schedule_time(value: str) -> time:
    """Parse schedule time."""
    return time.fromisoformat(value)


def _format_date_label(value: date) -> str:
    """Build short Russian date label for a row."""
    return f"{_RUSSIAN_WEEKDAYS[value.weekday()]}, {value:%d.%m}"


def _format_schedule_time(value: str) -> str:
    """Format schedule time without seconds."""
    return _parse_schedule_time(value).strftime("%H:%M")


def _slot_key(begin_lesson: str, end_lesson: str) -> str:
    """Build a stable slot key."""
    return f"{begin_lesson}-{end_lesson}"


def _kind_of_work_class(kind_of_work: str) -> str:
    """Return CSS class for lesson type color coding."""
    normalized = kind_of_work.strip().casefold()
    return _KIND_OF_WORK_CLASS_MAP.get(normalized, "lesson-card--default")


def _with_sunday_separator_dates(dates: set[date]) -> list[date]:
    """Include empty Sunday rows so table visually separates study weeks."""
    if not dates:
        return []

    expanded_dates = set(dates)
    current = min(dates)
    end = max(dates)

    while current <= end:
        if current.weekday() == 6:
            expanded_dates.add(current)
        current += timedelta(days=1)

    return sorted(expanded_dates)


def _build_slot_views(
    schedule: list[UserScheduleLesson],
) -> tuple[list[ScheduleSlotView], dict[str, ScheduleSlotView]]:
    """Build ordered slot metadata from the schedule."""
    ordered_slots = sorted(
        {(lesson["begin_lesson"], lesson["end_lesson"]) for lesson in schedule},
        key=lambda item: (_parse_schedule_time(item[0]), _parse_schedule_time(item[1])),
    )
    slot_views = [
        ScheduleSlotView(
            key=_slot_key(begin_lesson, end_lesson),
            label=(
                f"{index} пара "
                f"{_format_schedule_time(begin_lesson)}-{_format_schedule_time(end_lesson)}"
            ),
        )
        for index, (begin_lesson, end_lesson) in enumerate(ordered_slots, start=1)
    ]
    return slot_views, {slot.key: slot for slot in slot_views}


def build_schedule_table(
    schedule: list[UserScheduleLesson],
) -> tuple[list[ScheduleRowView], list[ScheduleSlotView]]:
    """Normalize raw schedule lessons into table rows and columns."""
    slot_views, slot_by_key = _build_slot_views(schedule)
    rows_by_date: dict[str, dict[str, list[ScheduleLessonView]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for lesson in sorted(
        schedule,
        key=lambda item: (
            _parse_schedule_date(item["date"]),
            _parse_schedule_time(item["begin_lesson"]),
            item["discipline_name"],
            item["kind_of_work"],
        ),
    ):
        slot_key = _slot_key(lesson["begin_lesson"], lesson["end_lesson"])
        if slot_key not in slot_by_key:
            continue
        rows_by_date[lesson["date"]][slot_key].append(
            ScheduleLessonView(
                discipline_name=lesson["discipline_name"],
                kind_of_work=lesson["kind_of_work"],
                kind_of_work_class=_kind_of_work_class(lesson["kind_of_work"]),
                lecturer_short_name=lesson["lecturer_short_name"],
                auditorium_name=lesson["auditorium_name"],
                building=lesson["building"],
                subgroup=lesson["sub_group"],
            )
        )

    ordered_dates = _with_sunday_separator_dates(
        {_parse_schedule_date(schedule_date) for schedule_date in rows_by_date}
    )
    row_views = [
        ScheduleRowView(
            date_key=schedule_date.isoformat(),
            date_label=_format_date_label(schedule_date),
            cells=dict(rows_by_date[schedule_date.isoformat()]),
        )
        for schedule_date in ordered_dates
    ]
    return row_views, slot_views


async def load_user_schedule(user_id: int) -> list[UserScheduleLesson]:
    """Fetch the user's schedule from Ruz API."""
    logger.debug("Loading schedule for user ID %s", user_id)
    settings = get_settings()
    config = ClientConfig(base_url=settings.api_url, api_key=settings.api_key)
    async with RuzClient(config=config) as client:
        return await client.schedule.get_user_schedule(user_id=user_id)


async def schedule_state(request: Request) -> SchedulePageState:
    """Build schedule page state from the current session."""
    settings = get_settings()
    client_ip = get_client_ip(request)
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie_value:
        logger.debug("Schedule request has no session cookie")
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/"},
        )

    try:
        session_data = decode_session(
            cookie_value,
            secret=settings.session_secret,
            max_age_seconds=settings.session_max_age_seconds,
        )
    except HTTPException as exc:
        logger.warning("Rejected invalid or expired schedule session cookie")
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/"},
        ) from exc

    await enforce_rate_limit(
        scope="schedule:ip",
        subject=client_ip,
        limit=settings.schedule_ip_rate_limit,
        window_seconds=settings.schedule_ip_rate_window_seconds,
        detail="Too many schedule requests from this IP address.",
    )
    await enforce_rate_limit(
        scope="schedule:user",
        subject=str(session_data.telegram_user_id),
        limit=settings.schedule_user_rate_limit,
        window_seconds=settings.schedule_user_rate_window_seconds,
        detail="Too many schedule requests for this Telegram user.",
    )

    cached_schedule = await get_cached_schedule(session_data.telegram_user_id)
    if cached_schedule is not None:
        rows, slots = build_schedule_table(cached_schedule)
        return SchedulePageState(
            authenticated=True,
            schedule_rows=rows,
            schedule_slots=slots,
        )

    try:
        schedule = await load_user_schedule(session_data.telegram_user_id)
    except RuzHttpError as exc:
        logger.exception(
            "Ruz API error while loading schedule for Telegram user ID %s",
            session_data.telegram_user_id,
        )
        return SchedulePageState(
            authenticated=True,
            schedule_rows=[],
            schedule_slots=[],
            error_message=f"Could not load schedule",
        )
    except (RuzAuthError, RuzClientError) as exc:
        logger.exception(
            "Ruz client error while loading schedule for Telegram user ID %s",
            session_data.telegram_user_id,
        )
        return SchedulePageState(
            authenticated=True,
            schedule_rows=[],
            schedule_slots=[],
            error_message=f"Could not load schedule",
        )

    await cache_schedule(
        session_data.telegram_user_id,
        schedule,
        ttl_seconds=settings.schedule_cache_ttl_seconds,
    )
    rows, slots = build_schedule_table(schedule)
    return SchedulePageState(
        authenticated=True,
        schedule_rows=rows,
        schedule_slots=slots,
    )


def build_page(state: SchedulePageState) -> str:
    """Render the schedule page template."""
    return templates.get_template("schedule.html").render(
        authenticated=state.authenticated,
        state=state,
        current_page="schedule",
    )
