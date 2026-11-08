"""Data models and 12-field schema constants for course records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

COURSE_FIELD_NAMES: list[str] = [
    "課程名稱",
    "主辦單位",
    "課程日期",
    "上課時間",
    "費用",
    "上課地點／方式",
    "報名連結",
    "是否有臨床心理師積分",
    "積分判斷依據段落",
    "資料來源平台",
    "建立時間",
    "報名期間",
]

CREDIT_STATUS_VALUES = ("是", "否", "未知")


@dataclass
class CourseRecord:
    """Represents a single continuing education course record with all 12 required fields."""

    course_name: str
    organizer: str
    course_date: str
    course_time: str = ""
    fee: str = ""
    location_mode: str = ""
    registration_url: str = ""
    has_clinical_credit: str = "未知"
    credit_evidence: str = ""
    source_platform: str = ""
    created_at: str = ""
    registration_period: str = ""

    def __post_init__(self) -> None:
        if self.has_clinical_credit not in CREDIT_STATUS_VALUES:
            self.has_clinical_credit = "未知"

    def to_dict(self) -> dict[str, str]:
        """Serialize to an ordered dictionary keyed by the 12 Chinese field names."""
        return {
            "課程名稱": self.course_name,
            "主辦單位": self.organizer,
            "課程日期": self.course_date,
            "上課時間": self.course_time,
            "費用": self.fee,
            "上課地點／方式": self.location_mode,
            "報名連結": self.registration_url,
            "是否有臨床心理師積分": self.has_clinical_credit,
            "積分判斷依據段落": self.credit_evidence,
            "資料來源平台": self.source_platform,
            "建立時間": self.created_at,
            "報名期間": self.registration_period,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, str]) -> CourseRecord:
        """Construct a CourseRecord from a dictionary keyed by Chinese field names."""
        return cls(
            course_name=str(data.get("課程名稱", "")),
            organizer=str(data.get("主辦單位", "")),
            course_date=str(data.get("課程日期", "")),
            course_time=str(data.get("上課時間", "")),
            fee=str(data.get("費用", "")),
            location_mode=str(data.get("上課地點／方式", "")),
            registration_url=str(data.get("報名連結", "")),
            has_clinical_credit=str(data.get("是否有臨床心理師積分", "未知")) or "未知",
            credit_evidence=str(data.get("積分判斷依據段落", "")),
            source_platform=str(data.get("資料來源平台", "")),
            created_at=str(data.get("建立時間", "")),
            registration_period=str(data.get("報名期間", "")),
        )

    def to_csv_row(self) -> list[str]:
        """Return field values in the exact COURSE_FIELD_NAMES order."""
        as_dict = self.to_dict()
        return [as_dict[field_name] for field_name in COURSE_FIELD_NAMES]
