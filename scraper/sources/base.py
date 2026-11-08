"""Base scraper interface and non-course title filtering rules."""

from __future__ import annotations

from abc import ABC, abstractmethod

from scraper.http_client import HttpClient
from scraper.models import CourseRecord

NON_COURSE_KEYWORDS: tuple[str, ...] = (
    "誠徵",
    "徵才",
    "招募",
    "職缺",
    "錄取名單",
    "理監事",
    "會員大會紀錄",
    "會議紀錄",
    "法規",
    "辦法修正",
    "獎學金",
    "徵稿",
    "休假公告",
)

COURSE_INDICATOR_KEYWORDS: tuple[str, ...] = (
    "課程",
    "工作坊",
    "研討會",
    "講座",
    "訓練",
    "研習",
    "培訓",
    "論壇",
    "演講",
    "督導",
    "讀書會",
    "繼續教育",
    "學分班",
    "年會",
)


def is_likely_course_title(title: str) -> bool:
    """Return False if title matches non-course keywords without course indicators."""
    cleaned = (title or "").strip()
    if not cleaned or len(cleaned) < 4:
        return False

    # Pure job postings or administrative records
    if any(job_kw in cleaned for job_kw in ("誠徵", "徵才", "職缺", "錄取名單", "會議紀錄", "會員大會紀錄", "休假公告")):
        return False

    has_non_course = any(kw in cleaned for kw in NON_COURSE_KEYWORDS)
    has_course_indicator = any(kw in cleaned for kw in COURSE_INDICATOR_KEYWORDS)

    if has_non_course and not has_course_indicator:
        return False

    return True


class BaseSourceScraper(ABC):
    """Abstract base scraper for an association or course platform."""

    source_id: str = ""
    source_name: str = ""
    default_organizer: str = ""
    base_url: str = ""

    @abstractmethod
    def scrape(self, client: HttpClient, created_at: str = "") -> list[CourseRecord]:
        """Scrape courses from this source."""

    def safe_scrape(
        self, client: HttpClient, created_at: str = ""
    ) -> tuple[list[CourseRecord], dict[str, str]]:
        """Execute scrape with fault isolation so one failing site never aborts the pipeline."""
        try:
            courses = self.scrape(client, created_at=created_at)
            return (
                courses,
                {
                    "source_id": self.source_id,
                    "source": self.source_name,
                    "status": "ok",
                    "count": str(len(courses)),
                    "error": "",
                },
            )
        except Exception as exc:
            return (
                [],
                {
                    "source_id": self.source_id,
                    "source": self.source_name,
                    "status": "error",
                    "count": "0",
                    "error": str(exc),
                },
            )
