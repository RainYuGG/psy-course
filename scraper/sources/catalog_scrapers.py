"""Catalog scrapers for the remaining 14 A-class Taiwanese psychology associations."""

from __future__ import annotations

from datetime import date
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from scraper.extractor import extract_course_from_page, normalize_roc_date
from scraper.http_client import HttpClient
from scraper.models import CourseRecord
from scraper.sources.base import (
    COURSE_INDICATOR_KEYWORDS,
    BaseSourceScraper,
    is_likely_course_title,
)

_SKIP_HREF_TOKENS = (
    "javascript:",
    "mailto:",
    "tel:",
    "/login",
    "/register_member",
    "/cart",
    "/about",
    "/contact",
    "/privacy",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "line.me",
)

_URL_COURSE_HINTS = (
    "course",
    "event",
    "news",
    "activity",
    "workshop",
    "seminar",
    "lecture",
    "training",
    "article",
    "post",
    "detail",
    "view",
    "page",
    "p=",
    "id=",
)


class GenericCatalogScraper(BaseSourceScraper):
    """Configurable listing + detail page scraper for association websites."""

    listing_urls: tuple[str, ...] = ()
    max_items: int = 12

    def get_listing_urls(self) -> tuple[str, ...]:
        if self.listing_urls:
            return self.listing_urls
        return (self.base_url,)

    def _is_candidate_link(self, title: str, resolved_url: str, base_url: str) -> bool:
        if not is_likely_course_title(title):
            return False

        lower_url = resolved_url.lower()
        if any(tok in lower_url for tok in _SKIP_HREF_TOKENS):
            return False

        has_course_kw = any(kw in title for kw in COURSE_INDICATOR_KEYWORDS)
        has_url_hint = any(hint in lower_url for hint in _URL_COURSE_HINTS)
        has_date_in_title = bool(normalize_roc_date(title))

        if not (has_course_kw or has_date_in_title or (has_url_hint and len(title) >= 8)):
            return False

        # Avoid re-fetching the exact listing URL itself
        if resolved_url.rstrip("/") == base_url.rstrip("/"):
            return False

        return True

    def scrape(self, client: HttpClient, created_at: str = "") -> list[CourseRecord]:
        created_date = created_at or date.today().isoformat()
        seen_urls: set[str] = set()
        records: list[CourseRecord] = []
        any_listing_succeeded = False
        last_error: Exception | None = None

        for list_url in self.get_listing_urls():
            try:
                listing_html = client.get_text(list_url)
                any_listing_succeeded = True
            except Exception as exc:
                last_error = exc
                continue

            soup = BeautifulSoup(listing_html or "", "lxml")
            candidates: list[tuple[str, str]] = []

            for anchor in soup.find_all("a", href=True):
                raw_href = str(anchor.get("href", "")).strip()
                if not raw_href or raw_href.startswith("#"):
                    continue
                title = anchor.get_text(" ", strip=True)
                if not title:
                    title = str(anchor.get("title", "")).strip()
                resolved = urljoin(list_url, raw_href)
                if resolved in seen_urls:
                    continue
                if not self._is_candidate_link(title, resolved, list_url):
                    continue
                seen_urls.add(resolved)
                candidates.append((title, resolved))

            for title, detail_url in candidates[: self.max_items]:
                try:
                    parsed_detail = urlparse(detail_url)
                    parsed_list = urlparse(list_url)
                    # Only fetch detail HTML if same host or standard http(s) page
                    if parsed_detail.scheme in ("http", "https") and (
                        parsed_detail.netloc == parsed_list.netloc
                        or not any(
                            form_host in detail_url
                            for form_host in ("forms.gle", "docs.google.com/forms", "beclass.com")
                        )
                    ):
                        detail_html = client.get_text(detail_url)
                    else:
                        detail_html = ""
                except Exception:
                    detail_html = ""

                record = extract_course_from_page(
                    title=title,
                    html=detail_html or f"<html><body><h1>{title}</h1></body></html>",
                    detail_url=detail_url,
                    source_platform=self.source_name,
                    default_organizer=self.default_organizer,
                    created_at=created_date,
                )
                records.append(record)

            # Fallback for single-page sites (e.g. Google Sites) where courses are inline blocks
            if not candidates:
                records.extend(self._extract_inline_blocks(soup, list_url, created_date))

        if not any_listing_succeeded and last_error is not None:
            raise last_error

        return records

    def _extract_inline_blocks(
        self, soup: BeautifulSoup, page_url: str, created_date: str
    ) -> list[CourseRecord]:
        inline_records: list[CourseRecord] = []
        seen_titles: set[str] = set()
        for heading in soup.find_all(["h2", "h3", "h4"]):
            title = heading.get_text(" ", strip=True)
            if not is_likely_course_title(title):
                continue
            if not any(kw in title for kw in COURSE_INDICATOR_KEYWORDS):
                continue
            if title in seen_titles:
                continue
            seen_titles.add(title)
            container = heading.parent if heading.parent is not None else heading
            record = extract_course_from_page(
                title=title,
                html=str(container),
                detail_url=page_url,
                source_platform=self.source_name,
                default_organizer=self.default_organizer,
                created_at=created_date,
            )
            inline_records.append(record)
            if len(inline_records) >= self.max_items:
                break
        return inline_records


# --- Batch 1 (Task 2.4): atpt, tcpu, twcpa, psychoanalysis, sop ---


class AtptScraper(GenericCatalogScraper):
    """台灣遊戲治療學會 (atpt.org.tw)."""

    source_id = "atpt"
    source_name = "台灣遊戲治療學會"
    default_organizer = "台灣遊戲治療學會"
    base_url = "https://www.atpt.org.tw/"
    listing_urls = ("https://www.atpt.org.tw/",)


class TcpuScraper(GenericCatalogScraper):
    """中華民國諮商心理師公會全國聯合會 (tcpu.org.tw)."""

    source_id = "tcpu"
    source_name = "中華民國諮商心理師公會全國聯合會"
    default_organizer = "中華民國諮商心理師公會全國聯合會"
    base_url = "https://www.tcpu.org.tw/"
    listing_urls = ("https://www.tcpu.org.tw/",)


class TwcpaScraper(GenericCatalogScraper):
    """臺灣諮商心理學會 (twcpa.org.tw/recentcourses)."""

    source_id = "twcpa"
    source_name = "臺灣諮商心理學會"
    default_organizer = "臺灣諮商心理學會"
    base_url = "https://www.twcpa.org.tw/recentcourses"
    listing_urls = ("https://www.twcpa.org.tw/recentcourses",)


class PsychoanalysisScraper(GenericCatalogScraper):
    """臺灣精神分析學會 (psychoanalysis.org.tw)."""

    source_id = "psychoanalysis"
    source_name = "臺灣精神分析學會"
    default_organizer = "臺灣精神分析學會"
    base_url = "https://psychoanalysis.org.tw/"
    listing_urls = ("https://psychoanalysis.org.tw/",)


class SopScraper(GenericCatalogScraper):
    """台灣精神醫學會 (sop.org.tw)."""

    source_id = "sop"
    source_name = "台灣精神醫學會"
    default_organizer = "台灣精神醫學會"
    base_url = "https://www.sop.org.tw/"
    listing_urls = ("https://www.sop.org.tw/",)


# --- Batch 2 (Task 2.5): rmdaroc, tap, tpos, iaptc, tasctaiwan, acft_eft, ecata, mindfulness, tsos ---


class RmdarocScraper(GenericCatalogScraper):
    """台灣復健醫學會／心理復健相關報名頁 (sites.google.com/rmdaroc.org/signup/首頁)."""

    source_id = "rmdaroc"
    source_name = "台灣心理復健協會"
    default_organizer = "台灣心理復健協會"
    base_url = "https://sites.google.com/rmdaroc.org/signup/%E9%A6%96%E9%A0%81"
    listing_urls = ("https://sites.google.com/rmdaroc.org/signup/%E9%A6%96%E9%A0%81",)


class TapScraper(GenericCatalogScraper):
    """臺灣心理治療學會 (tap.org.tw)."""

    source_id = "tap"
    source_name = "臺灣心理治療學會"
    default_organizer = "臺灣心理治療學會"
    base_url = "https://www.tap.org.tw/"
    listing_urls = ("https://www.tap.org.tw/",)


class TposScraper(GenericCatalogScraper):
    """台灣心理腫瘤醫學學會 (tpos-society.org)."""

    source_id = "tpos"
    source_name = "台灣心理腫瘤醫學學會"
    default_organizer = "台灣心理腫瘤醫學學會"
    base_url = "http://www.tpos-society.org/"
    listing_urls = ("http://www.tpos-society.org/",)


class IaptcScraper(GenericCatalogScraper):
    """台灣網路成癮防治學會 (iaptc.asia.edu.tw)."""

    source_id = "iaptc"
    source_name = "台灣網路成癮防治學會"
    default_organizer = "台灣網路成癮防治學會"
    base_url = "https://iaptc.asia.edu.tw/"
    listing_urls = ("https://iaptc.asia.edu.tw/",)


class TasctaiwanScraper(GenericCatalogScraper):
    """台灣性諮商學會 (tasctaiwan.tw)."""

    source_id = "tasctaiwan"
    source_name = "台灣性諮商學會"
    default_organizer = "台灣性諮商學會"
    base_url = "https://tasctaiwan.tw/"
    listing_urls = ("https://tasctaiwan.tw/",)


class AcftEftScraper(GenericCatalogScraper):
    """華人伴侶與家族治療協會 / 亞太情緒取向伴侶與家族治療協會 (acft.org.tw & asia-eft.com)."""

    source_id = "acft_eft"
    source_name = "華人伴侶與家族治療協會／亞太EFT"
    default_organizer = "華人伴侶與家族治療協會"
    base_url = "http://www.acft.org.tw/"
    listing_urls = (
        "http://www.acft.org.tw/",
        "https://asia-eft.com/",
    )


class EcataScraper(GenericCatalogScraper):
    """台灣表創性藝術治療學會 (ecata.org.tw)."""

    source_id = "ecata"
    source_name = "台灣表創性藝術治療學會"
    default_organizer = "台灣表創性藝術治療學會"
    base_url = "https://ecata.org.tw/"
    listing_urls = ("https://ecata.org.tw/",)


class MindfulnessScraper(GenericCatalogScraper):
    """台灣正念發展協會 (mindfulness.org.tw)."""

    source_id = "mindfulness"
    source_name = "台灣正念發展協會"
    default_organizer = "台灣正念發展協會"
    base_url = "https://www.mindfulness.org.tw/"
    listing_urls = ("https://www.mindfulness.org.tw/",)


class TsosScraper(GenericCatalogScraper):
    """台灣自殺防治學會 (tsos.org.tw)."""

    source_id = "tsos"
    source_name = "台灣自殺防治學會"
    default_organizer = "台灣自殺防治學會"
    base_url = "https://www.tsos.org.tw/"
    listing_urls = ("https://www.tsos.org.tw/",)
