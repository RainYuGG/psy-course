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
    "論文徵稿",
    "花絮回顧",
    "活動紀實",
    "課程回顧",
    "遊行實紀",
    "休假公告",
    "認證督導名單",
    "師資名單",
    "口試結果",
    "甄審",
    "特約商店",
    "決標公告",
    "採購案",
    "常年會費",
    "贊助繳費",
    "訂閱調查",
    "已額滿",
    "報名截止",
    "已截止",
)

GENERIC_MENU_TITLES: frozenset[str] = frozenset(
    {
        "遊療專業培訓",
        "學術研討會",
        "通訊繼續教育學分",
        "繼續教育課程",
        "繼續教育專區",
        "繼續教育補充專區",
        "一般課程",
        "年會專區",
        "查看近期課程",
        "精神分析工作坊",
        "跨領域工作坊",
        "入門課程",
        "臨床進階課程",
        "歷年課程",
        "近期課程",
        "課程專區",
        "課程/講座",
        "專業學習資源",
        "一般大眾成長課程",
        "人才培訓",
        "志工培訓",
        "培訓成果",
        "認證督導名單",
        "相關單位繼續教育課程",
        "學會主辦課程報名",
        "培訓課程",
        "課程資訊",
        "課程查詢",
        "課程總覽",
        "研習活動公告",
        "研習活動報名",
        "國內研討會",
        "國際論文精選與國際會議",
        "活動與消息",
        "最新消息",
        "本會活動訊息",
        "轉知活動訊息",
        "線上課程",
        "臨床課程",
        "課程報名",
        "精神分析臨床工作坊",
        "年會消息公告",
        "年會暨研討會",
        "歷屆年會",
        "近期年會",
        "年會論文集",
        "工作坊 Workshop",
        "2024年會系列活動",
        "2025年會系列活動",
        "2026年會系列活動",
    }
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
    "靜修營",
    "共學",
)


def is_likely_course_title(title: str) -> bool:
    """Return True only if title has a course indicator and no disqualifying non-course keywords."""
    cleaned = (title or "").strip()
    if not cleaned or len(cleaned) < 5 or cleaned in GENERIC_MENU_TITLES:
        return False

    if any(
        bad_kw in cleaned
        for bad_kw in (
            "誠徵",
            "徵才",
            "職缺",
            "錄取名單",
            "會議紀錄",
            "會員大會紀錄",
            "休假公告",
            "論文徵稿",
            "花絮回顧",
            "活動紀實",
            "課程回顧",
            "遊行實紀",
            "認證督導名單",
            "開啟「Spreadsheet",
            "組織架構",
            "申訴",
            "理事長簡介",
            "公會簡介",
            "公會章程",
            "網站連結",
            "政府機關",
            "地區公會",
            "其他線上學習網站",
            "資深優良",
            "口試結果",
            "甄選結果",
            "特約商店",
            "決標公告",
            "採購案",
            "常年會費",
            "贊助繳費",
            "訂閱調查",
            "人選參考名冊",
            "已額滿",
            "報名截止",
            "已截止",
        )
    ):
        return False

    has_non_course = any(kw in cleaned for kw in NON_COURSE_KEYWORDS)
    has_course_indicator = any(kw in cleaned for kw in COURSE_INDICATOR_KEYWORDS)

    if has_non_course and not has_course_indicator:
        return False

    return has_course_indicator


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
