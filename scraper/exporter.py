"""CSV (UTF-8 with BOM) and JSON exporters for aggregated continuing education courses."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from scraper.models import COURSE_FIELD_NAMES, CourseRecord


def export_courses_csv(courses: list[CourseRecord], csv_path: Path) -> None:
    """Write courses to csv_path using UTF-8 with BOM (utf-8-sig) and exact 12 headers."""
    target = Path(csv_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COURSE_FIELD_NAMES)
        for course in courses:
            writer.writerow(course.to_csv_row())


def export_courses_json(
    courses: list[CourseRecord],
    statuses: list[dict[str, Any]],
    json_path: Path,
    updated_at: str,
) -> None:
    """Write courses metadata, source statuses, and 12-field course dictionaries to json_path."""
    target = Path(json_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    timestamp = updated_at or datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "updated_at": timestamp,
        "total": len(courses),
        "fields": list(COURSE_FIELD_NAMES),
        "source_statuses": statuses,
        "courses": [course.to_dict() for course in courses],
    }

    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
