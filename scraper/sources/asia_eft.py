"""Scraper for Asia EFT (亞太情緒取向伴侶與家族治療協會) via its WordPress REST API."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone

from scraper.extractor import (
    extract_fee,
    extract_location_mode,
    extract_registration_period,
)
from scraper.models import CourseRecord
from scraper.sources.base import BaseSourceScraper

_POSTS_API_URL = "https://asia-eft.com/wp-json/wp/v2/posts?per_page=100"
_TAIPEI_TZ = timezone(timedelta(hours=8))
# Session dates in Asia EFT posts are MM/DD lists, e.g. "08/27、09/10、10/24".
_SESSION_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)")
_TIME_RANGE_RE = re.compile(r"(\d{1,2}:\d{2})\s*[-~～至]\s*(\d{1,2}:\d{2})")
_REG_URL_RE = re.compile(
    r"https://(?:forms\.gle|docs\.google\.com|line\.me|accupass\.com|bit\.ly|tinyurl\.com)/\S+?"
    r"(?=[\s）)»\u3000]|$)"
)
_ORGANIZER_RE = re.compile(r"主辦單位[：:]\s*([^\n。；;]{2,40})")


def _strip_html(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment or "")
    return re.sub(r"\s+", " ", text).strip()


def _session_dates(post: dict) -> list[date]:
    """Parse the MM/DD session list from the post, anchoring the year to the post date."""
    post_date = datetime.fromisoformat(str(post.get("date") or "")[:10]).date()
    content = _strip_html(str(post.get("content", {}).get("rendered") or ""))
    found: list[date] = []
    for month_s, day_s in _SESSION_DATE_RE.findall(content):
        try:
            candidate = date(post_date.year, int(month_s), int(day_s))
        except ValueError:
            continue
        # A post published in late year announcing next-year sessions (01/xx, 02/xx).
        if (post_date - candidate).days > 90:
            try:
                candidate = date(post_date.year + 1, int(month_s), int(day_s))
            except ValueError:
                continue
        if candidate not in found:
            found.append(candidate)
    return sorted(found)


def _roc_date_str(local_date: date) -> str:
    return f"{local_date.year - 1911:03d}/{local_date.month:02d}/{local_date.day:02d}"


class AsiaEftScraper(BaseSourceScraper):
    """Scrape Asia EFT course posts via the public WordPress REST API (no HTML parsing)."""

    source_id = "asia_eft"
    source_name = "Asia EFT（亞太情緒取向伴侶與家族治療協會）"
    default_organizer = "Asia EFT（亞太情緒取向伴侶與家族治療協會）"

    def scrape(self, client, created_at: str = "") -> list[CourseRecord]:
        created_date = created_at or date.today().isoformat()
        today = datetime.now(_TAIPEI_TZ).date()
        posts = json.loads(client.get_text(_POSTS_API_URL))
        records: list[CourseRecord] = []
        seen_titles: set[str] = set()

        for post in posts:
            title = _strip_html(str(post.get("title", {}).get("rendered") or ""))
            if len(title) < 5 or title in seen_titles:
                continue
            content = _strip_html(str(post.get("content", {}).get("rendered") or ""))
            if not content:
                continue
            dates = _session_dates(post)
            if len(dates) < 2:
                continue  # only multi-session series carry MM/DD date lists; intros/articles do not
            if max(dates) < today:
                continue  # series fully finished
            reg_url_match = _REG_URL_RE.search(content)
            if not reg_url_match:
                continue  # course posts carry a registration link; articles/videos do not
            seen_titles.add(title)

            course_time = ""
            time_match = _TIME_RANGE_RE.search(content)
            if time_match:
                course_time = f"{time_match.group(1)}–{time_match.group(2)}"

            organizer_match = _ORGANIZER_RE.search(content)
            organizer = (
                organizer_match.group(1).strip() if organizer_match else self.default_organizer
            )

            registration_url = reg_url_match.group(0).strip()

            period = extract_registration_period(content)
            if not period:
                period = f"即日起至 {_roc_date_str(dates[0])} 前"
            date_range = (
                f"{_roc_date_str(dates[0])}–{_roc_date_str(dates[-1])}"
                if len(dates) > 1
                else _roc_date_str(dates[0])
            )

            records.append(
                CourseRecord(
                    course_name=title,
                    organizer=organizer,
                    course_date=date_range,
                    course_time=course_time,
                    fee=extract_fee(content),
                    location_mode=extract_location_mode(title, content, organizer),
                    registration_url=registration_url,
                    source_platform=self.source_name,
                    created_at=created_date,
                    registration_period=period,
                )
            )

        return records
