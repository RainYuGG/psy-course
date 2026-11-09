"""Keyword-search scraper for the AccuPass event platform (public JSON API)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from scraper.extractor import extract_course_from_page
from scraper.models import CourseRecord
from scraper.sources.base import BaseSourceScraper, is_likely_course_title

_SEARCH_API_URL = "https://api.accupass.com/v3/search/SearchEvents"
_DETAIL_API_URL = "https://api.accupass.com/v3/events/{event_id}"
_EVENT_URL = "https://www.accupass.com/event/{event_id}"

_API_HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://www.accupass.com",
    "Referer": "https://www.accupass.com/",
}

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


def _local_dt(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _detail_fields(detail: dict) -> dict:
    """Pull date/time/fee/mode/organizer/address/description from the event detail JSON."""
    event_time = detail.get("eventTimeObj") or {}
    start_dt = _local_dt(str(event_time.get("startDateTime") or ""))
    end_dt = _local_dt(str(event_time.get("endDateTime") or ""))

    course_date = ""
    if start_dt is not None:
        if end_dt is not None and end_dt.date() > start_dt.date():
            course_date = f"{_roc_date_str(start_dt.date())}–{_roc_date_str(end_dt.date())}"
        else:
            course_date = _roc_date_str(start_dt.date())

    course_time = ""
    if start_dt is not None and end_dt is not None and end_dt.date() == start_dt.date():
        course_time = f"{start_dt:%H:%M}–{end_dt:%H:%M}"

    fee = ""
    if detail.get("isFree"):
        fee = "免費"
    else:
        register_btn = detail.get("registerBtn") or {}
        try:
            price_num = float(register_btn.get("price") or 0)
        except (TypeError, ValueError):
            price_num = 0.0
        currency = str(register_btn.get("currency") or "")
        if price_num > 0:
            fee = f"{currency}{price_num:g}"
        elif any("免費" in str(tag.get("name") or "") for tag in detail.get("tags") or []):
            fee = "免費"

    mode = {"Online": "線上", "Offline": "實體"}.get(str(detail.get("eventPlaceType") or ""), "")
    organizer = str((detail.get("organizer") or {}).get("title") or "").strip()
    return {
        "course_date": course_date,
        "course_time": course_time,
        "fee": fee,
        "mode": mode,
        "organizer": organizer,
        "address": str(detail.get("address") or "").strip(),
        "description": str(detail.get("description") or "").strip(),
    }


class AccupassScraper(BaseSourceScraper):
    """Scrape AccuPass events via the site's public search + event-detail JSON APIs."""

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
                data = json.loads(client.post_json(_SEARCH_API_URL, body, headers=_API_HEADERS))
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
                if start_local is not None and start_local < today_local:
                    continue  # already started; upcoming filter would drop it anyway
                seen_ids.add(event_id)

                try:
                    detail = json.loads(client.get_text(_DETAIL_API_URL.format(event_id=event_id)))
                except Exception:
                    continue
                if (detail.get("registerBtn") or {}).get("isDisabled"):
                    continue  # registration closed

                fields = _detail_fields(detail)
                html_parts = [f"<html><body><h1>{name}</h1>"]
                if fields["mode"]:
                    html_parts.append(f"<p>上課方式：{fields['mode']}</p>")
                if fields["address"]:
                    html_parts.append(f"<p>地點：{fields['address']}</p>")
                if fields["fee"]:
                    html_parts.append(f"<p>報名費用：{fields['fee']}</p>")
                if fields["description"]:
                    html_parts.append(f"<p>{fields['description']}</p>")
                html_parts.append("</body></html>")
                record = extract_course_from_page(
                    title=name,
                    html="".join(html_parts),
                    detail_url=_EVENT_URL.format(event_id=event_id),
                    source_platform=self.source_name,
                    default_organizer=fields["organizer"] or self.default_organizer,
                    created_at=created_date,
                )
                if fields["course_date"]:
                    record.course_date = fields["course_date"]
                if fields["course_time"]:
                    record.course_time = fields["course_time"]
                if fields["fee"]:
                    record.fee = fields["fee"]
                if fields["mode"]:
                    record.location_mode = fields["mode"]
                records.append(record)

        if not any_request_ok and last_error is not None:
            raise last_error
        return records
