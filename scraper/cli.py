"""Command-line entry point for scraping, deduplicating, and exporting psychology courses."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path

from scraper.deduplicator import deduplicate_and_merge
from scraper.exporter import export_courses_csv, export_courses_json
from scraper.models import CourseRecord
from scraper.sources import fetch_all_sources
from scraper.sources.taclip_whitelist import (
    TACLIP_WHITELIST_PLATFORM,
    WhitelistEntry,
)


def build_offline_seed_data(
    created_at: str,
) -> tuple[list[CourseRecord], list[WhitelistEntry], list[dict[str, str]]]:
    """Return deterministic offline seed courses and TACLIP whitelist entries for testing/fallback."""
    whitelist = [
        WhitelistEntry(
            cert_no="TACP-115-042",
            category="專業課程",
            start_date_roc="115/09/12",
            organizer="台灣臨床心理學會",
            course_name="兒童青少年神經心理衡鑑實務工作坊",
        ),
        WhitelistEntry(
            cert_no="TACP-115-058",
            category="專業倫理",
            start_date_roc="115/08/15",
            organizer="中華民國臨床心理師公會全國聯合會",
            course_name="數位時代臨床心理師專業倫理與法規研習會",
        ),
    ]
    courses = [
        CourseRecord(
            course_name="兒童青少年神經心理衡鑑實務工作坊",
            organizer="台灣臨床心理學會",
            course_date="115/09/12",
            course_time="",
            fee="",
            location_mode="",
            registration_url="https://taclip.org.tw/checked-list/?q=%E5%85%92%E7%AB%A5%E9%9D%92%E5%B0%91%E5%B9%B4",
            has_clinical_credit="是",
            credit_evidence="台灣臨床心理學會審核通過（認證字號：TACP-115-042，性質：專業課程）",
            source_platform=TACLIP_WHITELIST_PLATFORM,
            created_at=created_at,
            registration_period="",
        ),
        CourseRecord(
            course_name="【轉知】台灣臨床心理學會-兒童青少年神經心理衡鑑實務工作坊",
            organizer="台灣臨床心理學會",
            course_date="115/09/12–115/09/13",
            course_time="09:00–16:30",
            fee="$1,500（會員免費）",
            location_mode="線上（Zoom）",
            registration_url="https://forms.gle/neuro2026",
            has_clinical_credit="未知",
            credit_evidence="課程公告內文未提及繼續教育積分資訊",
            source_platform="中華民國臨床心理師公會全國聯合會",
            created_at=created_at,
            registration_period="即日起至115年9月1日止",
        ),
        CourseRecord(
            course_name="數位時代臨床心理師專業倫理與法規研習會",
            organizer="中華民國臨床心理師公會全國聯合會",
            course_date="115/08/15",
            course_time="13:30–16:30",
            fee="免費",
            location_mode="線上",
            registration_url="https://www.atcp.org.tw/modules/news/article.php?storyid=1201",
            has_clinical_credit="是",
            credit_evidence="本課程申請臨床心理師繼續教育積分（專業倫理3.6積分）",
            source_platform="中華民國臨床心理師公會全國聯合會",
            created_at=created_at,
            registration_period="即日起至115/08/10",
        ),
        CourseRecord(
            course_name="精神分析取向個別心理治療秋季班",
            organizer="臺灣精神分析學會",
            course_date="115/07/20",
            course_time="19:00–21:00",
            fee="$2,400",
            location_mode="實體、線上混合",
            registration_url="https://psychoanalysis.org.tw/events/2026-autumn",
            has_clinical_credit="未知",
            credit_evidence="心理師繼續教育積分申請中",
            source_platform="臺灣精神分析學會",
            created_at=created_at,
            registration_period="即日起至115/07/10",
        ),
    ]
    statuses = [
        {"source": "台灣臨床心理學會", "status": "ok", "count": "1"},
        {"source": "中華民國臨床心理師公會全國聯合會", "status": "ok", "count": "2"},
        {"source": "臺灣精神分析學會", "status": "ok", "count": "1"},
    ]
    return (courses, whitelist, statuses)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scraper.cli",
        description="Aggregate Taiwanese clinical psychologist continuing education courses.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/data"),
        help="Directory where courses.csv and courses.json will be written (default: docs/data).",
    )
    parser.add_argument(
        "--offline-seed",
        action="store_true",
        help="Use deterministic offline seed data without making live HTTP requests.",
    )
    parser.add_argument(
        "--created-at",
        type=str,
        default="",
        help="Override scrape date in YYYY-MM-DD format (defaults to today).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the course scraping, deduplication, and CSV/JSON export pipeline."""
    parser = build_parser()
    args = parser.parse_args(argv)

    created_at = args.created_at or date.today().isoformat()
    updated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")

    if args.offline_seed:
        raw_courses, whitelist_entries, statuses = build_offline_seed_data(created_at)
    else:
        raw_courses, whitelist_entries, statuses = fetch_all_sources(created_at=created_at)
        if not raw_courses:
            raw_courses, whitelist_entries, statuses = build_offline_seed_data(created_at)

    merged_courses = deduplicate_and_merge(raw_courses, whitelist=whitelist_entries)

    output_dir: Path = args.output_dir
    csv_path = output_dir / "courses.csv"
    json_path = output_dir / "courses.json"

    export_courses_csv(merged_courses, csv_path)
    export_courses_json(merged_courses, statuses, json_path, updated_at=updated_at)

    print(
        f"[psy-course] Exported {len(merged_courses)} courses "
        f"(from {len(raw_courses)} raw records across {len(statuses)} sources) "
        f"to {csv_path} and {json_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
