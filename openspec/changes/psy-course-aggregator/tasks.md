# Tasks

## Global Constraints

- **12 Required Course Fields (exact order and header names in CSV and JSON):**
  1. `課程名稱`
  2. `主辦單位`
  3. `課程日期` (ROC slash format `YYY/MM/DD`, e.g. `115/06/25`, or range `115/09/12–115/09/13`)
  4. `上課時間` (e.g. `13:30–16:30` or empty string if unspecified)
  5. `費用` (e.g. `免費`, `$800`, `$1500（含教材）`, or empty string if unspecified)
  6. `上課地點／方式` (e.g. `線上`, `北醫進修推廣部`, `實體、線上混合`)
  7. `報名連結` (clickable registration URL; falls back to the announcement detail URL if no external registration form URL is present)
  8. `是否有臨床心理師積分` (strictly one of: `是`, `否`, `未知`)
  9. `積分判斷依據段落` (verbatim sentence/excerpt from the source page or official `taclip` whitelist certification number `台灣臨床心理學會審核通過（認證字號：TACP...）`)
  10. `資料來源平台` (human-readable association/platform name, e.g. `中華民國臨床心理師公會全國聯合會`)
  11. `建立時間` (scrape date in `YYYY-MM-DD` format, e.g. `2026-11-08`)
  12. `報名期間` (registration period if stated on page, otherwise empty string)
- **Zero Paid API Keys:** Field extraction MUST use deterministic Python HTML DOM + regex rules only (`httpx`, `beautifulsoup4`, `lxml`), with no LLM API calls.
- **CSV Encoding:** `docs/data/courses.csv` MUST be encoded as `utf-8-sig` (UTF-8 with BOM) so Excel opens Chinese text cleanly and Google Sheets `=IMPORTDATA()` can ingest it directly.

## Task 1: Project Foundation, 12-Field Course Model, and Rule-Based Extractor

- [x] 1.1 建立 Python 套件與目錄結構（`scraper/__init__.py`、`docs/data/`、`tests/`、`requirements.txt`、`pyproject.toml`）
- [x] 1.2 實作 `scraper/models.py` 定義 12 個指定欄位的 `CourseRecord` dataclass、欄位順序常數 `COURSE_FIELD_NAMES` 與 `to_dict()` / `to_csv_row()` 方法
- [x] 1.3 實作 `scraper/extractor.py` 純規則抽取引擎與 `tests/test_extractor.py` 單元測試

### Task 1 Details & Interfaces

- **Files to create:**
  - `requirements.txt` (`httpx>=0.27.0`, `beautifulsoup4>=4.12.0`, `lxml>=5.0.0`, `pytest>=8.0.0`)
  - `pyproject.toml` (configuring `pytest` pythonpath = `["."]`)
  - `scraper/__init__.py`
  - `scraper/models.py`:
    - `COURSE_FIELD_NAMES: list[str]` containing the exact 12 Chinese field names in order.
    - `CREDIT_STATUS_VALUES = ("是", "否", "未知")`
    - `@dataclass class CourseRecord`: fields `course_name: str`, `organizer: str`, `course_date: str`, `course_time: str = ""`, `fee: str = ""`, `location_mode: str = ""`, `registration_url: str = ""`, `has_clinical_credit: str = "未知"`, `credit_evidence: str = ""`, `source_platform: str = ""`, `created_at: str = ""`, `registration_period: str = ""`.
    - `CourseRecord.to_dict() -> dict[str, str]` keyed by the 12 Chinese field names in `COURSE_FIELD_NAMES` order, plus `CourseRecord.from_dict(data: Mapping[str, str]) -> CourseRecord`.
    - `CourseRecord.to_csv_row() -> list[str]` returning values in `COURSE_FIELD_NAMES` order.
  - `scraper/extractor.py`:
    - `normalize_roc_date(text: str) -> str`: extracts single or multi-day dates from strings like `2026/07/05`, `2026-01-09 ~ 2026-01-24`, `115年7月29日（星期三）`, `115年9月12日-9月13日`, `115.06.25` and returns `YYY/MM/DD` (e.g. `115/07/05` or `115/09/12–115/09/13`). Years $\ge 1912$ convert via $Y - 1911$.
    - `extract_time_range(text: str) -> str`: extracts `HH:MM–HH:MM` (normalized with en-dash `–`) from patterns like `9:30-12:30`, `09:30~17:00`, `13:30至16:30`, or single start time `15:00` when labeled after `時間：`.
    - `extract_fee(text: str) -> str`: extracts fee description from labels (`費用`, `報名費`, `收費標準`, `課程費用`) or standalone `免費` / `免收報名費` patterns.
    - `extract_location_mode(title: str, text: str) -> str`: extracts labeled location/mode (`地點`, `辦理地點`, `上課地點`, `辦理方式`, `上課方式`) and detects `線上` / `實體` keywords (e.g. `【實體上課】`, `線上課程`, `Zoom`, `Google Meet`).
    - `extract_registration_period(text: str) -> str`: extracts labeled registration period (`報名期間`, `報名日期`, `即日起至...`) or date range before `開放報名`.
    - `extract_registration_url(html: str, detail_url: str) -> str`: finds registration links in HTML (prioritizing links near `報名` labels or known form hosts `forms.gle`, `docs.google.com/forms`, `beclass.com`, `accupass.com`, `kktix.com`, `mental-health.gov.taipei`), resolving relative URLs and falling back to `detail_url`. Excludes social share links (`facebook.com/share`, `twitter.com/share`, `line.naver.jp`, `telegram.me`, `linkedin.com`).
    - `evaluate_clinical_credit(text: str, whitelist_match: dict[str, str] | None = None) -> tuple[str, str]`: returns `(has_clinical_credit, credit_evidence)`:
      1. If `whitelist_match` is provided (with `cert_no` and optional `category`), returns `("是", f"台灣臨床心理學會審核通過（認證字號：{cert_no}，性質：{category}）")` (or without `，性質：...` if empty).
      2. Otherwise scans sentences/lines mentioning `積分`, `學分`, or `繼續教育`:
         - Explicit negation (`不申請`, `無申請`, `恕不提供`, `不提供積分`) -> `("否", verbatim_sentence)`
         - Mentions `臨床心理師` (or `臨床、諮商心理師` / `臨床及諮商心理師`) -> `("是", verbatim_sentence)`
         - Mentions only other professions (`諮商心理師`, `社工師`, `護理師`, `精神科專科醫師`, `職能治療師`) without `臨床` -> `("否", verbatim_sentence)`
         - Ambiguous `心理師` (`已申請心理師積分`, `心理師繼續教育積分申請中`) without specifying `臨床` -> `("未知", verbatim_sentence)`
      3. If no sentence mentions credits -> `("未知", "課程公告內文未提及繼續教育積分資訊")`.
    - `extract_course_from_page(title: str, html: str, detail_url: str, source_platform: str, default_organizer: str = "", created_at: str = "", whitelist_match: dict[str, str] | None = None) -> CourseRecord`: combines all rules to produce a populated `CourseRecord`.
  - `tests/test_extractor.py`: unit tests covering all extractor functions, real ATCP and Psychoanalysis text samples, and all 4 credit judgment scenarios.

## Task 2: HTTP Client, TACLIP Credit Whitelist, and 15 A-Class Source Scrapers

- [ ] 2.1 實作 `scraper/http_client.py` 共用 HTTP 抓取工具（含 Timeout、Retry、User-Agent 與特定站點 SSL 驗證容錯）與 `scraper/sources/base.py` `BaseSourceScraper` 介面
- [ ] 2.2 實作 `scraper/sources/taclip_whitelist.py` 抓取台灣臨床心理學會 `taclip.org.tw/checked-list/` 審核通過課程總表與最新消息
- [ ] 2.3 實作臨床心理師公會全聯會爬蟲 `scraper/sources/atcp.py`（抓取 `storytopic=12` 轉知活動訊息與 `storytopic=15` 研習活動公告並過濾非課程訊息）
- [ ] 2.4 實作第一批學會爬蟲（`atpt` 遊戲治療、`tcpu` 諮商全聯會、`twcpa` 諮商學會、`psychoanalysis` 精神分析學會、`sop` 精神醫學會）
- [ ] 2.5 實作第二批學會爬蟲（`rmdaroc` 復健醫學、`tap` 心理治療、`tpos` 心理腫瘤、`iaptc` 網路成癮、`tasctaiwan` 性諮商、`acft_eft` 伴侶家族、`ecata` 表創藝術、`mindfulness` 正念、`tsos` 自殺防治）與 `tests/test_sources.py`

### Task 2 Details & Interfaces

- **Files to create:**
  - `scraper/http_client.py`:
    - `HttpClient`: wraps `httpx.Client` with realistic browser `User-Agent`, configurable timeout (default 15.0s), retries (default 2), and automatic fallback to `verify=False` when an SSL certificate verification error occurs (needed for legacy Taiwanese association servers).
  - `scraper/sources/__init__.py`: exports `ALL_SCRAPERS` registry and `fetch_all_sources(client, created_at) -> tuple[list[CourseRecord], list[dict]]`.
  - `scraper/sources/base.py`:
    - `NON_COURSE_KEYWORDS`: tuple of keywords to filter out job postings and administrative notices (`誠徵`, `徵才`, `招募`, `職缺`, `錄取名單`, `理監事`, `會員大會紀錄`, `會議紀錄`, `法規`, `辦法修正`, `獎學金`, `徵稿`, `休假公告`).
    - `is_likely_course_title(title: str) -> bool`: returns `False` if title matches non-course keywords without course indicators (`課程`, `工作坊`, `研討會`, `講座`, `訓練`, `研習`, `培訓`, `論壇`, `演講`, `督導`).
    - `BaseSourceScraper`: base class with `source_id: str`, `source_name: str`, `default_organizer: str`, `base_url: str`, and `scrape(client: HttpClient, created_at: str) -> list[CourseRecord]`, plus `safe_scrape(client: HttpClient, created_at: str) -> tuple[list[CourseRecord], dict[str, str]]` which catches any network/parsing exception and returns `([], {"source": self.source_name, "status": "error", "error": str(exc)})` so a single site failure never aborts the pipeline.
  - `scraper/sources/taclip_whitelist.py`:
    - Parses `<table id="footable_3078">` (or any table with headers `認證字號`, `課程性質`, `開始日期`, `開課單位`, `課程名稱`) on `https://taclip.org.tw/checked-list/` into both:
      1. `WhitelistEntry` records (`cert_no`, `category`, `start_date_roc`, `organizer`, `course_name`) for cross-referencing, and
      2. `CourseRecord` objects with `has_clinical_credit="是"`, `credit_evidence="台灣臨床心理學會審核通過（認證字號：...，性質：...）"`, `source_platform="台灣臨床心理學會（審核通過課程總表）"`, and a fallback search/listing `registration_url`.
    - Also scrapes `https://taclip.org.tw/` course announcements (excluding `徵才專區`).
  - `scraper/sources/atcp.py`:
    - Scrapes `https://www.atcp.org.tw/modules/news/index.php?storytopic=12` (轉知活動訊息) and `storytopic=15` (研習活動公告), fetches detail pages `article.php?storyid=...`, extracts the main content block after `NEWS`, and builds `CourseRecord` items.
  - `scraper/sources/catalog_scrapers.py`:
    - Dedicated/configured scrapers for the remaining A-class sites (`atpt.org.tw`, `tcpu.org.tw`, `twcpa.org.tw/recentcourses`, `psychoanalysis.org.tw`, `sop.org.tw`, `sites.google.com/rmdaroc.org/signup/首頁`, `tap.org.tw`, `tpos-society.org`, `iaptc.asia.edu.tw`, `tasctaiwan.tw`, `acft.org.tw`, `asia-eft.com`, `ecata.org.tw`, `mindfulness.org.tw`, `tsos.org.tw`).
  - `tests/test_sources.py`:
    - Offline HTML fixture tests verifying `taclip_whitelist` table parsing, `atcp` list + detail extraction, non-course filtering (`徵才` exclusion), and fault isolation when a site returns HTTP 503 (`tsos.org.tw`).

## Task 3: Cross-Source Deduplicator, CSV/JSON Exporter, and CLI Runner

- [ ] 3.1 實作 `scraper/deduplicator.py` 依正規化課程名稱與民國日期去重，並將 `taclip` 審核通過紀錄與各學會詳細公告互補合併
- [ ] 3.2 實作 `scraper/exporter.py` 產出 `docs/data/courses.json` 與 `docs/data/courses.csv`（UTF-8 with BOM 嚴格 12 欄位）
- [ ] 3.3 實作 `scraper/cli.py` CLI 入口支援一鍵執行全站抓取、本地測試與產出檔案驗證，並撰寫 `tests/test_pipeline.py`

### Task 3 Details & Interfaces

- **Files to create:**
  - `scraper/deduplicator.py`:
    - `normalize_course_key(name: str) -> str`: strips punctuation, brackets, prefixes (like organizer prefix before `-`), and whitespace for fuzzy/substring matching.
    - `match_whitelist_entry(course: CourseRecord, whitelist: list[WhitelistEntry]) -> WhitelistEntry | None`: matches a scraped `CourseRecord` against `taclip` whitelist entries by start date (`course.course_date.split("–")[0] == entry.start_date_roc`) and normalized course name containment/similarity.
    - `deduplicate_and_merge(courses: list[CourseRecord], whitelist: list[WhitelistEntry] | None = None) -> list[CourseRecord]`:
      1. First enriches any non-whitelist `CourseRecord` that matches `whitelist` so its `has_clinical_credit` becomes `"是"` and `credit_evidence` includes the official `TACP...` certification number.
      2. Merges duplicate records sharing the same start date and normalized course name (or where a `taclip` whitelist-only record matches a detailed scraper record), preferring non-empty `course_time`, `fee`, `location_mode`, external `registration_url`, and `registration_period` from the detailed announcement while keeping `has_clinical_credit="是"` and the `TACP` certification evidence.
      3. Sorts output records by `course_date` descending (newest/upcoming first).
  - `scraper/exporter.py`:
    - `export_courses_csv(courses: list[CourseRecord], csv_path: Path) -> None`: writes `csv_path` with `encoding="utf-8-sig"`, header row `COURSE_FIELD_NAMES`, and one row per `CourseRecord`.
    - `export_courses_json(courses: list[CourseRecord], statuses: list[dict], json_path: Path, updated_at: str) -> None`: writes UTF-8 JSON with `{ "updated_at": updated_at, "total": len(courses), "fields": COURSE_FIELD_NAMES, "source_statuses": statuses, "courses": [c.to_dict() for c in courses] }`.
  - `scraper/cli.py`:
    - `main(argv: list[str] | None = None) -> int`: CLI supporting `--output-dir docs/data` and `--offline-seed` (or live scrape with fallback), running the scrapers, deduplicating, and writing `docs/data/courses.csv` and `docs/data/courses.json`.
  - Run `python3 -m scraper.cli` (or seed run) so `docs/data/courses.csv` and `docs/data/courses.json` are generated with real scraped data from the reachable A-class sites.
  - `tests/test_pipeline.py`: tests `deduplicate_and_merge`, `export_courses_csv` (verifying UTF-8 BOM bytes `\xef\xbb\xbf` and exact 12 column headers), `export_courses_json`, and `cli.main`.

## Task 4: GitHub Pages Course Catalog Web GUI and Scheduled GitHub Actions Workflow

- [ ] 4.1 實作 `docs/index.html`、`docs/style.css` 與 `docs/app.js` 響應式查詢介面（支援臨床積分是／未知／否、線上／實體、免費、月份、來源平台、關鍵字即時篩選）
- [ ] 4.2 於網頁 GUI 實作「展開檢視積分判斷依據段落原文」、「一鍵下載 UTF-8 BOM CSV」及「複製 Google Sheets `=IMPORTDATA()` 同步公式與說明視窗」
- [ ] 4.3 建立 `.github/workflows/update-courses.yml` 設定每日定時執行爬蟲、更新 `docs/data/` 並部署 GitHub Pages，並撰寫 `tests/test_ui_and_workflow.py`

### Task 4 Details & Interfaces

- **Files to create:**
  - `docs/index.html`:
    - Clean, responsive Traditional Chinese interface for clinical psychologists and students (`臨床心理師繼續教育課程彙整查詢平台`).
    - Filter controls:
      - Keyword search input (`#filter-keyword`: searches course name, organizer, location, evidence)
      - Clinical credit filter (`#filter-credit`: 全部 / 是 / 未知 / 否)
      - Attendance mode filter (`#filter-mode`: 全部 / 線上 / 實體)
      - Fee filter (`#filter-fee`: 全部 / 免費 / 付費)
      - Month filter (`#filter-month`: dynamically populated from `課程日期` `YYY/MM`)
      - Source platform filter (`#filter-source`: dynamically populated from `資料來源平台`)
    - Action bar:
      - Course count badge (`#course-count`), last updated timestamp (`#last-updated`), source status summary (`#source-status-summary`)
      - Direct download link/button for `./data/courses.csv` (`#btn-download-csv`)
      - Button to open Google Sheets sync helper modal/panel (`#btn-sheets-sync`) displaying the ready-to-copy `=IMPORTDATA(".../data/courses.csv")` formula and step-by-step instructions.
    - Table (`#courses-table`) displaying the 12 fields clearly, with color-coded badges for `是否有臨床心理師積分` (`是` green, `未知` amber, `否` gray), expandable/collapsible `積分判斷依據段落`, and clickable `報名連結` (`target="_blank" rel="noopener noreferrer"`).
  - `docs/style.css`: responsive styling (desktop table + mobile card/scroll layout, clear typography, accessible badge contrast).
  - `docs/app.js`: fetches `./data/courses.json`, renders filter options and table rows, filters in real time on input/change events, handles `=IMPORTDATA(...)` URL construction from `window.location.href` and clipboard copy, and supports client-side CSV export of currently filtered rows in addition to full `courses.csv` download.
  - `.github/workflows/update-courses.yml`:
    - Triggers on `schedule` (daily cron, e.g. `0 22 * * *` UTC = 06:00 Taiwan time) and `workflow_dispatch`.
    - Installs Python 3.11 + `requirements.txt`, runs `python -m scraper.cli --output-dir docs/data`, commits updated `docs/data/courses.csv` and `docs/data/courses.json` if changed, and deploys `docs/` to GitHub Pages.
  - `README.md`: concise usage, local development, and Google Sheets synchronization guide.
  - `tests/test_ui_and_workflow.py`: verifies `docs/index.html`, `docs/app.js`, `docs/style.css`, `docs/data/courses.csv`, `docs/data/courses.json`, and `.github/workflows/update-courses.yml` exist and contain all required filter controls, 12 field headers, and workflow triggers.
