"""Tests for schedule page normalization."""

from ruzclient.http.endpoints.schedule import UserScheduleLesson

from ruzsite.services.schedule_service import build_schedule_table


def test_build_schedule_table_creates_date_rows_and_ordered_slots() -> None:
    """Schedule data should be grouped by date and sorted by lesson start time."""
    schedule: list[UserScheduleLesson] = [
        {
            "lesson_id": 1,
            "date": "2026-05-25",
            "begin_lesson": "10:10:00",
            "end_lesson": "11:40:00",
            "sub_group": 2,
            "discipline_name": "Physics",
            "kind_of_work": "Лекции",
            "lecturer_short_name": "Dr. B",
            "lecturer_id": 2,
            "discipline_id": 22,
            "auditorium_name": "202",
            "building": "B",
            "group_id": 100,
        },
        {
            "lesson_id": 2,
            "date": "2026-05-22",
            "begin_lesson": "08:30:00",
            "end_lesson": "10:00:00",
            "sub_group": 1,
            "discipline_name": "Math",
            "kind_of_work": "Практические (семинарские) занятия",
            "lecturer_short_name": "Dr. A",
            "lecturer_id": 1,
            "discipline_id": 11,
            "auditorium_name": "101",
            "building": "A",
            "group_id": 100,
        },
    ]

    rows, slots = build_schedule_table(schedule)

    assert [slot.label for slot in slots] == [
        "1 пара 08:30-10:00",
        "2 пара 10:10-11:40",
    ]
    assert [row.date_label for row in rows] == ["Пт, 22.05", "Вс, 24.05", "Пн, 25.05"]
    assert rows[0].cells["08:30:00-10:00:00"][0].discipline_name == "Math"
    assert rows[2].cells["10:10:00-11:40:00"][0].discipline_name == "Physics"
    assert (
        rows[0].cells["08:30:00-10:00:00"][0].kind_of_work_class
        == "lesson-card--practice"
    )
    assert (
        rows[2].cells["10:10:00-11:40:00"][0].kind_of_work_class
        == "lesson-card--lecture"
    )


def test_build_schedule_table_inserts_empty_sunday_rows_between_weeks() -> None:
    """A Sunday row should be inserted to visually separate adjacent weeks."""
    schedule: list[UserScheduleLesson] = [
        {
            "lesson_id": 1,
            "date": "2026-05-22",
            "begin_lesson": "08:30:00",
            "end_lesson": "10:00:00",
            "sub_group": 1,
            "discipline_name": "Math",
            "kind_of_work": "Практические (семинарские) занятия",
            "lecturer_short_name": "Dr. A",
            "lecturer_id": 1,
            "discipline_id": 11,
            "auditorium_name": "101",
            "building": "A",
            "group_id": 100,
        },
        {
            "lesson_id": 2,
            "date": "2026-05-25",
            "begin_lesson": "10:10:00",
            "end_lesson": "11:40:00",
            "sub_group": 2,
            "discipline_name": "Physics",
            "kind_of_work": "Лекции",
            "lecturer_short_name": "Dr. B",
            "lecturer_id": 2,
            "discipline_id": 22,
            "auditorium_name": "202",
            "building": "B",
            "group_id": 100,
        },
    ]

    rows, _ = build_schedule_table(schedule)

    assert [row.date_label for row in rows] == ["Пт, 22.05", "Вс, 24.05", "Пн, 25.05"]
    assert rows[1].date_key == "2026-05-24"
    assert rows[1].cells == {}


def test_build_schedule_table_maps_known_ruz_kind_of_work_values() -> None:
    """Known Ruz lesson kinds should resolve to stable CSS classes."""
    schedule: list[UserScheduleLesson] = [
        {
            "lesson_id": 1,
            "date": "2026-05-22",
            "begin_lesson": "08:30:00",
            "end_lesson": "10:00:00",
            "sub_group": 1,
            "discipline_name": "Subject 1",
            "kind_of_work": "Лабораторные работы",
            "lecturer_short_name": "A",
            "lecturer_id": 1,
            "discipline_id": 11,
            "auditorium_name": "101",
            "building": "A",
            "group_id": 100,
        },
        {
            "lesson_id": 2,
            "date": "2026-05-22",
            "begin_lesson": "10:10:00",
            "end_lesson": "11:40:00",
            "sub_group": 1,
            "discipline_name": "Subject 2",
            "kind_of_work": "Зачет с оценкой",
            "lecturer_short_name": "B",
            "lecturer_id": 2,
            "discipline_id": 12,
            "auditorium_name": "102",
            "building": "B",
            "group_id": 100,
        },
        {
            "lesson_id": 3,
            "date": "2026-05-22",
            "begin_lesson": "12:00:00",
            "end_lesson": "13:30:00",
            "sub_group": 1,
            "discipline_name": "Subject 3",
            "kind_of_work": "Консультации перед экзаменом",
            "lecturer_short_name": "C",
            "lecturer_id": 3,
            "discipline_id": 13,
            "auditorium_name": "103",
            "building": "C",
            "group_id": 100,
        },
        {
            "lesson_id": 4,
            "date": "2026-05-22",
            "begin_lesson": "13:40:00",
            "end_lesson": "15:10:00",
            "sub_group": 1,
            "discipline_name": "Subject 4",
            "kind_of_work": "Экзамены",
            "lecturer_short_name": "D",
            "lecturer_id": 4,
            "discipline_id": 14,
            "auditorium_name": "104",
            "building": "D",
            "group_id": 100,
        },
        {
            "lesson_id": 5,
            "date": "2026-05-22",
            "begin_lesson": "15:20:00",
            "end_lesson": "16:50:00",
            "sub_group": 1,
            "discipline_name": "Subject 5",
            "kind_of_work": "Производственная практика ",
            "lecturer_short_name": "E",
            "lecturer_id": 5,
            "discipline_id": 15,
            "auditorium_name": "105",
            "building": "E",
            "group_id": 100,
        },
    ]

    rows, _ = build_schedule_table(schedule)
    lessons = [
        rows[0].cells["08:30:00-10:00:00"][0],
        rows[0].cells["10:10:00-11:40:00"][0],
        rows[0].cells["12:00:00-13:30:00"][0],
        rows[0].cells["13:40:00-15:10:00"][0],
        rows[0].cells["15:20:00-16:50:00"][0],
    ]

    assert [lesson.kind_of_work_class for lesson in lessons] == [
        "lesson-card--lab",
        "lesson-card--graded-credit",
        "lesson-card--consultation",
        "lesson-card--exam",
        "lesson-card--internship",
    ]
