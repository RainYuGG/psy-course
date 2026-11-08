"""Registry and runner for all 19 Taiwanese clinical/counseling psychology course scrapers."""

from __future__ import annotations

from datetime import date

from scraper.http_client import HttpClient
from scraper.models import CourseRecord
from scraper.sources.atcp import AtcpScraper
from scraper.sources.base import BaseSourceScraper
from scraper.sources.catalog_scrapers import (
    AcftEftScraper,
    AtptScraper,
    BeclassScraper,
    EcataScraper,
    IaptcScraper,
    KaohsiungHealthScraper,
    MindfulnessScraper,
    PsychoanalysisScraper,
    RmdarocScraper,
    SopScraper,
    TapScraper,
    TasctaiwanScraper,
    TaipeiHealthScraper,
    TcpuScraper,
    TposScraper,
    TsosScraper,
    TwcpaScraper,
)
from scraper.sources.taclip_whitelist import TaclipWhitelistScraper, WhitelistEntry

ALL_SCRAPERS: list[BaseSourceScraper] = [
    TaclipWhitelistScraper(),
    AtcpScraper(),
    AtptScraper(),
    TcpuScraper(),
    TwcpaScraper(),
    PsychoanalysisScraper(),
    SopScraper(),
    RmdarocScraper(),
    TapScraper(),
    TposScraper(),
    IaptcScraper(),
    TasctaiwanScraper(),
    AcftEftScraper(),
    EcataScraper(),
    MindfulnessScraper(),
    TsosScraper(),
    BeclassScraper(),
    TaipeiHealthScraper(),
    KaohsiungHealthScraper(),
]


def fetch_all_sources(
    client: HttpClient | None = None,
    created_at: str = "",
) -> tuple[list[CourseRecord], list[WhitelistEntry], list[dict[str, str]]]:
    """Run all registered scrapers with fault isolation and return (courses, whitelist, statuses)."""
    http_client = client or HttpClient()
    created_date = created_at or date.today().isoformat()

    all_courses: list[CourseRecord] = []
    whitelist_entries: list[WhitelistEntry] = []
    statuses: list[dict[str, str]] = []

    for scraper in ALL_SCRAPERS:
        courses, status = scraper.safe_scrape(http_client, created_at=created_date)
        all_courses.extend(courses)
        statuses.append(status)
        if isinstance(scraper, TaclipWhitelistScraper):
            whitelist_entries.extend(scraper.last_whitelist_entries)

    return (all_courses, whitelist_entries, statuses)


__all__ = [
    "ALL_SCRAPERS",
    "AcftEftScraper",
    "AtptScraper",
    "BeclassScraper",
    "BaseSourceScraper",
    "EcataScraper",
    "IaptcScraper",
    "KaohsiungHealthScraper",
    "MindfulnessScraper",
    "PsychoanalysisScraper",
    "RmdarocScraper",
    "SopScraper",
    "TaclipWhitelistScraper",
    "TapScraper",
    "TasctaiwanScraper",
    "TaipeiHealthScraper",
    "TcpuScraper",
    "TposScraper",
    "TsosScraper",
    "TwcpaScraper",
    "WhitelistEntry",
    "fetch_all_sources",
]
