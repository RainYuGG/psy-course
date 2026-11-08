"""Scraper for Taiwan Association of Clinical Psychology (TACLIP) approved course list and news."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup, Tag

from scraper.extractor import (
    evaluate_clinical_credit,
    extract_course_from_page,
    extract_location_mode,
    normalize_roc_date,
)
from scraper.http_client import HttpClient
from scraper.models import CourseRecord
from scraper.sources.base import (
    COURSE_INDICATOR_KEYWORDS,
    BaseSourceScraper,
    is_likely_course_title,
)

TACLIP_CHECKED_LIST_URL = "https://taclip.org.tw/checked-list/"
TACLIP_HOME_URL = "https://taclip.org.tw/"
TACLIP_WHITELIST_PLATFORM = "台灣臨床心理學會（審核通過課程總表）"
TACLIP_PLATFORM = "台灣臨床心理學會"

_REQUIRED_HEADERS = ("認證字號", "課程性質", "開始日期", "開課單位", "課程名稱")


@dataclass
class WhitelistEntry:
    """Represents an official TACLIP continuing-education approved course row."""

    cert_no: str
    category: str
    start_date_roc: str
    organizer: str
    course_name: str


def _find_checked_list_table(soup: BeautifulSoup) -> Tag | None:
    table = soup.find("table", id="footable_3078")
    if isinstance(table, Tag):
        return table

    for candidate in soup.find_all("table"):
        header_text = " ".join(th.get_text(" ", strip=True) for th in candidate.find_all(["th", "td"])[:10])
        if all(h in header_text for h in _REQUIRED_HEADERS):
            return candidate
    return None


def parse_taclip_whitelist_html(
    html: str, created_at: str = ""
) -> tuple[list[WhitelistEntry], list[CourseRecord]]:
    """Parse TACLIP checked-list HTML table into WhitelistEntry and CourseRecord lists."""
    created_date = created_at or date.today().isoformat()
    soup = BeautifulSoup(html or "", "lxml")
    table = _find_checked_list_table(soup)
    if table is None:
        return ([], [])

    entries: list[WhitelistEntry] = []
    records: list[CourseRecord] = []

    tbody = table.find("tbody") or table
    for tr in tbody.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) < 5:
            continue

        cert_no, category, raw_start_date, organizer, course_name = (
            cells[0].strip(),
            cells[1].strip(),
            cells[2].strip(),
            cells[3].strip(),
            cells[4].strip(),
        )
        if not course_name or course_name == "課程名稱":
            continue

        start_date_roc = normalize_roc_date(raw_start_date) or raw_start_date
        entry = WhitelistEntry(
            cert_no=cert_no,
            category=category,
            start_date_roc=start_date_roc,
            organizer=organizer or TACLIP_PLATFORM,
            course_name=course_name,
        )
        entries.append(entry)

        has_credit, evidence = evaluate_clinical_credit(
            "", whitelist_match={"cert_no": cert_no, "category": category}
        )
        location_mode = extract_location_mode(course_name, "")
        query = quote_plus(f"{organizer} {course_name}".strip())
        fallback_url = f"{TACLIP_CHECKED_LIST_URL}?q={query}"

        records.append(
            CourseRecord(
                course_name=course_name,
                organizer=organizer or TACLIP_PLATFORM,
                course_date=start_date_roc,
                course_time="",
                fee="",
                location_mode=location_mode,
                registration_url=fallback_url,
                has_clinical_credit=has_credit,
                credit_evidence=evidence,
                source_platform=TACLIP_WHITELIST_PLATFORM,
                created_at=created_date,
                registration_period="",
            )
        )

    return (entries, records)


class TaclipWhitelistScraper(BaseSourceScraper):
    """Scrapes both TACLIP checked-list whitelist and TACLIP course announcements."""

    source_id = "taclip"
    source_name = TACLIP_PLATFORM
    default_organizer = TACLIP_PLATFORM
    base_url = TACLIP_CHECKED_LIST_URL

    def __init__(self, max_detail_pages: int = 12) -> None:
        self.max_detail_pages = max_detail_pages
        self.last_whitelist_entries: list[WhitelistEntry] = []

    def scrape(self, client: HttpClient, created_at: str = "") -> list[CourseRecord]:
        created_date = created_at or date.today().isoformat()
        checked_html = client.get_text(TACLIP_CHECKED_LIST_URL)
        entries, records = parse_taclip_whitelist_html(checked_html, created_at=created_date)
        self.last_whitelist_entries = entries

        # Also scrape course announcements from TACLIP homepage (excluding job postings)
        try:
            home_html = client.get_text(TACLIP_HOME_URL)
            records.extend(self._scrape_home_announcements(client, home_html, created_date))
        except Exception:
            pass

        return records

    def _scrape_home_announcements(
        self, client: HttpClient, home_html: str, created_date: str
    ) -> list[CourseRecord]:
        soup = BeautifulSoup(home_html or "", "lxml")
        seen_urls: set[str] = set()
        results: list[CourseRecord] = []

        for anchor in soup.find_all("a", href=True):
            title = anchor.get_text(" ", strip=True)
            if not is_likely_course_title(title):
                continue
            if not any(kw in title for kw in COURSE_INDICATOR_KEYWORDS):
                continue

            href = urljoin(TACLIP_HOME_URL, str(anchor["href"]).strip())
            if not href.startswith("http") or href in seen_urls:
                continue
            if any(skip in href for skip in ("/checked-list", "/category/", "/tag/", "/author/", "#")):
                continue

            seen_urls.add(href)
            try:
                detail_html = client.get_text(href)
                record = extract_course_from_page(
                    title=title,
                    html=detail_html,
                    detail_url=href,
                    source_platform=TACLIP_PLATFORM,
                    default_organizer=self.default_organizer,
                    created_at=created_date,
                )
                results.append(record)
            except Exception:
                continue

            if len(results) >= self.max_detail_pages:
                break

        return results
