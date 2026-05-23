"""Settings schemas."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class GroupSearchResult:
    """Single group search result prepared for rendering."""

    oid: int
    name: str
    guid: str
    faculty_name: str | None = None


@dataclass(slots=True)
class SettingsPageState:
    """Settings page rendering state."""

    authenticated: bool
    current_group_oid: int | None = None
    current_group_name: str | None = None
    current_subgroup: int | None = None
    group_query: str = ""
    group_results: list[GroupSearchResult] = field(default_factory=list)
    error_message: str | None = None
    success_message: str | None = None
