"""Catalog scrapers for A-class Taiwanese psychology associations, an event platform, and city health bureaus."""

from __future__ import annotations

import io
import re



from datetime import date
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from scraper.extractor import (
    extract_course_from_page,
    extract_fee,
    extract_registration_period,
    is_registration_closed,
    normalize_roc_date,
)

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

_SCHEDULE_RANGE_RE = re.compile(r"(\d{1,2})[:：](\d{2})\s*[~～\-–—]\s*(\d{1,2})[:：](\d{2})")


def _schedule_span(text: str) -> str:
    """Min-start to max-end span of a 3+-row schedule table (agenda PDFs)."""
    ranges = _SCHEDULE_RANGE_RE.findall(text)
    if len(ranges) < 3:
        return ""
    starts = [f"{int(h):02d}:{m}" for h, m, _, _ in ranges]
    ends = [f"{int(h):02d}:{m}" for _, _, h, m in ranges]
    return f"{min(starts)}–{max(ends)}"


def _fee_range_from_table(detail_html: str) -> str:
    """Min–max price across a multi-tier fee table (會員/學生/非會員 × 早鳥/一般)."""
    soup = BeautifulSoup(detail_html, "lxml")
    for table in soup.find_all("table"):
        text = table.get_text(" ", strip=True)
        if "每人費用" not in text and "早鳥價" not in text:
            continue
        nums: list[int] = []
        for cell in table.find_all(["td", "th"]):
            for digits in re.findall(r"[\d,]+", cell.get_text(strip=True)):
                if digits.replace(",", "").isdigit() and int(digits.replace(",", "")) >= 100:
                    nums.append(int(digits.replace(",", "")))
        if len(nums) >= 2:
            return f"{min(nums):,}–{max(nums):,}元"
    return ""

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
    # Beclass course pages (rid=...) are themselves the registration form.
    registration_url_is_detail: bool = False
    # Government 轉知 articles keep fee/registration details in attached PDFs.
    max_pdf_attachments: int = 0
    # Sites with multi-tier fee tables on the public course page.
    fee_table: bool = False

    def get_listing_urls(self) -> tuple[str, ...]:
        if self.listing_urls:
            return self.listing_urls
        return (self.base_url,)

    def _pdf_attachment_text(self, client, detail_html: str, detail_url: str) -> str:
        """Download attached PDFs from the detail page and return their extracted text."""
        if not self.max_pdf_attachments or not detail_html:
            return ""
        soup = BeautifulSoup(detail_html, "lxml")
        texts: list[str] = []
        seen_urls: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href") or "").strip()
            if not href.lower().endswith(".pdf"):
                continue
            url = urljoin(detail_url, href)
            if url in seen_urls:
                continue
            seen_urls.add(url)
            try:
                data = client.get_bytes(url)
            except Exception:
                continue
            try:
                from pypdf import PdfReader

                reader = PdfReader(io.BytesIO(data))
                text = "\n".join((page.extract_text() or "") for page in reader.pages[:4])
            except Exception:
                continue
            if text.strip():
                texts.append(text)
            if len(texts) >= self.max_pdf_attachments:
                break
        return "\n".join(texts)[:6000]


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

                body_text = BeautifulSoup(detail_html or "", "lxml").get_text("\n", strip=True)
                if is_registration_closed(title, body_text):
                    continue
                record = extract_course_from_page(
                    title=title,
                    html=detail_html or f"<html><body><h1>{title}</h1></body></html>",
                    detail_url=detail_url,
                    source_platform=self.source_name,
                    default_organizer=self.default_organizer,
                    created_at=created_date,
                )
                if self.max_pdf_attachments and detail_html:
                    pdf_text = self._pdf_attachment_text(client, detail_html, detail_url)
                    if pdf_text:
                        pdf_fee = extract_fee(pdf_text)
                        if pdf_fee:
                            record.fee = pdf_fee
                        pdf_period = extract_registration_period(pdf_text)
                        if pdf_period:
                            record.registration_period = pdf_period
                        if not record.course_time or record.course_time == "詳見簡章":
                            record.course_time = _schedule_span(pdf_text) or record.course_time
                if self.fee_table:
                    table_fee = _fee_range_from_table(detail_html)
                    if table_fee:
                        record.fee = table_fee
                if self.registration_url_is_detail:
                    record.registration_url = detail_url
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


_CATALOG_SPECS: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    ("AtptScraper", "atpt", "台灣遊戲治療學會", "台灣遊戲治療學會", ("https://www.atpt.org.tw/course.php", "https://www.atpt.org.tw/")),
    ("TcpuScraper", "tcpu", "中華民國諮商心理師公會全國聯合會", "中華民國諮商心理師公會全國聯合會", ("https://www.tcpu.org.tw/",)),
    ("TwcpaScraper", "twcpa", "臺灣諮商心理學會", "臺灣諮商心理學會", ("https://www.twcpa.org.tw/recentcourses",)),
    ("PsychoanalysisScraper", "psychoanalysis", "臺灣精神分析學會", "臺灣精神分析學會", ("https://psychoanalysis.org.tw/zh-Hant/event/list/6", "https://psychoanalysis.org.tw/")),
    ("SopScraper", "sop", "台灣精神醫學會", "台灣精神醫學會", ("https://www.sop.org.tw/",)),
    ("RmdarocScraper", "rmdaroc", "台灣心理復健協會", "台灣心理復健協會", ("https://sites.google.com/rmdaroc.org/signup/%E9%A6%96%E9%A0%81",)),
    ("TapScraper", "tap", "臺灣心理治療學會", "臺灣心理治療學會", ("https://www.tap.org.tw/",)),
    ("TposScraper", "tpos", "台灣心理腫瘤醫學學會", "台灣心理腫瘤醫學學會", ("http://www.tpos-society.org/",)),
    ("IaptcScraper", "iaptc", "台灣網路成癮防治學會", "台灣網路成癮防治學會", ("https://iaptc.asia.edu.tw/",)),
    ("TasctaiwanScraper", "tasctaiwan", "台灣性諮商學會", "台灣性諮商學會", ("https://tasctaiwan.tw/",)),
    ("AcftEftScraper", "acft_eft", "華人伴侶與家族治療協會／亞太EFT", "華人伴侶與家族治療協會", ("http://www.acft.org.tw/", "https://asia-eft.com/")),
    ("EcataScraper", "ecata", "台灣表創性藝術治療學會", "台灣表創性藝術治療學會", ("https://ecata.org.tw/",)),
    ("MindfulnessScraper", "mindfulness", "台灣正念發展協會", "台灣正念發展協會", ("https://www.mindfulness.org.tw/",)),
    ("TsosScraper", "tsos", "台灣自殺防治學會", "台灣自殺防治學會", ("https://www.tsos.org.tw/",)),
    ("BeclassScraper", "beclass", "Beclass 活動平台", "Beclass 活動平台", ("https://www.beclass.com/default.php?name=ShowList&op=catRank&range=T",)),
    ("TaipeiHealthScraper", "taipei_health", "臺北市政府衛生局", "臺北市政府衛生局", ("https://health.gov.taipei/", "https://health.gov.taipei/News.aspx?n=4E598A19194EA548")),
    ("KaohsiungHealthScraper", "kaohsiung_health", "高雄市政府衛生局", "高雄市政府衛生局", ("https://health.kcg.gov.tw/", "https://health.kcg.gov.tw/News.aspx?n=51623F92649C1BE2")),
)

for _cls_name, _sid, _sname, _org, _urls in _CATALOG_SPECS:
    globals()[_cls_name] = type(
        _cls_name,
        (GenericCatalogScraper,),
        {
            "source_id": _sid,
            "source_name": _sname,
            "default_organizer": _org,
            "base_url": _urls[0],
            "listing_urls": _urls,
            "registration_url_is_detail": _sid == "beclass",
            "max_pdf_attachments": 3 if _sid in ("taipei_health", "kaohsiung_health") else 0,
            "fee_table": _sid == "atpt",
        },
    )
