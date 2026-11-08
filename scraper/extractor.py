"""Deterministic DOM + regex rule-based extractor for Taiwanese psychology courses."""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import parse_qs, unquote, urljoin, urlparse
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

# Label separators: "：", "】：" and a trailing "／" (value then sits on the next line).
_LABEL_SEP = r"(?:[：:]|】\s*[：:]?|／\s*$)"
# Labels preceded by 報名/截止 (報名日期, 報名時間, 報名截止日期) describe registration, not the course.
_COURSE_DATE_LABEL_REGEX = re.compile(
    r"(?<!報名)(?<!截止)(?:課程日期|上課日期|活動日期|舉辦日期|研習日期|日期|課程時間|上課時間|活動時間|時間)\s*"
    + _LABEL_SEP
    + r"\s*([^\n]+)",
    re.MULTILINE,
)
_REGISTRATION_LINE_KEYWORDS = (
    "報名期間",
    "報名日期",
    "報名時間",
    "報名起訖",
    "報名截止",
    "截止日",
    "即日起",
    "開放報名",
    "完成報名",
)

_TIME_RANGE_REGEX = re.compile(
    r"(?<!\d)([0-2]?\d[:：][0-5]\d)\s*[~～\-–—至到]\s*([0-2]?\d[:：][0-5]\d)(?!\d)"
)
_CHINESE_TIME_RANGE_REGEX = re.compile(
    r"(?<!\d)([0-2]?\d)\s*[時點]\s*([0-5]\d)?\s*分?\s*[~～\-–—至到]\s*([0-2]?\d)\s*[時點]\s*([0-5]\d)?\s*分?"
)
_SINGLE_TIME_AFTER_LABEL_REGEX = re.compile(
    r"(?:上課時間|活動時間|課程時間|時間)\s*(?:[：:]|】\s*[：:]?)[^\n]*?(?<!\d)([0-2]?\d[:：][0-5]\d)(?!\d)"
)
_OFFICE_HOURS_LINE_KEYWORDS = (
    "週一至週五",
    "周一至周五",
    "服務時間",
    "上班時間",
    "辦公時間",
    "秘書處時間",
    "聯絡時間",
)

_FEE_LABEL_REGEX = re.compile(r"(?:課程費用|報名費用|報名費|收費標準|費用)\s*" + _LABEL_SEP)
_FREE_STANDALONE_REGEX = re.compile(r"(?:免收報名費|免費參加|免費報名|全程免費|費用全免|免費(?!名額))")
# A fee value must carry a price or a free marker; bare words such as 會員 or a lone （ are not fees.
_FEE_VALUE_REGEX = re.compile(r"(?:NT\$|\$|新台幣)\s*\d|\d[\d,]*\s*元|免費(?!名額)|免收|^\d[\d,]{2,}$")

_LOCATION_LABEL_REGEX = re.compile(
    r"(?:上課地點|辦理地點|活動地點|講座地點|研習地點|會場地點|地點|會場|場地|辦理方式|上課方式|進行方式|授課方式)\s*"
    + _LABEL_SEP
)
_CITY_NAMES = (
    r"(?:臺北市|台北市|新北市|桃園市|臺中市|台中市|臺南市|台南市|高雄市|基隆市|新竹市|新竹縣|苗栗縣|彰化縣"
    r"|南投縣|雲林縣|嘉義市|嘉義縣|屏東縣|宜蘭縣|花蓮縣|臺東縣|台東縣|澎湖縣)"
)
# Prefer an address that runs through its house number (…大學路1號) over stopping at the first 大學.
_ADDRESS_WITH_NUMBER_REGEX = re.compile(
    rf"({_CITY_NAMES}[^\n。；;！!？?，,]{{2,38}}?\d+(?:之\d+)?號(?:\d+樓)?)"
)
_ADDRESS_VENUE_REGEX = re.compile(
    rf"({_CITY_NAMES}[^\n。；;！!？?]{{2,38}}?(?:大學|醫院|中心|學會|學院|講堂|會議室|教室|廳|館|樓|號))"
)
_CITY_REGION_TAG_REGEX = re.compile(
    r"(?:[【\[（(]\s*(台北|臺北|新北|桃園|新竹|台中|臺中|嘉義|台南|臺南|高雄|屏東|宜蘭|花蓮|台東|臺東|北部|中部|南部|東部)(?:場|區)?\s*[】\]）)]"
    r"|(台北|臺北|新北|桃園|新竹|台中|臺中|嘉義|台南|臺南|高雄|屏東|宜蘭|花蓮|台東|臺東|北部|中部|南部|東部)場)"
)
_INSTITUTION_ORGANIZER_KEYWORDS = (
    "醫院",
    "大學",
    "衛生局",
    "衛生所",
    "心理衛生中心",
    "防治中心",
    "療養院",
    "診所",
    "治療所",
    "諮商所",
    "基金會",
    "法院",
)
_ONLINE_KEYWORDS_REGEX = re.compile(
    r"(?:線上(?:課程|視訊|授課|講座|工作坊|研討會|同步|上課|進行|辦理)?|視訊(?:課程|講座|上課|會議)?|Zoom|Google\s*Meet|Webex|Teams|網路直播|通訊繼續教育)",
    re.IGNORECASE,
)
_IN_PERSON_KEYWORDS_REGEX = re.compile(r"(?:實體(?:課程|上課|講座|工作坊|辦理|進行)?)")

_REG_PERIOD_LABEL_REGEX = re.compile(
    r"(?:報名期間|報名日期|報名時間|報名期限|報名起訖|報名截止日期|報名截止時間|報名截止日|報名截止)\s*"
    + _LABEL_SEP
)
_REG_PERIOD_IMMEDIATE_REGEX = re.compile(
    r"(即日起\s*(?:至|起至)?\s*[^\n。；;（）()]{2,34}?(?:止|前|額滿為止)?)(?=[。，,；;\s\n]|$)"
)
_REG_PERIOD_OPEN_REGEX = re.compile(
    r"((?:\d{3,4}\s*[年./-]\s*\d{1,2}\s*[月./-]\s*\d{1,2}\s*日?\s*(?:[~～\-–—至到]\s*(?:\d{3,4}\s*[年./-]\s*)?\d{1,2}\s*[月./-]\s*\d{1,2}\s*日?)?)\s*開放報名)"
)
_REG_PERIOD_DEADLINE_SENTENCE_REGEX = re.compile(
    r"((?:請於|自)?\s*\d{3,4}\s*[年./-]\s*\d{1,2}\s*[月./-]\s*\d{1,2}\s*日?[^\n。，,；;]{0,20}?(?:前完成報名|前報名|報名截止|截止報名))"
)

_ORGANIZER_LABEL_REGEX = re.compile(
    r"(?:主辦單位|開課單位|辦理單位|主辦|承辦單位)\s*(?:[：:]|】\s*[：:]?)\s*([^\n。；;]+)"
)
_TITLE_ORG_PREFIX_REGEX = re.compile(r"^([\u4e00-\u9fff]{3,30}?)(?:[-－—])")

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
    "/register.php",
    "guestlogin",
    "/login",
    "/member",
    "/event/search",
    "/product-category/",
    "co_register_02.asp",
    "/people-area/",
    "callforpapers",
    "/cdn-cgi/",
    "blackhole=",
)

_PLAIN_URL_AFTER_REG_LABEL_REGEX = re.compile(
    r"(?:報名網址|報名連結|報名方式|線上報名|網路報名|報名表單)\s*(?:[：:]|】\s*[：:]?)?\s*(https?://[^\s<>\"'）)]+)"
)
_CLOSED_REGISTRATION_REGEX = re.compile(
    r"(?:報名已截止|報名截止|已截止報名|已額滿|名額已滿|停止報名|截止報名)"
)
_CREDIT_SENTENCE_KEYWORDS = ("積分", "學分", "繼續教育")
_CREDIT_NEGATION_KEYWORDS = ("不申請", "無申請", "恕不提供", "不提供積分", "無繼續教育積分", "未申請", "不提供繼續教育")
# Menu labels and form questions (積分查詢, 繼續教育細則辦法, 您需要申請繼續教育積分嗎) are navigation
# text, not a credit claim about this course: a segment counts as credit evidence only when it
# carries a claim/provision keyword and is not phrased as a question.
_CREDIT_CLAIM_KEYWORDS = (
    "申請", "認證", "核給", "計分", "累計", "認定", "認可", "換取", "換得",
    "計入", "獲得", "核發", "提供", "登錄",
)
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

    return ""


def extract_end_date(text: str) -> str:
    """Return the end ROC date of the first date or range in free text (e.g. a registration deadline)."""
    found = _extract_date_from_segment(text or "")
    return found.split("–")[-1] if found else ""


def _pad_hhmm(hhmm: str) -> str:
    normalized = hhmm.strip().replace("：", ":")
    parts = normalized.split(":")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    return normalized


def _strip_office_hour_lines(text: str) -> str:
    lines = [
        line
        for line in (text or "").splitlines()
        if not any(kw in line for kw in _OFFICE_HOURS_LINE_KEYWORDS)
    ]
    return "\n".join(lines)


def extract_time_range(text: str) -> str:
    """Extract 'HH:MM–HH:MM' (with en-dash) or single 'HH:MM' after a time label."""
    if not text:
        return ""

    filtered = _strip_office_hour_lines(text)

    match = _TIME_RANGE_REGEX.search(filtered)
    if match:
        start_t = _pad_hhmm(match.group(1))
        end_t = _pad_hhmm(match.group(2))
        return f"{start_t}–{end_t}"

    cn_match = _CHINESE_TIME_RANGE_REGEX.search(filtered)
    if cn_match:
        h1, m1, h2, m2 = (
            int(cn_match.group(1)),
            int(cn_match.group(2) or 0),
            int(cn_match.group(3)),
            int(cn_match.group(4) or 0),
        )
        return f"{h1:02d}:{m1:02d}–{h2:02d}:{m2:02d}"

    single_match = _SINGLE_TIME_AFTER_LABEL_REGEX.search(filtered)
    if single_match:
        return _pad_hhmm(single_match.group(1))

    return ""

_LABEL_ONLY_REGEX = re.compile(r"^.{1,12}[：:／]\s*$")
_CONTINUATION_ENDINGS = ("至", "～", "~", "-", "–", "—", "到", "起")


def _paren_unbalanced(value: str) -> bool:
    return value.count("（") > value.count("）") or value.count("(") > value.count(")")


def _labelled_value(text: str, label_regex: re.Pattern[str]) -> str:
    """Value after the first matching label, continuing onto following lines when the value is
    empty, is itself a label, or is cut mid-phrase (open parenthesis, trailing 至)."""
    lines = [ln.strip() for ln in (text or "").splitlines()]
    for i, line in enumerate(lines):
        match = label_regex.search(line)
        if not match:
            continue
        value = line[match.end():].strip()
        j = i + 1
        while j <= i + 3 and j < len(lines) and (not value or _LABEL_ONLY_REGEX.match(value)):
            value = lines[j]
            j += 1
        if not value or _LABEL_ONLY_REGEX.match(value):
            continue
        while (
            j <= i + 5
            and j < len(lines)
            and lines[j]
            and (_paren_unbalanced(value) or value.endswith(_CONTINUATION_ENDINGS))
        ):
            value += lines[j]
            j += 1
        return value
    return ""


def _normalize_fee(value: str) -> str:
    if len(value) > 40:
        match = _FEE_VALUE_REGEX.search(value)
        value = match.group(0) if match else value[:40]
    is_free = any(k in value for k in ("免收報名費", "免費")) or re.search(r"(?<![0-9,])0\s*元", value)
    if is_free and "$" not in value and not re.search(r"[1-9][\d,]*\s*元", value):
        return "免費"
    return value


def extract_fee(text: str) -> str:
    """Extract a price or free marker from a fee label (or the few lines after it)."""
    if not text:
        return ""

    lines = [ln.strip() for ln in text.splitlines()]
    for i, line in enumerate(lines):
        match = _FEE_LABEL_REGEX.search(line)
        if not match:
            continue
        for candidate in [line[match.end():], *lines[i + 1 : i + 5]]:
            candidate = re.split(r"[。；;]", candidate)[0].strip().rstrip("，, ")
            if candidate and _FEE_VALUE_REGEX.search(candidate):
                return _normalize_fee(candidate)

    if _FREE_STANDALONE_REGEX.search(text):
        return "免費"

    return ""


def extract_location_mode(title: str, text: str, organizer: str = "") -> str:
    """Extract labeled location/mode or detect online/in-person/venue from title, text, and organizer."""
    combined = f"{title or ''}\n{text or ''}"

    loc_value = re.sub(r"\s+", " ", _labelled_value(text, _LOCATION_LABEL_REGEX)).strip().rstrip("。；; ")
    if loc_value:
        has_online = bool(_ONLINE_KEYWORDS_REGEX.search(loc_value))
        has_in_person = bool(_IN_PERSON_KEYWORDS_REGEX.search(loc_value))
        if has_online and has_in_person:
            return (
                f"實體、線上混合（{loc_value}）"
                if loc_value not in ("實體、線上混合", "實體與線上同步")
                else loc_value
            )
        return loc_value

    has_online_any = bool(_ONLINE_KEYWORDS_REGEX.search(combined))
    has_in_person_any = bool(_IN_PERSON_KEYWORDS_REGEX.search(combined))

    if has_online_any and has_in_person_any:
        return "實體、線上混合"
    if has_online_any:
        return "線上"

    addr_match = _ADDRESS_WITH_NUMBER_REGEX.search(text or "") or _ADDRESS_VENUE_REGEX.search(text or "")
    if addr_match:
        return re.sub(r"\s+", " ", addr_match.group(1)).strip()

    city_match = _CITY_REGION_TAG_REGEX.search(combined)
    if city_match:
        city = (city_match.group(1) or city_match.group(2) or "").strip()
        if city:
            return f"{city}（實體）"

    if has_in_person_any:
        return "實體"

    clean_org = (organizer or "").strip()
    if clean_org and any(kw in clean_org for kw in _INSTITUTION_ORGANIZER_KEYWORDS):
        return f"{clean_org}（實體）"

    return ""


def extract_registration_period(text: str) -> str:
    """Extract labeled registration period, '即日起至...', or '...開放報名'."""
    if not text:
        return ""

    val = re.sub(r"\s+", " ", _labelled_value(text, _REG_PERIOD_LABEL_REGEX)).split("。")[0].strip().rstrip("；; ")
    if val:
        return val

    imm_match = _REG_PERIOD_IMMEDIATE_REGEX.search(text)
    if imm_match:
        return re.sub(r"\s+", " ", imm_match.group(1)).strip().rstrip("。；;，, ")

    open_match = _REG_PERIOD_OPEN_REGEX.search(text)
    if open_match:
        return re.sub(r"\s+", " ", open_match.group(1)).strip()

    deadline_match = _REG_PERIOD_DEADLINE_SENTENCE_REGEX.search(text)
    if deadline_match:
        return re.sub(r"\s+", " ", deadline_match.group(1)).strip()

    if "額滿為止" in text:
        return "即日起（額滿為止）"

    return ""

def _unwrap_redirect_url(url: str) -> str:
    """Unwrap Google AccountChooser continue=... and Facebook l.php?u=... URLs."""
    if "accounts.google.com/AccountChooser" in url or "l.facebook.com/l.php" in url:
        parsed = urlparse(url)
        q = parse_qs(parsed.query)
        target = (q.get("continue") or q.get("u") or [""])[0]
        if target:
            return unquote(target).split("?fbclid=")[0]
    return url

def _is_excluded_url(href: str) -> bool:
    lower_href = href.lower().strip()
    if not lower_href or lower_href.startswith("#"):
        return True
    return any(pattern in lower_href for pattern in _EXCLUDED_SHARE_PATTERNS)


def is_registration_closed(title: str, text: str) -> bool:
    """Return True if title or text explicitly marks the course registration as closed/full."""
    if _CLOSED_REGISTRATION_REGEX.search(title or ""):
        return True
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped in ("報名截止", "已截止", "已額滿", "報名已截止", "名額已滿"):
            return True
    return False


def extract_registration_url(html: str, detail_url: str) -> str:
    """Find registration URL in HTML or plain text, falling back to detail_url."""
    if not html:
        return detail_url

    soup = BeautifulSoup(html, "lxml")
    candidates: list[tuple[int, str]] = []

    for anchor in soup.find_all("a", href=True):
        raw_href = str(anchor.get("href", "")).strip()
        if _is_excluded_url(raw_href):
            continue

        resolved = _unwrap_redirect_url(urljoin(detail_url, raw_href))
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

        # Priority 2: Explicit course registration action text
        if any(kw in anchor_text for kw in ("點此報名", "線上報名", "立即報名", "我要報名", "報名表單", "前往報名")):
            candidates.append((85, resolved))
            continue

        if any(kw in context_text for kw in ("報名網址", "報名連結", "報名表單", "線上報名", "網路報名")):
            candidates.append((75, resolved))
            continue

        if any(kw in lower_resolved for kw in ("course-enroll", "/events/register/", "signup", "sign_up", "enroll")):
            candidates.append((60, resolved))

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    # Fallback: plain-text URL written right after 報名網址： / 報名方式：
    plain_text = soup.get_text("\n", strip=True)
    plain_match = _PLAIN_URL_AFTER_REG_LABEL_REGEX.search(plain_text)
    if plain_match:
        candidate_url = _unwrap_redirect_url(plain_match.group(1).strip().rstrip("。，,；;"))
        if not _is_excluded_url(candidate_url):
            return candidate_url

    for host in _KNOWN_FORM_HOSTS:
        host_match = re.search(rf"https?://[^\s<>\"'）)]*{re.escape(host)}[^\s<>\"'）)]*", plain_text)
        if host_match:
            return _unwrap_redirect_url(host_match.group(0).rstrip("。，,；;"))

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

    # Split text into candidate sentences/lines; require a credit-claim keyword so nav menu
    # labels (積分查詢, 繼續教育積分...) and form questions are not reported as evidence.
    raw_segments = re.split(r"[\n\r。！？!?；;]+", text)
    credit_sentences = [
        seg.strip()
        for seg in raw_segments
        if seg.strip()
        and any(kw in seg for kw in _CREDIT_SENTENCE_KEYWORDS)
        and any(kw in seg for kw in _CREDIT_CLAIM_KEYWORDS)
        and not seg.strip().endswith(("嗎", "？", "?"))
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


def _extract_organizer(
    title: str, text: str, default_organizer: str, source_platform: str
) -> str:
    # Forwarded posts (轉知) carry the true organizer as a CJK prefix before the first dash,
    # e.g. 「國家衛生研究院-『…』模式訓練工作坊」; titles starting with dates/digits don't match.
    prefix_match = _TITLE_ORG_PREFIX_REGEX.match((title or "").strip())
    if prefix_match:
        return prefix_match.group(1).strip()
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

    clean_title = re.sub(r"\s+", " ", (title or "")).strip()
    if not clean_title:
        heading = soup.find(["h1", "h2", "title"])
        clean_title = heading.get_text(" ", strip=True) if heading else "未命名課程"

    # Trim overly long anchor text where card summary was concatenated after title
    if len(clean_title) > 55 and " " in clean_title:
        short_match = re.match(
            r"^(.{6,55}?(?:工作坊(?:\([^)]+\)|（[^）]+）)?|課程|研討會|講座|訓練|研習會|論壇|督導|靜修營|年會))\s+",
            clean_title,
        )
        if short_match:
            clean_title = short_match.group(1).strip()

    organizer = _extract_organizer(clean_title, text, default_organizer, source_platform)
    course_date = normalize_roc_date(text) or normalize_roc_date(clean_title)
    course_time = extract_time_range(text) or extract_time_range(clean_title)
    if not course_time:
        if any(w in text for w in ("全天", "全日", "整日")):
            course_time = "09:00–17:00（全天）"
        elif "上午" in text and "下午" in text:
            course_time = "09:00–16:30"
        elif "詳見簡章" in text or detail_url:
            course_time = "詳見簡章"

    fee = extract_fee(text)
    location_mode = extract_location_mode(clean_title, text, organizer=organizer)
    if not location_mode:
        location_mode = f"{organizer}（依簡章公告）" if organizer else "依簡章公告"

    registration_period = extract_registration_period(text)
    if not registration_period:
        if course_date:
            start_d = course_date.split("–")[0].strip()
            registration_period = f"即日起至 {start_d} 前"
        else:
            registration_period = "詳見報名連結"

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
