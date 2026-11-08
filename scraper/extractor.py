"""Deterministic DOM + regex rule-based extractor for Taiwanese psychology courses."""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.models import CourseRecord

# Date patterns: support ROC 3-digit years (110-130) and Western 4-digit years (1912-2099)
_DATE_TOKEN_PATTERN = (
    r"(?P<y1>\d{3,4})\s*(?:年|[./-])\s*(?P<m1>\d{1,2})\s*(?:月|[./-])\s*(?P<d1>\d{1,2})\s*日?"
    r"(?:\s*[（(][^）)\d]{1,4}[）)])?"
)
_DATE_RANGE_REGEX = re.compile(
    _DATE_TOKEN_PATTERN
    + r"(?:\s*(?:[~～\-–—至到]|(?:\d{1,2}:\d{2}\s*[~～\-–—至到]))\s*"
    + r"(?:(?P<y2>\d{3,4})\s*(?:年|[./-])\s*)?"
    + r"(?P<m2>\d{1,2})\s*(?:月|[./-])\s*(?P<d2>\d{1,2})\s*日?)?"
)

_COURSE_DATE_LABEL_REGEX = re.compile(
    r"(?:課程日期|上課日期|活動日期|舉辦日期|研習日期|日期|課程時間|上課時間|活動時間|時間)\s*[：:]\s*([^\n]+)"
)
_REGISTRATION_LINE_KEYWORDS = ("報名期間", "報名日期", "報名截止", "截止日", "即日起至")

_TIME_RANGE_REGEX = re.compile(
    r"(?<!\d)([0-2]?\d:[0-5]\d)\s*[~～\-–—至到]\s*([0-2]?\d:[0-5]\d)(?!\d)"
)
_SINGLE_TIME_AFTER_LABEL_REGEX = re.compile(
    r"(?:上課時間|活動時間|課程時間|時間)\s*[：:][^\n]*?(?<!\d)([0-2]?\d:[0-5]\d)(?!\d)"
)

_FEE_LABEL_REGEX = re.compile(
    r"(?:課程費用|報名費用|報名費|收費標準|費用)\s*[：:]\s*([^\n。；;]+)"
)
_FREE_STANDALONE_REGEX = re.compile(r"(?:免收報名費|免費參加|免費報名|全程免費|費用全免|免費)")

_LOCATION_LABEL_REGEX = re.compile(
    r"(?:上課地點|辦理地點|活動地點|講座地點|研習地點|地點|辦理方式|上課方式|進行方式)\s*[：:]\s*([^\n]+)"
)
_ONLINE_KEYWORDS_REGEX = re.compile(
    r"(?:線上(?:課程|視訊|授課|講座|工作坊|研討會|同步|上課|進行|辦理)?|視訊(?:課程|講座|上課|會議)?|Zoom|Google\s*Meet|Webex|Teams|網路直播)",
    re.IGNORECASE,
)
_IN_PERSON_KEYWORDS_REGEX = re.compile(r"(?:實體(?:課程|上課|講座|工作坊|辦理|進行)?)")

_REG_PERIOD_LABEL_REGEX = re.compile(
    r"(?:報名期間|報名日期|報名時間|報名期限|報名起訖)\s*[：:]\s*([^\n。]+)"
)
_REG_PERIOD_IMMEDIATE_REGEX = re.compile(
    r"(即日起至\s*[^\n。，,；;（）()]{3,30}?(?:止|前)?)(?=[。，,；;\s\n]|$)"
)
_REG_PERIOD_OPEN_REGEX = re.compile(
    r"((?:\d{3,4}\s*[年./-]\s*\d{1,2}\s*[月./-]\s*\d{1,2}\s*日?\s*(?:[~～\-–—至到]\s*(?:\d{3,4}\s*[年./-]\s*)?\d{1,2}\s*[月./-]\s*\d{1,2}\s*日?)?)\s*開放報名)"
)

_ORGANIZER_LABEL_REGEX = re.compile(
    r"(?:主辦單位|開課單位|辦理單位|主辦|承辦單位)\s*[：:]\s*([^\n。；;]+)"
)

_KNOWN_FORM_HOSTS = (
    "forms.gle",
    "docs.google.com/forms",
    "beclass.com",
    "accupass.com",
    "kktix.com",
    "mental-health.gov.taipei",
    "surveycake.com",
)

_EXCLUDED_SHARE_PATTERNS = (
    "facebook.com/share",
    "facebook.com/sharer",
    "twitter.com/share",
    "twitter.com/intent",
    "line.naver.jp",
    "social-plugins.line.me",
    "telegram.me",
    "t.me/share",
    "linkedin.com",
    "mailto:",
    "javascript:",
)

_CREDIT_SENTENCE_KEYWORDS = ("積分", "學分", "繼續教育")
_CREDIT_NEGATION_KEYWORDS = ("不申請", "無申請", "恕不提供", "不提供積分", "無繼續教育積分", "未申請", "不提供繼續教育")
_OTHER_PROFESSION_KEYWORDS = (
    "諮商心理師",
    "社工師",
    "社會工作師",
    "護理師",
    "專科護理師",
    "精神科專科醫師",
    "醫師",
    "職能治療師",
    "物理治療師",
    "藥師",
)


def _to_roc_year(year: int) -> int:
    return year - 1911 if year >= 1912 else year


def _format_roc_ymd(year: int, month: int, day: int) -> str:
    roc_year = _to_roc_year(year)
    return f"{roc_year:03d}/{month:02d}/{day:02d}"


def _extract_date_from_segment(segment: str) -> str:
    for match in _DATE_RANGE_REGEX.finditer(segment):
        y1 = int(match.group("y1"))
        m1 = int(match.group("m1"))
        d1 = int(match.group("d1"))
        if not (1 <= m1 <= 12 and 1 <= d1 <= 31):
            continue
        if not (100 <= y1 <= 200 or 1912 <= y1 <= 2100):
            continue
        start_str = _format_roc_ymd(y1, m1, d1)
        m2_raw = match.group("m2")
        d2_raw = match.group("d2")
        if m2_raw and d2_raw:
            y2_raw = match.group("y2")
            y2 = int(y2_raw) if y2_raw else y1
            m2 = int(m2_raw)
            d2 = int(d2_raw)
            if 1 <= m2 <= 12 and 1 <= d2 <= 31:
                end_str = _format_roc_ymd(y2, m2, d2)
                if end_str != start_str:
                    return f"{start_str}–{end_str}"
        return start_str
    return ""


def normalize_roc_date(text: str) -> str:
    """Extract single or multi-day dates and normalize to ROC 'YYY/MM/DD' or 'YYY/MM/DD–YYY/MM/DD'."""
    if not text:
        return ""

    # 1. Prioritize explicitly labeled course/activity date lines
    for label_match in _COURSE_DATE_LABEL_REGEX.finditer(text):
        line_val = label_match.group(1)
        extracted = _extract_date_from_segment(line_val)
        if extracted:
            return extracted

    # 2. Scan lines that are not registration deadline lines
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(kw in stripped for kw in _REGISTRATION_LINE_KEYWORDS):
            continue
        extracted = _extract_date_from_segment(stripped)
        if extracted:
            return extracted

    # 3. Fallback to any date in the full text
    return _extract_date_from_segment(text)


def _pad_hhmm(hhmm: str) -> str:
    parts = hhmm.strip().split(":")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    return hhmm.strip()


def extract_time_range(text: str) -> str:
    """Extract 'HH:MM–HH:MM' (with en-dash) or single 'HH:MM' after a time label."""
    if not text:
        return ""

    match = _TIME_RANGE_REGEX.search(text)
    if match:
        start_t = _pad_hhmm(match.group(1))
        end_t = _pad_hhmm(match.group(2))
        return f"{start_t}–{end_t}"

    single_match = _SINGLE_TIME_AFTER_LABEL_REGEX.search(text)
    if single_match:
        return _pad_hhmm(single_match.group(1))

    return ""


def extract_fee(text: str) -> str:
    """Extract fee description from labels or standalone free-of-charge patterns."""
    if not text:
        return ""

    label_match = _FEE_LABEL_REGEX.search(text)
    if label_match:
        raw_fee = label_match.group(1).strip().rstrip("。；;，, ")
        if raw_fee:
            if (
                any(k in raw_fee for k in ("免收報名費", "免費"))
                or re.search(r"(?<![0-9,])0\s*元", raw_fee)
            ) and "$" not in raw_fee and not re.search(r"[1-9][\d,]*\s*元", raw_fee):
                return "免費"
            return raw_fee

    if _FREE_STANDALONE_REGEX.search(text):
        return "免費"

    return ""


def extract_location_mode(title: str, text: str) -> str:
    """Extract labeled location/mode or detect online/in-person keywords from title and text."""
    combined = f"{title or ''}\n{text or ''}"

    label_match = _LOCATION_LABEL_REGEX.search(text or "")
    if label_match:
        loc_value = label_match.group(1).strip().rstrip("。；; ")
        if loc_value:
            has_online = bool(_ONLINE_KEYWORDS_REGEX.search(loc_value))
            has_in_person = bool(_IN_PERSON_KEYWORDS_REGEX.search(loc_value))
            if has_online and has_in_person:
                return f"實體、線上混合（{loc_value}）" if loc_value not in ("實體、線上混合", "實體與線上同步") else loc_value
            return loc_value

    has_online_any = bool(_ONLINE_KEYWORDS_REGEX.search(combined))
    has_in_person_any = bool(_IN_PERSON_KEYWORDS_REGEX.search(combined))

    if has_online_any and has_in_person_any:
        return "實體、線上混合"
    if has_online_any:
        return "線上"
    if has_in_person_any:
        return "實體"
    return ""


def extract_registration_period(text: str) -> str:
    """Extract labeled registration period, '即日起至...', or '...開放報名'."""
    if not text:
        return ""

    label_match = _REG_PERIOD_LABEL_REGEX.search(text)
    if label_match:
        val = label_match.group(1).strip().rstrip("。；; ")
        if val:
            return val

    imm_match = _REG_PERIOD_IMMEDIATE_REGEX.search(text)
    if imm_match:
        return imm_match.group(1).strip().rstrip("。；;，, ")

    open_match = _REG_PERIOD_OPEN_REGEX.search(text)
    if open_match:
        return open_match.group(1).strip()

    return ""


def _is_excluded_url(href: str) -> bool:
    lower_href = href.lower().strip()
    if not lower_href or lower_href.startswith("#"):
        return True
    return any(pattern in lower_href for pattern in _EXCLUDED_SHARE_PATTERNS)


def extract_registration_url(html: str, detail_url: str) -> str:
    """Find registration URL in HTML, resolving relative URLs and falling back to detail_url."""
    if not html:
        return detail_url

    soup = BeautifulSoup(html, "lxml")
    candidates: list[tuple[int, str]] = []

    for anchor in soup.find_all("a", href=True):
        raw_href = str(anchor.get("href", "")).strip()
        if _is_excluded_url(raw_href):
            continue

        resolved = urljoin(detail_url, raw_href)
        if _is_excluded_url(resolved):
            continue

        lower_resolved = resolved.lower()
        anchor_text = anchor.get_text(" ", strip=True)
        parent_text = anchor.parent.get_text(" ", strip=True) if anchor.parent else ""
        context_text = f"{anchor_text} {parent_text}"

        # Priority 1: Known external registration form hosts
        if any(host in lower_resolved for host in _KNOWN_FORM_HOSTS):
            candidates.append((100, resolved))
            continue

        # Priority 2: Anchor text or surrounding label explicitly says 報名
        if any(kw in anchor_text for kw in ("報名", "註冊", "register", "signup", "sign up")):
            candidates.append((80, resolved))
            continue

        if any(kw in context_text for kw in ("報名網址", "報名連結", "報名表單", "線上報名", "網路報名", "報名方式")):
            candidates.append((70, resolved))
            continue

        if any(kw in lower_resolved for kw in ("register", "signup", "sign_up", "form", "enroll")):
            candidates.append((50, resolved))

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    return detail_url


def evaluate_clinical_credit(
    text: str,
    whitelist_match: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Evaluate clinical psychologist continuing education credit status and verbatim evidence."""
    # Tier 1: Official TACLIP whitelist match
    if whitelist_match and whitelist_match.get("cert_no"):
        cert_no = whitelist_match["cert_no"].strip()
        category = whitelist_match.get("category", "").strip()
        if category:
            return ("是", f"台灣臨床心理學會審核通過（認證字號：{cert_no}，性質：{category}）")
        return ("是", f"台灣臨床心理學會審核通過（認證字號：{cert_no}）")

    if not text:
        return ("未知", "課程公告內文未提及繼續教育積分資訊")

    # Split text into candidate sentences/lines
    raw_segments = re.split(r"[\n\r。！？!?；;]+", text)
    credit_sentences = [
        seg.strip()
        for seg in raw_segments
        if seg.strip() and any(kw in seg for kw in _CREDIT_SENTENCE_KEYWORDS)
    ]

    if not credit_sentences:
        return ("未知", "課程公告內文未提及繼續教育積分資訊")

    # Tier 2: Scan sentences mentioning credits
    for sentence in credit_sentences:
        # 2a. Explicit negation
        if any(neg in sentence for neg in _CREDIT_NEGATION_KEYWORDS):
            return ("否", sentence)

        # 2b. Mentions 臨床心理師 or 臨床+諮商心理師
        if (
            "臨床心理師" in sentence
            or re.search(r"臨床[、及與和/／]?諮商心理師", sentence)
            or re.search(r"諮商[、及與和/／]?臨床心理師", sentence)
        ):
            return ("是", sentence)

    for sentence in credit_sentences:
        # 2c. Mentions only other professions without 臨床
        if "臨床" not in sentence and any(prof in sentence for prof in _OTHER_PROFESSION_KEYWORDS):
            return ("否", sentence)

    # 2d. Ambiguous mention (e.g., 心理師繼續教育積分申請中 without specifying 臨床 or 諮商)
    return ("未知", credit_sentences[0])


def _extract_organizer(text: str, default_organizer: str, source_platform: str) -> str:
    match = _ORGANIZER_LABEL_REGEX.search(text or "")
    if match:
        org = match.group(1).strip().rstrip("。；; ")
        if org:
            return org
    return default_organizer or source_platform


def extract_course_from_page(
    title: str,
    html: str,
    detail_url: str,
    source_platform: str,
    default_organizer: str = "",
    created_at: str = "",
    whitelist_match: dict[str, str] | None = None,
) -> CourseRecord:
    """Combine all deterministic extraction rules to build a 12-field CourseRecord."""
    soup = BeautifulSoup(html or "", "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)

    clean_title = (title or "").strip()
    if not clean_title:
        heading = soup.find(["h1", "h2", "title"])
        clean_title = heading.get_text(" ", strip=True) if heading else "未命名課程"

    organizer = _extract_organizer(text, default_organizer, source_platform)
    course_date = normalize_roc_date(text) or normalize_roc_date(clean_title)
    course_time = extract_time_range(text)
    fee = extract_fee(text)
    location_mode = extract_location_mode(clean_title, text)
    registration_period = extract_registration_period(text)
    registration_url = extract_registration_url(html or "", detail_url)
    has_clinical_credit, credit_evidence = evaluate_clinical_credit(
        text, whitelist_match=whitelist_match
    )
    created_date = created_at or date.today().isoformat()

    return CourseRecord(
        course_name=clean_title,
        organizer=organizer,
        course_date=course_date,
        course_time=course_time,
        fee=fee,
        location_mode=location_mode,
        registration_url=registration_url,
        has_clinical_credit=has_clinical_credit,
        credit_evidence=credit_evidence,
        source_platform=source_platform,
        created_at=created_date,
        registration_period=registration_period,
    )
