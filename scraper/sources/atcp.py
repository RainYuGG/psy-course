"""Scraper for Association of Taiwan Clinical Psychologists (ATCP / 臨床心理師公會全聯會)."""

from __future__ import annotations

from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.extractor import extract_course_from_page, is_registration_closed
from scraper.http_client import HttpClient
from scraper.models import CourseRecord
from scraper.sources.base import BaseSourceScraper, is_likely_course_title
ATCP_TOPIC_URLS: tuple[str, ...] = (
    "https://www.atcp.org.tw/modules/news/index.php?storytopic=12",
    "https://www.atcp.org.tw/modules/news/index.php?storytopic=15",
)
ATCP_PLATFORM = "中華民國臨床心理師公會全國聯合會"


def _extract_atcp_article_html(full_html: str) -> str:
    """Extract the main article block and strip ATCP navigation/sidebar noise."""
    if not full_html:
        return ""
    soup = BeautifulSoup(full_html, "lxml")
    article_body = soup.find(class_=["article-body", "news-content", "itemBody", "comText"])
    if article_body is not None:
        return str(article_body)

    text_html = full_html
    if "NEWS" in text_html:
        text_html = text_html.split("NEWS", 1)[-1]
    for marker in ("中華民國臨床心理師公會全國聯合會 15", "其他線上學習網站", "Design by"):
        if marker in text_html:
            text_html = text_html.split(marker, 1)[0]
    return f"<div>{text_html}</div>"

class AtcpScraper(BaseSourceScraper):
    """Scrapes ATCP storytopic=12 (轉知活動訊息) and storytopic=15 (研習活動公告)."""

    source_id = "atcp"
    source_name = ATCP_PLATFORM
    default_organizer = ATCP_PLATFORM
    base_url = ATCP_TOPIC_URLS[0]

    def __init__(self, max_items_per_topic: int = 15) -> None:
        self.max_items_per_topic = max_items_per_topic

    def scrape(self, client: HttpClient, created_at: str = "") -> list[CourseRecord]:
        created_date = created_at or date.today().isoformat()
        seen_urls: set[str] = set()
        records: list[CourseRecord] = []

        for topic_url in ATCP_TOPIC_URLS:
            list_html = client.get_text(topic_url)
            soup = BeautifulSoup(list_html or "", "lxml")
            count = 0

            for anchor in soup.find_all("a", href=True):
                raw_href = str(anchor.get("href", "")).strip()
                if "article.php" not in raw_href or "storyid=" not in raw_href:
                    continue

                title = anchor.get_text(" ", strip=True)
                if not is_likely_course_title(title):
                    continue

                detail_url = urljoin(topic_url, raw_href)
                if detail_url in seen_urls:
                    continue
                seen_urls.add(detail_url)

                try:
                    detail_html = client.get_text(detail_url)
                    body_html = _extract_atcp_article_html(detail_html)
                    if is_registration_closed(title, BeautifulSoup(body_html, "lxml").get_text("\n", strip=True)):
                        continue
                    record = extract_course_from_page(
                        title=title,
                        html=body_html,
                        detail_url=detail_url,
                        source_platform=self.source_name,
                        default_organizer=self.default_organizer,
                        created_at=created_date,
                    )
                    records.append(record)
                    count += 1
                except Exception:
                    continue
                if count >= self.max_items_per_topic:
                    break

        return records
