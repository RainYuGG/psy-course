"""Cross-source course deduplication, TACLIP whitelist matching, and field merging."""

from __future__ import annotations

from dataclasses import replace
from difflib import SequenceMatcher
import re

from scraper.extractor import evaluate_clinical_credit, normalize_roc_date
from scraper.models import CourseRecord
from scraper.sources.taclip_whitelist import TACLIP_WHITELIST_PLATFORM, WhitelistEntry

_LEADING_BRACKET_TAG_RE = re.compile(r"^\s*(?:[【\[（(][^】\]）)]{1,16}[】\]）)]\s*)+")
_INLINE_TAG_BRACKET_RE = re.compile(
    r"[【\[（(]\s*(?:轉知|活動轉知|課程轉知|研習|講座|工作坊|公告|實體|線上|視訊|"
    r"實體課程|線上課程|實體上課|視訊課程|網路課程|繼續教育|免費|兩日課程|一日課程|"
    r"半日課程|全天|半天|含實作|報名中|熱烈報名中)[^】\]）)]{0,8}[】\]）)]"
)
_PREFIX_SEP_RE = re.compile(r"\s*[-－–—：:]\s*")
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
_NON_WORD_RE = re.compile(r"[^\u4e00-\u9fffa-z0-9]+")
_LEADING_YEAR_RE = re.compile(r"^\d{3,4}年(?:度)?")

_EXTERNAL_FORM_HOSTS = (
    "forms.gle",
    "docs.google.com/forms",
    "beclass.com",
    "accupass.com",
    "kktix.com",
    "mental-health.gov.taipei",
    "surveycake.com",
)
_DEFAULT_MISSING_EVIDENCE = "課程公告內文未提及繼續教育積分資訊"


def _extract_start_date(course_date: str) -> str:
    """Return the start date (`YYY/MM/DD`) from a single or range ROC date string."""
    raw = (course_date or "").strip()
    if not raw:
        return ""
    first_part = re.split(r"[–—\-~～]", raw)[0].strip()
    return normalize_roc_date(first_part) or first_part


def normalize_course_key(name: str) -> str:
    """Normalize a course title for cross-source fuzzy/substring deduplication."""
    text = (name or "").strip()
    if not text:
        return ""

    # Strip leading bracketed tags such as 【轉知】 or [研習]
    text = _LEADING_BRACKET_TAG_RE.sub("", text).strip()
    # Strip inline delivery/category bracket tags such as （線上課程）
    text = _INLINE_TAG_BRACKET_RE.sub("", text).strip()

    # Strip organizer or announcement prefixes before '-' or '：' when the prefix contains CJK characters
    parts = _PREFIX_SEP_RE.split(text, maxsplit=1)
    if len(parts) == 2:
        prefix, remainder = parts[0].strip(), parts[1].strip()
        remainder_clean = _NON_WORD_RE.sub("", remainder.lower())
        if _CJK_CHAR_RE.search(prefix) and len(remainder_clean) >= 4:
            text = remainder

    lowered = text.lower()
    return _NON_WORD_RE.sub("", lowered)


def _strip_leading_year(key: str) -> str:
    stripped = _LEADING_YEAR_RE.sub("", key)
    return stripped if len(stripped) >= 4 else key


def _similarity_score(key_a: str, key_b: str) -> float:
    """Return a similarity score in [0.0, 1.0] if two normalized keys represent the same course."""
    if not key_a or not key_b:
        return 0.0
    if key_a == key_b:
        return 1.0

    core_a = _strip_leading_year(key_a)
    core_b = _strip_leading_year(key_b)
    if core_a == core_b:
        return 0.98

    shorter_len = min(len(key_a), len(key_b))
    if shorter_len >= 4 and (key_a in key_b or key_b in key_a):
        return 0.92

    core_shorter_len = min(len(core_a), len(core_b))
    if core_shorter_len >= 4 and (core_a in core_b or core_b in core_a):
        return 0.90

    ratio = SequenceMatcher(None, core_a, core_b).ratio()
    if ratio >= 0.72:
        return ratio
    return 0.0


def match_whitelist_entry(
    course: CourseRecord,
    whitelist: list[WhitelistEntry],
) -> WhitelistEntry | None:
    """Match a scraped CourseRecord against TACLIP whitelist entries by start date and normalized name."""
    if not whitelist:
        return None

    course_start = _extract_start_date(course.course_date)
    if not course_start:
        return None

    course_key = normalize_course_key(course.course_name)
    if not course_key:
        return None

    best_entry: WhitelistEntry | None = None
    best_score = 0.0

    for entry in whitelist:
        entry_start = _extract_start_date(entry.start_date_roc)
        if not entry_start or entry_start != course_start:
            continue

        entry_key = normalize_course_key(entry.course_name)
        score = _similarity_score(course_key, entry_key)
        if score > best_score:
            best_score = score
            best_entry = entry

    return best_entry


def _is_whitelist_only_record(record: CourseRecord) -> bool:
    url = record.registration_url or ""
    return (
        record.source_platform == TACLIP_WHITELIST_PLATFORM
        or "taclip.org.tw/checked-list/?q=" in url
        or "google.com/search?q=" in url
    )


def _url_priority(url: str) -> int:
    u = (url or "").strip()
    if not u:
        return 0
    lower = u.lower()
    if "taclip.org.tw/checked-list/?q=" in lower or "google.com/search?q=" in lower:
        return 10
    if any(host in lower for host in _EXTERNAL_FORM_HOSTS):
        return 100
    return 60

def _credit_status_priority(status: str) -> int:
    if status == "是":
        return 3
    if status == "否":
        return 2
    return 1


def _merge_evidence(ev_a: str, ev_b: str) -> str:
    clean_a = (ev_a or "").strip()
    clean_b = (ev_b or "").strip()
    if not clean_a:
        return clean_b
    if not clean_b or clean_a == clean_b:
        return clean_a
    if clean_a == _DEFAULT_MISSING_EVIDENCE:
        return clean_b
    if clean_b == _DEFAULT_MISSING_EVIDENCE:
        return clean_a

    # Prefer official TACLIP certification evidence first, optionally preserving detailed excerpt
    a_is_taclip = "台灣臨床心理學會審核通過" in clean_a or "TACP" in clean_a
    b_is_taclip = "台灣臨床心理學會審核通過" in clean_b or "TACP" in clean_b
    if a_is_taclip and not b_is_taclip:
        return f"{clean_a}；{clean_b}"
    if b_is_taclip and not a_is_taclip:
        return f"{clean_b}；{clean_a}"
    return clean_a if len(clean_a) >= len(clean_b) else clean_b


def _enrich_with_whitelist(
    course: CourseRecord,
    whitelist: list[WhitelistEntry],
) -> CourseRecord:
    if _is_whitelist_only_record(course):
        return replace(course)

    matched = match_whitelist_entry(course, whitelist)
    if matched is None:
        return replace(course)

    _, official_evidence = evaluate_clinical_credit(
        "",
        whitelist_match={"cert_no": matched.cert_no, "category": matched.category},
    )
    merged_evidence = _merge_evidence(official_evidence, course.credit_evidence)
    organizer = course.organizer
    if (not organizer or organizer == course.source_platform) and matched.organizer:
        organizer = matched.organizer

    return replace(
        course,
        organizer=organizer,
        has_clinical_credit="是",
        credit_evidence=merged_evidence,
    )


def _merge_two_records(first: CourseRecord, second: CourseRecord) -> CourseRecord:
    """Merge two duplicate CourseRecord entries, preferring detailed announcement fields."""
    first_is_wl = _is_whitelist_only_record(first)
    second_is_wl = _is_whitelist_only_record(second)

    if first_is_wl and not second_is_wl:
        detailed, secondary = second, first
    else:
        detailed, secondary = first, second

    course_name = detailed.course_name or secondary.course_name
    organizer = detailed.organizer
    if (not organizer or organizer == detailed.source_platform) and secondary.organizer:
        organizer = secondary.organizer

    # Prefer multi-day range (`YYY/MM/DD–YYY/MM/DD`) over single-day start date
    if "–" in (detailed.course_date or ""):
        course_date = detailed.course_date
    elif "–" in (secondary.course_date or ""):
        course_date = secondary.course_date
    else:
        course_date = detailed.course_date or secondary.course_date

    is_fb_time = lambda v: not v or v in ("詳見開課單位簡章", "詳見簡章")
    course_time = (
        detailed.course_time
        if not is_fb_time(detailed.course_time)
        else (secondary.course_time if not is_fb_time(secondary.course_time) else (detailed.course_time or secondary.course_time))
    )
    fee = detailed.fee or secondary.fee

    is_fb_loc = lambda v: not v or "依簡章公告" in v
    loc_candidates = [v for v in (detailed.location_mode, secondary.location_mode) if not is_fb_loc(v)]
    location_mode = max(loc_candidates, key=len) if loc_candidates else (detailed.location_mode or secondary.location_mode)
    registration_url = (
        detailed.registration_url
        if _url_priority(detailed.registration_url) >= _url_priority(secondary.registration_url)
        else secondary.registration_url
    )

    has_clinical_credit = (
        detailed.has_clinical_credit
        if _credit_status_priority(detailed.has_clinical_credit)
        >= _credit_status_priority(secondary.has_clinical_credit)
        else secondary.has_clinical_credit
    )
    credit_evidence = _merge_evidence(detailed.credit_evidence, secondary.credit_evidence)
    source_platform = detailed.source_platform or secondary.source_platform
    created_at = detailed.created_at or secondary.created_at
    registration_period = detailed.registration_period or secondary.registration_period

    return CourseRecord(
        course_name=course_name,
        organizer=organizer,
        course_date=course_date,
        course_time=course_time,
        fee=fee,
        location_mode=location_mode,
        registration_url=registration_url,
        has_clinical_credit=has_clinical_credit,
        credit_evidence=credit_evidence,
        source_platform=source_platform,
        created_at=created_at,
        registration_period=registration_period,
    )


def _date_sort_key(record: CourseRecord) -> tuple[tuple[int, int, int], str, str]:
    start = _extract_start_date(record.course_date)
    m = re.match(r"^(\d{2,3})/(\d{2})/(\d{2})$", start)
    if m:
        ymd = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    else:
        ymd = (0, 0, 0)
    return (ymd, record.course_date or "", record.course_name or "")


def deduplicate_and_merge(
    courses: list[CourseRecord],
    whitelist: list[WhitelistEntry] | None = None,
) -> list[CourseRecord]:
    """Enrich courses with TACLIP whitelist, merge cross-source duplicates, and sort by date descending."""
    wl = whitelist or []
    enriched = [_enrich_with_whitelist(course, wl) for course in courses]

    merged_list: list[CourseRecord] = []
    for candidate in enriched:
        cand_start = _extract_start_date(candidate.course_date)
        cand_key = normalize_course_key(candidate.course_name)

        matched_idx: int | None = None
        for idx, existing in enumerate(merged_list):
            exist_start = _extract_start_date(existing.course_date)
            exist_key = normalize_course_key(existing.course_name)

            if cand_start and exist_start:
                if cand_start == exist_start and _similarity_score(cand_key, exist_key) > 0.0:
                    matched_idx = idx
                    break
            elif not cand_start and not exist_start and cand_key and cand_key == exist_key:
                matched_idx = idx
                break

        if matched_idx is not None:
            merged_list[matched_idx] = _merge_two_records(merged_list[matched_idx], candidate)
        else:
            merged_list.append(candidate)

    # shortcut: drop standalone whitelist rows without real announcement URLs and keep ROC year >= 115 (2026+)
    active_list = [
        r
        for r in merged_list
        if not _is_whitelist_only_record(r) and _date_sort_key(r)[0][0] >= 115
    ]
    active_list.sort(key=_date_sort_key, reverse=True)
    return active_list
