"""Schedule schemas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ruzclient.http.endpoints.schedule import UserScheduleLesson


@dataclass(slots=True, frozen=True)
class ScheduleLessonView:
    """Single lesson prepared for rendering."""

    discipline_name: str
    kind_of_work: str
    kind_of_work_class: str
    lecturer_short_name: str
    auditorium_name: str
    building: str
    subgroup: int


@dataclass(slots=True, frozen=True)
class ScheduleSlotView:
    """Single schedule column."""

    key: str
    label: str


@dataclass(slots=True)
class ScheduleRowView:
    """Single schedule row."""

    date_key: str
    date_label: str
    cells: dict[str, list[ScheduleLessonView]]


@dataclass(slots=True)
class SchedulePageState:
    """Schedule page rendering state."""

    authenticated: bool
    schedule_rows: list[ScheduleRowView]
    schedule_slots: list[ScheduleSlotView]
    error_message: str | None = None


@dataclass(slots=True, frozen=True)
class ScheduleCacheSnapshot:
    """Serialized schedule cache payload with user group identity metadata."""

    schedule: list[UserScheduleLesson]
    group_id: Any | None = None
    subgroup: int | None = None
