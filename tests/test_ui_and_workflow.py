"""Tests for GitHub Pages Web GUI (index.html, style.css, app.js), data artifacts, workflow, and README."""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

from bs4 import BeautifulSoup

from scraper.models import COURSE_FIELD_NAMES

ROOT_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT_DIR / "docs"
DATA_DIR = DOCS_DIR / "data"
WORKFLOW_PATH = ROOT_DIR / ".github" / "workflows" / "update-courses.yml"
README_PATH = ROOT_DIR / "README.md"


class TestIndexHtmlStructure:
    """Verify docs/index.html contains all required controls, badges, modals, and 12-column table."""

    def test_index_html_exists_and_has_title(self) -> None:
        index_path = DOCS_DIR / "index.html"
        assert index_path.is_file(), "docs/index.html must exist"
        html = index_path.read_text(encoding="utf-8")
        assert "臨床心理師繼續教育課程彙整查詢平台" in html

    def test_index_html_has_all_required_filter_controls(self) -> None:
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "lxml")

        required_ids = [
            "filter-keyword",
            "filter-credit",
            "filter-mode",
            "filter-fee",
            "filter-month",
            "filter-source",
        ]
        for control_id in required_ids:
            el = soup.find(id=control_id)
            assert el is not None, f"Missing required filter control #{control_id}"

        credit_options = [opt.get_text(strip=True) for opt in soup.select("#filter-credit option")]
        for expected in ("是", "未知", "否"):
            assert any(expected in opt for opt in credit_options), (
                f"#filter-credit missing option {expected}"
            )

        mode_options = [opt.get_text(strip=True) for opt in soup.select("#filter-mode option")]
        for expected in ("線上", "實體"):
            assert any(expected in opt for opt in mode_options), (
                f"#filter-mode missing option {expected}"
            )

        fee_options = [opt.get_text(strip=True) for opt in soup.select("#filter-fee option")]
        for expected in ("免費", "付費"):
            assert any(expected in opt for opt in fee_options), (
                f"#filter-fee missing option {expected}"
            )

    def test_index_html_has_action_bar_and_status_elements(self) -> None:
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "lxml")

        for element_id in (
            "course-count",
            "last-updated",
            "source-status-summary",
            "btn-download-csv",
            "btn-sheets-sync",
        ):
            el = soup.find(id=element_id)
            assert el is not None, f"Missing required element #{element_id}"

    def test_index_html_table_has_exact_12_column_headers_in_order(self) -> None:
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "lxml")

        table = soup.find(id="courses-table")
        assert table is not None, "Missing #courses-table"

        headers = [th.get_text(strip=True) for th in table.select("thead th")]
        assert headers == COURSE_FIELD_NAMES, (
            f"Table headers {headers} do not match COURSE_FIELD_NAMES {COURSE_FIELD_NAMES}"
        )


class TestStyleCssAndAppJs:
    """Verify docs/style.css and docs/app.js implement required client-side behaviors."""

    def test_style_css_exists_and_defines_responsive_and_badge_styles(self) -> None:
        css_path = DOCS_DIR / "style.css"
        assert css_path.is_file(), "docs/style.css must exist"
        css = css_path.read_text(encoding="utf-8")
        assert "@media" in css, "style.css must include responsive @media queries"
        assert "badge" in css, "style.css must define credit status badge styles"

    def test_app_js_loads_courses_json_and_implements_filters_and_sheets_formula(self) -> None:
        js_path = DOCS_DIR / "app.js"
        assert js_path.is_file(), "docs/app.js must exist"
        js = js_path.read_text(encoding="utf-8")

        assert "./data/courses.json" in js
        assert "IMPORTDATA" in js
        assert "escapeHtml" in js
        for control_id in (
            "filter-keyword",
            "filter-credit",
            "filter-mode",
            "filter-fee",
            "filter-month",
            "filter-source",
            "course-count",
            "last-updated",
            "source-status-summary",
            "btn-download-csv",
            "btn-sheets-sync",
            "courses-table",
        ):
            assert control_id in js, f"docs/app.js must reference #{control_id}"

        assert 'target="_blank"' in js or "target='_blank'" in js
        assert "noopener noreferrer" in js

    def test_app_js_runtime_filtering_formula_and_escaping_behavior(self) -> None:
        js_path = DOCS_DIR / "app.js"
        assert js_path.is_file(), "docs/app.js must exist"

        script = """
        const app = require('./docs/app.js');
        const assert = require('assert');

        assert.strictEqual(
          app.escapeHtml('<script>alert("x")</script>'),
          '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;'
        );

        assert.strictEqual(
          app.buildImportDataFormula('https://example.github.io/psy-course/index.html?q=1#top'),
          '=IMPORTDATA("https://example.github.io/psy-course/data/courses.csv")'
        );

        const courses = [
          {
            "課程名稱": "創傷知情臨床實務工作坊",
            "主辦單位": "台灣臨床心理學會",
            "課程日期": "115/07/29",
            "上課時間": "09:00–16:00",
            "費用": "免費",
            "上課地點／方式": "線上 Zoom",
            "報名連結": "https://forms.gle/abc",
            "是否有臨床心理師積分": "是",
            "積分判斷依據段落": "台灣臨床心理學會審核通過（認證字號：TACP115001）",
            "資料來源平台": "台灣臨床心理學會",
            "建立時間": "2026-11-08",
            "報名期間": "即日起至115/07/20"
          },
          {
            "課程名稱": "榮格沙遊治療實務",
            "主辦單位": "台灣遊戲治療學會",
            "課程日期": "115/08/15–115/08/16",
            "上課時間": "09:30–17:00",
            "費用": "$2400",
            "上課地點／方式": "國立臺灣師範大學（實體）",
            "報名連結": "https://www.atpt.org.tw/course",
            "是否有臨床心理師積分": "否",
            "積分判斷依據段落": "本課程僅申請諮商心理師繼續教育積分",
            "資料來源平台": "台灣遊戲治療學會",
            "建立時間": "2026-11-08",
            "報名期間": ""
          }
        ];

        assert.strictEqual(app.filterCourses(courses, { credit: "是" }).length, 1);
        assert.strictEqual(app.filterCourses(courses, { mode: "線上" }).length, 1);
        assert.strictEqual(app.filterCourses(courses, { mode: "實體" }).length, 1);
        assert.strictEqual(app.filterCourses(courses, { fee: "免費" }).length, 1);
        assert.strictEqual(app.filterCourses(courses, { fee: "付費" }).length, 1);
        assert.strictEqual(app.filterCourses(courses, { month: "115/07" }).length, 1);
        assert.strictEqual(app.filterCourses(courses, { source: "台灣遊戲治療學會" }).length, 1);
        assert.strictEqual(app.filterCourses(courses, { keyword: "TACP115001" }).length, 1);

        const csvText = app.coursesToCsvWithBom(courses);
        assert.ok(csvText.startsWith('\\uFEFF課程名稱,主辦單位,課程日期'));
        """
        proc = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"Node runtime test failed: {proc.stderr}"


class TestGeneratedDataArtifacts:
    """Verify docs/data/courses.csv and docs/data/courses.json exist and satisfy schema constraints."""

    def test_courses_csv_has_utf8_bom_and_12_headers(self) -> None:
        csv_path = DATA_DIR / "courses.csv"
        assert csv_path.is_file(), "docs/data/courses.csv must exist"
        raw = csv_path.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf"), "courses.csv must start with UTF-8 BOM"

        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)

        assert len(rows) > 1, "courses.csv must contain header + course rows"
        assert rows[0] == COURSE_FIELD_NAMES

    def test_courses_json_matches_schema(self) -> None:
        json_path = DATA_DIR / "courses.json"
        assert json_path.is_file(), "docs/data/courses.json must exist"
        payload = json.loads(json_path.read_text(encoding="utf-8"))

        assert "updated_at" in payload
        assert payload["fields"] == COURSE_FIELD_NAMES
        assert isinstance(payload["source_statuses"], list)
        assert isinstance(payload["courses"], list)
        assert payload["total"] == len(payload["courses"])
        assert payload["total"] > 0


class TestGitHubActionsWorkflowAndReadme:
    """Verify .github/workflows/update-courses.yml and README.md."""

    def test_workflow_exists_and_configures_schedule_scraper_and_pages_deploy(self) -> None:
        assert WORKFLOW_PATH.is_file(), ".github/workflows/update-courses.yml must exist"
        content = WORKFLOW_PATH.read_text(encoding="utf-8")

        assert "schedule:" in content
        assert "cron:" in content
        assert "workflow_dispatch:" in content
        assert "python -m scraper.cli --output-dir docs/data" in content
        assert "docs/data/courses.csv" in content
        assert "docs/data/courses.json" in content
        assert "deploy-pages" in content or "upload-pages-artifact" in content

    def test_readme_documents_usage_and_google_sheets_sync(self) -> None:
        assert README_PATH.is_file(), "README.md must exist"
        readme = README_PATH.read_text(encoding="utf-8")

        assert "python -m scraper.cli --output-dir docs/data" in readme
        assert "=IMPORTDATA(" in readme
        assert "臨床心理師" in readme
        for field_name in COURSE_FIELD_NAMES:
            assert field_name in readme, f"README.md should document field {field_name}"
