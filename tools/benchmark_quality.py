"""Deterministic quality benchmark for the psy-course website data + UI.

Measures the committed artifacts the site actually serves:
  docs/data/courses.json, docs/data/courses.csv, docs/index.html, docs/app.js

Primary metric: field_anomalies (lower is better) = hard field/link violations
+ placeholder values + unknown credits + dataset-level problems (duplicates,
stale rows, CSV/JSON mismatch, UI wiring errors).

No network, no time-of-day dependency: staleness is measured against the
dataset's own updated_at timestamp.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"
FIELDS = [
    "課程名稱",
    "主辦單位",
    "課程日期",
    "上課時間",
    "費用",
    "上課地點／方式",
    "報名連結",
    "是否有臨床心理師積分",
    "積分判斷依據段落",
    "資料來源平台",
    "建立時間",
    "報名期間",
]

PLACEHOLDER_RE = re.compile(r"詳見|不詳|待確認|暫無|依簡章公告")
MOJIBAKE_RE = re.compile(r"â€|Ã¤|Ã¨|Ã©|Â\x80|Ã¯")
ROC_DATE_RE = re.compile(r"(\d{3})/(\d{1,2})/(\d{1,2})")
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})[–\-~](\d{1,2}):(\d{2})$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NON_URL_CHARS_RE = re.compile(r"[\s\u4e00-\u9fff，。（）()]")


def parse_roc_date(text: str) -> dt.date | None:
    m = ROC_DATE_RE.fullmatch(text.strip())
    if not m:
        return None
    year, month, day = (int(g) for g in m.groups())
    if not 100 <= year <= 130:
        return None
    try:
        return dt.date(year + 1911, month, day)
    except ValueError:
        return None


def course_end_date(raw: str) -> dt.date | None:
    """Latest date mentioned in the 課程日期 field (single date or range)."""
    dates = [parse_roc_date(part) for part in re.split(r"[–\-~]", raw)]
    dates = [d for d in dates if d is not None]
    if not dates:
        return None
    return max(dates)


def link_is_valid(url: str) -> bool:
    if not url or not url.startswith(("http://", "https://")):
        return False
    if NON_URL_CHARS_RE.search(url):
        return False
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", parsed.netloc.lower()):
        return False
    if parsed.path in ("", "/") and not parsed.query:
        return False  # bare homepage is not a registration link
    return True


def check_course(record: dict) -> dict[str, int]:
    counts = {"hard": 0, "placeholder": 0, "unknown": 0, "link_bad": 0}
    for field in FIELDS:
        if field in ("上課時間", "費用", "報名期間"):
            continue  # emptiness handled by the placeholder loop below
        if field not in record or not str(record.get(field, "")).strip():
            counts["hard"] += 1

    name = str(record.get("課程名稱", ""))
    if name and (len(name) < 4 or MOJIBAKE_RE.search(name)):
        counts["hard"] += 1

    date_raw = str(record.get("課程日期", "")).strip()
    if date_raw and course_end_date(date_raw) is None:
        counts["hard"] += 1

    created = str(record.get("建立時間", "")).strip()
    if created and not ISO_DATE_RE.match(created):
        counts["hard"] += 1

    url = str(record.get("報名連結", "")).strip()
    if url and not link_is_valid(url):
        counts["hard"] += 1
        counts["link_bad"] += 1

    for field in ("上課時間", "費用", "報名期間"):
        val = str(record.get(field, "")).strip()
        if field == "上課時間" and val and not TIME_RE.match(val) and not PLACEHOLDER_RE.search(val):
            # present but malformed time (e.g. free-text)
            counts["hard"] += 1
        elif not val or PLACEHOLDER_RE.search(val):
            counts["placeholder"] += 1

    if str(record.get("是否有臨床心理師積分", "")).strip() == "未知":
        counts["unknown"] += 1
    return counts


def main() -> int:
    errors: list[str] = []
    try:
        payload = json.loads((DATA_DIR / "courses.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FATAL: cannot load courses.json: {exc}", file=sys.stderr)
        return 1

    courses = payload.get("courses", [])
    updated_raw = str(payload.get("updated_at", ""))
    try:
        updated_date = dt.datetime.strptime(updated_raw, "%Y-%m-%d %H:%M:%S").date()
    except ValueError:
        updated_date = None

    total_hard = total_placeholder = total_unknown = link_bad = 0
    duplicates = stale = 0
    seen: set[tuple[str, str]] = set()

    for record in courses:
        counts = check_course(record)
        total_hard += counts["hard"]
        total_placeholder += counts["placeholder"]
        total_unknown += counts["unknown"]
        link_bad += counts["link_bad"]
        key = (str(record.get("課程名稱", "")), str(record.get("課程日期", "")))
        if key in seen:
            duplicates += 1
        seen.add(key)
        if updated_date is not None:
            end = course_end_date(str(record.get("課程日期", "")))
            if end is not None and end < updated_date:
                stale += 1

    # CSV/JSON consistency
    csv_mismatch = 0
    try:
        with (DATA_DIR / "courses.csv").open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.reader(fh))
        header, data_rows = rows[0], rows[1:]
        if header != FIELDS:
            csv_mismatch += 1
        if len(data_rows) != len(courses):
            csv_mismatch += 1
        else:
            for csv_row, record in zip(data_rows, courses):
                if [record.get(f, "") for f in FIELDS] != csv_row:
                    csv_mismatch += 1
                    if csv_mismatch >= 5:
                        break
    except OSError:
        csv_mismatch += 1
        errors.append("courses.csv missing")

    # UI wiring
    ui_errors = 0
    index_html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    app_js = (ROOT / "docs" / "app.js").read_text(encoding="utf-8")
    if "courses.json" not in app_js:
        ui_errors += 1
    if "app.js" not in index_html:
        ui_errors += 1
    for field in FIELDS:
        if field not in app_js:
            ui_errors += 1
    try:
        proc = subprocess.run(
            ["node", "--check", str(ROOT / "docs" / "app.js")],
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            ui_errors += 1
            errors.append(f"app.js syntax error: {proc.stderr.decode()[:200]}")
    except (OSError, subprocess.TimeoutExpired):
        pass  # node unavailable: skip, do not fail

    anomalies = (
        total_hard + total_placeholder + total_unknown + duplicates + stale + csv_mismatch + ui_errors
    )
    print(f"METRIC field_anomalies={anomalies}")
    print(f"METRIC link_invalid={link_bad}")
    print(f"METRIC placeholders={total_placeholder}")
    print(f"METRIC unknown_credits={total_unknown}")
    print(f"METRIC duplicates={duplicates}")
    print(f"METRIC stale={stale}")
    print(f"METRIC csv_mismatch={csv_mismatch}")
    print(f"METRIC ui_errors={ui_errors}")
    print(f"METRIC courses_total={len(courses)}")
    for err in errors:
        print(f"WARN {err}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
