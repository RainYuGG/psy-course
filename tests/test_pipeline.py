"""Unit and integration tests for deduplicator, CSV/JSON exporter, and CLI pipeline."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scraper.cli import main as cli_main
from scraper.deduplicator import (
    deduplicate_and_merge,
    match_whitelist_entry,
    normalize_course_key,
)
from scraper.exporter import export_courses_csv, export_courses_json
from scraper.models import COURSE_FIELD_NAMES, CourseRecord
from scraper.sources.taclip_whitelist import (
    TACLIP_WHITELIST_PLATFORM,
    WhitelistEntry,
)


class TestNormalizeCourseKey:
    """Tests for normalize_course_key."""

    def test_strips_brackets_punctuation_and_whitespace(self) -> None:
        raw = "【轉知】「創傷知情」臨床實務工作坊（線上課程）！"
        key = normalize_course_key(raw)
        assert key == "創傷知情臨床實務工作坊"

    def test_strips_organizer_prefix_before_hyphen(self) -> None:
        key_with_org = normalize_course_key("台灣臨床心理學會 - 2026年司法心理衡鑑專題講座")
        key_plain = normalize_course_key("2026年司法心理衡鑑專題講座")
        assert key_with_org == key_plain
        assert "司法心理衡鑑專題講座" in key_with_org

    def test_preserves_ascii_acronyms_with_hyphens(self) -> None:
        key = normalize_course_key("DSM-5-TR 臨床診斷實務研討會")
        assert "dsm5tr" in key
        assert "臨床診斷實務研討會" in key


class TestMatchWhitelistEntry:
    """Tests for match_whitelist_entry."""

    def test_matches_by_start_date_and_normalized_name(self) -> None:
        whitelist = [
            WhitelistEntry(
                cert_no="TACP-115-088",
                category="專業課程",
                start_date_roc="115/09/12",
                organizer="國立臺灣大學醫學院附設醫院",
                course_name="創傷知情與情緒調節臨床實務工作坊",
            ),
            WhitelistEntry(
                cert_no="TACP-115-099",
                category="專業倫理",
                start_date_roc="115/10/03",
                organizer="台灣臨床心理學會",
                course_name="臨床心理師倫理與法規研習",
            ),
        ]
        course = CourseRecord(
            course_name="【轉知】臺大醫院 - 創傷知情與情緒調節臨床實務工作坊（兩日課程）",
            organizer="中華民國臨床心理師公會全國聯合會",
            course_date="115/09/12–115/09/13",
            source_platform="中華民國臨床心理師公會全國聯合會",
        )
        matched = match_whitelist_entry(course, whitelist)
        assert matched is not None
        assert matched.cert_no == "TACP-115-088"

    def test_does_not_match_when_start_date_differs(self) -> None:
        whitelist = [
            WhitelistEntry(
                cert_no="TACP-115-088",
                category="專業課程",
                start_date_roc="115/09/12",
                organizer="國立臺灣大學醫學院附設醫院",
                course_name="創傷知情與情緒調節臨床實務工作坊",
            )
        ]
        course = CourseRecord(
            course_name="創傷知情與情緒調節臨床實務工作坊",
            organizer="國立臺灣大學醫學院附設醫院",
            course_date="115/11/20",
        )
        assert match_whitelist_entry(course, whitelist) is None


class TestDeduplicateAndMerge:
    """Tests for deduplicate_and_merge across TACLIP whitelist and association detail records."""

    def test_merges_taclip_whitelist_record_with_detailed_atcp_record(self) -> None:
        whitelist_entry = WhitelistEntry(
            cert_no="TACP-115-042",
            category="專業課程",
            start_date_roc="115/09/12",
            organizer="台灣臨床心理學會",
            course_name="兒童青少年神經心理衡鑑實務工作坊",
        )
        whitelist_record = CourseRecord(
            course_name="兒童青少年神經心理衡鑑實務工作坊",
            organizer="台灣臨床心理學會",
            course_date="115/09/12",
            course_time="",
            fee="",
            location_mode="",
            registration_url="https://taclip.org.tw/checked-list/?q=%E5%85%92%E7%AB%A5",
            has_clinical_credit="是",
            credit_evidence="台灣臨床心理學會審核通過（認證字號：TACP-115-042，性質：專業課程）",
            source_platform=TACLIP_WHITELIST_PLATFORM,
            created_at="2026-11-08",
            registration_period="",
        )
        atcp_detail_record = CourseRecord(
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
            created_at="2026-11-08",
            registration_period="即日起至115年9月1日止",
        )

        merged = deduplicate_and_merge(
            [whitelist_record, atcp_detail_record],
            whitelist=[whitelist_entry],
        )
        assert len(merged) == 1
        rec = merged[0]
        assert rec.course_date == "115/09/12–115/09/13"
        assert rec.course_time == "09:00–16:30"
        assert rec.fee == "$1,500（會員免費）"
        assert rec.location_mode == "線上（Zoom）"
        assert rec.registration_url == "https://forms.gle/neuro2026"
        assert rec.registration_period == "即日起至115年9月1日止"
        assert rec.has_clinical_credit == "是"
        assert "TACP-115-042" in rec.credit_evidence

    def test_enriches_non_whitelist_record_and_sorts_descending_by_date(self) -> None:
        whitelist = [
            WhitelistEntry(
                cert_no="TACP-115-105",
                category="專業法規",
                start_date_roc="115/11/15",
                organizer="馬偕紀念醫院",
                course_name="自殺防治與危機處置臨床實務講座",
            )
        ]
        older_course = CourseRecord(
            course_name="精神分析導論秋季班",
            organizer="臺灣精神分析學會",
            course_date="115/06/25",
            course_time="19:00–21:00",
            fee="$800",
            location_mode="線上",
            registration_url="https://psychoanalysis.org.tw/events/101",
            has_clinical_credit="否",
            credit_evidence="本課程不申請繼續教育積分",
            source_platform="臺灣精神分析學會",
            created_at="2026-11-08",
            registration_period="",
        )
        newer_course = CourseRecord(
            course_name="【講座】自殺防治與危機處置臨床實務講座",
            organizer="馬偕紀念醫院",
            course_date="115/11/15",
            course_time="13:30–16:30",
            fee="免費",
            location_mode="馬偕紀念醫院福音樓9樓",
            registration_url="https://www.atcp.org.tw/modules/news/article.php?storyid=999",
            has_clinical_credit="未知",
            credit_evidence="繼續教育積分申請中",
            source_platform="中華民國臨床心理師公會全國聯合會",
            created_at="2026-11-08",
            registration_period="即日起至額滿為止",
        )

        result = deduplicate_and_merge([older_course, newer_course], whitelist=whitelist)
        assert len(result) == 2
        # Sorted newest course_date first
        assert result[0].course_date == "115/11/15"
        assert result[0].has_clinical_credit == "是"
        assert "TACP-115-105" in result[0].credit_evidence
        assert result[1].course_date == "115/06/25"


class TestFilterUpcoming:
    """Only courses that have not finished and still accept registration are listed."""

    def test_drops_finished_deadline_passed_and_undated_courses(self) -> None:
        from datetime import date

        from scraper.deduplicator import filter_upcoming

        def rec(name: str, course_date: str, period: str = "") -> CourseRecord:
            return CourseRecord(
                course_name=name,
                organizer="測試單位",
                course_date=course_date,
                registration_period=period,
            )

        courses = [
            rec("finished", "115/10/27"),
            rec("ongoing series", "115/09/23–115/12/02"),
            rec("future", "116/01/24", "即日起至 116/01/24 前"),
            rec("deadline passed", "115/12/05", "115年11月6日(五)前完成報名"),
            rec("deadline is today", "115/12/19", "115年11月8日(日)前完成報名"),
            rec("undated", ""),
        ]

        kept = filter_upcoming(courses, today=date(2026, 11, 8))

        assert [c.course_name for c in kept] == ["ongoing series", "future", "deadline is today"]


class TestExporters:
    """Tests for export_courses_csv and export_courses_json."""

    def test_export_courses_csv_writes_utf8_bom_and_12_headers(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "data" / "courses.csv"
        sample = CourseRecord(
            course_name="臨床心理師倫理工作坊",
            organizer="台灣臨床心理學會",
            course_date="115/08/20",
            course_time="09:00–12:00",
            fee="免費",
            location_mode="線上",
            registration_url="https://taclip.org.tw/events/1",
            has_clinical_credit="是",
            credit_evidence="台灣臨床心理學會審核通過（認證字號：TACP-115-001）",
            source_platform="台灣臨床心理學會",
            created_at="2026-11-08",
            registration_period="即日起至115/08/10",
        )
        export_courses_csv([sample], csv_path)

        raw_bytes = csv_path.read_bytes()
        assert raw_bytes.startswith(b"\xef\xbb\xbf")

        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = list(csv.reader(f))

        assert len(reader) == 2
        assert reader[0] == COURSE_FIELD_NAMES
        assert len(reader[0]) == 12
        assert reader[1] == sample.to_csv_row()

    def test_export_courses_json_writes_expected_schema(self, tmp_path: Path) -> None:
        json_path = tmp_path / "data" / "courses.json"
        sample = CourseRecord(
            course_name="臨床心理師倫理工作坊",
            organizer="台灣臨床心理學會",
            course_date="115/08/20",
            course_time="09:00–12:00",
            fee="免費",
            location_mode="線上",
            registration_url="https://taclip.org.tw/events/1",
            has_clinical_credit="是",
            credit_evidence="台灣臨床心理學會審核通過（認證字號：TACP-115-001）",
            source_platform="台灣臨床心理學會",
            created_at="2026-11-08",
            registration_period="即日起至115/08/10",
        )
        statuses = [{"source": "台灣臨床心理學會", "status": "ok", "count": "1"}]
        export_courses_json([sample], statuses, json_path, updated_at="2026-11-08 08:00:00")

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["updated_at"] == "2026-11-08 08:00:00"
        assert payload["total"] == 1
        assert payload["fields"] == COURSE_FIELD_NAMES
        assert payload["source_statuses"] == statuses
        assert len(payload["courses"]) == 1
        assert payload["courses"][0]["課程名稱"] == "臨床心理師倫理工作坊"
        assert list(payload["courses"][0].keys()) == COURSE_FIELD_NAMES


class TestCliMain:
    """Tests for scraper.cli.main."""

    def test_cli_offline_seed_generates_csv_and_json(self, tmp_path: Path) -> None:
        out_dir = tmp_path / "docs" / "data"
        exit_code = cli_main(["--output-dir", str(out_dir), "--offline-seed", "--today", "2026-01-01"])
        assert exit_code == 0

        csv_path = out_dir / "courses.csv"
        json_path = out_dir / "courses.json"
        assert csv_path.exists()
        assert json_path.exists()
        assert csv_path.read_bytes().startswith(b"\xef\xbb\xbf")

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["total"] > 0
        assert payload["fields"] == COURSE_FIELD_NAMES
        assert len(payload["courses"]) == payload["total"]

    def test_cli_live_mode_invokes_fetch_all_sources_and_deduplicates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_fetch_all_sources(created_at: str = ""):
            wl = [
                WhitelistEntry(
                    cert_no="TACP-115-777",
                    category="專業課程",
                    start_date_roc="115/10/10",
                    organizer="台灣臨床心理學會",
                    course_name="神經心理衡鑑進階研習",
                )
            ]
            courses = [
                CourseRecord(
                    course_name="【轉知】神經心理衡鑑進階研習",
                    organizer="中華民國臨床心理師公會全國聯合會",
                    course_date="115/10/10",
                    course_time="09:00–16:00",
                    fee="$1,000",
                    location_mode="線上",
                    registration_url="https://forms.gle/test777",
                    has_clinical_credit="未知",
                    credit_evidence="課程公告內文未提及繼續教育積分資訊",
                    source_platform="中華民國臨床心理師公會全國聯合會",
                    created_at=created_at or "2026-11-08",
                    registration_period="即日起至115/10/01",
                )
            ]
            statuses = [{"source": "中華民國臨床心理師公會全國聯合會", "status": "ok", "count": "1"}]
            return (courses, wl, statuses)

        monkeypatch.setattr("scraper.cli.fetch_all_sources", fake_fetch_all_sources)
        out_dir = tmp_path / "live_out"
        exit_code = cli_main(
            ["--output-dir", str(out_dir), "--created-at", "2026-11-08", "--today", "2026-01-01"]
        )
        assert exit_code == 0

        payload = json.loads((out_dir / "courses.json").read_text(encoding="utf-8"))
        assert payload["total"] == 1
        course_dict = payload["courses"][0]
        assert course_dict["是否有臨床心理師積分"] == "是"
        assert "TACP-115-777" in course_dict["積分判斷依據段落"]
        assert course_dict["建立時間"] == "2026-11-08"

    def test_cli_drops_courses_that_already_ended(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_fetch_all_sources(created_at: str = ""):
            def rec(name: str, course_date: str) -> CourseRecord:
                return CourseRecord(
                    course_name=name,
                    organizer="測試單位",
                    course_date=course_date,
                    registration_url="https://forms.gle/x",
                    source_platform="測試單位",
                    created_at=created_at,
                )

            return ([rec("已結束的訓練課程", "115/10/10"), rec("尚未開始的訓練課程", "116/02/01")], [], [])

        monkeypatch.setattr("scraper.cli.fetch_all_sources", fake_fetch_all_sources)
        out_dir = tmp_path / "out"
        assert cli_main(["--output-dir", str(out_dir), "--today", "2026-11-08"]) == 0

        payload = json.loads((out_dir / "courses.json").read_text(encoding="utf-8"))
        assert [c["課程名稱"] for c in payload["courses"]] == ["尚未開始的訓練課程"]
