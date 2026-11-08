"""Keyword-search scraper for the AccuPass event platform (public JSON API)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from scraper.extractor import extract_course_from_page, is_registration_closed
from scraper.models import CourseRecord
from scraper.sources.base import BaseSourceScraper, is_likely_course_title

_API_URL = "https://api.accupass.com/v3/search/SearchEvents"
_EVENT_URL = "https://www.accupass.com/event/{event_id}"

# Psychology-CE-focused keywords; the API returns all matching events, and
# is_likely_course_title plus the upcoming-date filter trim the rest.
_KEYWORDS = ("臨床心理師 工作坊", "臨床心理師 課程", "心理治療 訓練")
_MAX_ITEMS_PER_KEYWORD = 12
_TAIPEI_TZ = timezone(timedelta(hours=8))


def _parse_local_date(iso_utc: str) -> date | None:
    try:
        return datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(_TAIPEI_TZ).date()
    except ValueError:
        return None


def _roc_date_str(local_date: date) -> str:
    return f"{local_date.year - 1911:03d}/{local_date.month:02d}/{local_date.day:02d}"


class AccupassScraper(BaseSourceScraper):
    """Scrape AccuPass events via the site's public SearchEvents JSON API."""

    source_id = "accupass"
    source_name = "AccuPass 活動平台"
    default_organizer = ""

    def scrape(self, client, created_at: str = "") -> list[CourseRecord]:
        created_date = created_at or date.today().isoformat()
        today_local = datetime.now(_TAIPEI_TZ).date()
        records: list[CourseRecord] = []
        seen_ids: set[str] = set()
        any_request_ok = False
        last_error: Exception | None = None

        for keyword in _KEYWORDS:
            body = {
                "categoryTypeList": [],
                "simpleEventPlaceTypeList": [],
                "cityLocationList": [],
                "sortBy": "4",
                "timeType": "0",
                "currentIndex": 0,
                "keyword": keyword,
            }
            try:
                text = client.post_json(
                    _API_URL,
                    body,
                    headers={
                        "Content-Type": "application/json",
                        "Origin": "https://www.accupass.com",
                        "Referer": "https://www.accupass.com/",
                    },
                )
                data = json.loads(text)
                any_request_ok = True
            except Exception as exc:
                last_error = exc
                continue

            for item in (data.get("items") or [])[:_MAX_ITEMS_PER_KEYWORD]:
                event_id = str(item.get("eventIdNumber") or "").strip()
                name = str(item.get("name") or "").strip()
                if not event_id or event_id in seen_ids or not is_likely_course_title(name):
                    continue
                start_local = _parse_local_date(str(item.get("startDateTime") or ""))
                end_local = _parse_local_date(str(item.get("endDateTime") or ""))
                if start_local is not None and start_local < today_local:
                    continue  # already started; upcoming filter would drop it anyway
                seen_ids.add(event_id)
                detail_url = _EVENT_URL.format(event_id=event_id)
                try:
                    detail_html = client.get_text(detail_url)
                except Exception:
                    detail_html = ""
                if is_registration_closed(name, detail_html):
                    continue
                record = extract_course_from_page(
                    title=name,
                    html=detail_html or f"<html><body><h1>{name}</h1></body></html>",
                    detail_url=detail_url,
                    source_platform=self.source_name,
                    default_organizer=self.default_organizer,
                    created_at=created_date,
                )
                if not record.course_date and start_local is not None:
                    # Event pages print weekday+time only; the API carries the real date.
                    if end_local is not None and end_local > start_local:
                        record.course_date = f"{_roc_date_str(start_local)}–{_roc_date_str(end_local)}"
                    else:
                        record.course_date = _roc_date_str(start_local)
                records.append(record)

        if not any_request_ok and last_error is not None:
            raise last_error
        return records
