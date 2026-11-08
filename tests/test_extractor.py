"""Unit tests for CourseRecord model and rule-based extractor."""

from __future__ import annotations

import pytest

from scraper.extractor import (
    evaluate_clinical_credit,
    extract_course_from_page,
    extract_fee,
    extract_location_mode,
    extract_registration_period,
    extract_registration_url,
    extract_time_range,
    normalize_roc_date,
)
from scraper.models import COURSE_FIELD_NAMES, CREDIT_STATUS_VALUES, CourseRecord


class TestCourseRecordModel:
    """Tests for CourseRecord dataclass and 12-field schema contract."""

    def test_course_field_names_exact_order(self) -> None:
        expected = [
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
        assert COURSE_FIELD_NAMES == expected
        assert len(COURSE_FIELD_NAMES) == 12
        assert CREDIT_STATUS_VALUES == ("是", "否", "未知")

    def test_course_record_defaults_and_serialization(self) -> None:
        record = CourseRecord(
            course_name="臨床心理督導工作坊",
            organizer="台灣臨床心理學會",
            course_date="115/06/25",
            course_time="13:30–16:30",
            fee="$800",
            location_mode="線上",
            registration_url="https://forms.gle/example123",
            has_clinical_credit="是",
            credit_evidence="台灣臨床心理學會審核通過（認證字號：TACP1150123）",
            source_platform="台灣臨床心理學會",
            created_at="2026-11-08",
            registration_period="即日起至115/06/20",
        )
        as_dict = record.to_dict()
        assert list(as_dict.keys()) == COURSE_FIELD_NAMES
        assert as_dict["課程名稱"] == "臨床心理督導工作坊"
        assert as_dict["上課地點／方式"] == "線上"
        assert as_dict["是否有臨床心理師積分"] == "是"

        csv_row = record.to_csv_row()
        assert len(csv_row) == 12
        assert csv_row == [as_dict[k] for k in COURSE_FIELD_NAMES]

        restored = CourseRecord.from_dict(as_dict)
        assert restored == record

    def test_course_record_default_values(self) -> None:
        record = CourseRecord(
            course_name="測試課程",
            organizer="測試單位",
            course_date="115/07/01",
        )
        assert record.has_clinical_credit == "未知"
        assert record.course_time == ""
        assert record.fee == ""


class TestNormalizeRocDate:
    """Tests for normalize_roc_date across Western and ROC date formats."""

    @pytest.mark.parametrize(
        ("raw_text", "expected"),
        [
            ("2026/07/05", "115/07/05"),
            ("2026-01-09 ~ 2026-01-24", "115/01/09–115/01/24"),
            ("115年7月29日（星期三）", "115/07/29"),
            ("115年9月12日-9月13日", "115/09/12–115/09/13"),
            ("115.06.25", "115/06/25"),
            ("時間：2026年11月6日（五）", "115/11/06"),
            ("課程日期：115/08/15~08/16", "115/08/15–115/08/16"),
            ("2026/10/03(六)-10/04(日)", "115/10/03–115/10/04"),
        ],
    )
    def test_normalize_roc_date_formats(self, raw_text: str, expected: str) -> None:
        assert normalize_roc_date(raw_text) == expected

    def test_normalize_roc_date_prefers_course_date_over_registration_deadline(self) -> None:
        sample = (
            "報名期間：即日起至115年6月10日止\n"
            "上課日期：115年7月29日（星期三）09:00-16:00"
        )
        assert normalize_roc_date(sample) == "115/07/29"


class TestExtractTimeRange:
    """Tests for extract_time_range."""

    @pytest.mark.parametrize(
        ("raw_text", "expected"),
        [
            ("上課時間：9:30-12:30", "09:30–12:30"),
            ("時間：115年7月29日 09:30~17:00", "09:30–17:00"),
            ("13:30至16:30（共3小時）", "13:30–16:30"),
            ("時間：15:00", "15:00"),
            ("無時間資訊的段落", ""),
        ],
    )
    def test_extract_time_range(self, raw_text: str, expected: str) -> None:
        assert extract_time_range(raw_text) == expected


class TestExtractFee:
    """Tests for extract_fee."""

    @pytest.mark.parametrize(
        ("raw_text", "expected_substring"),
        [
            ("課程費用：免費（需事先報名）", "免費"),
            ("本活動免收報名費，歡迎踴躍參加。", "免費"),
            ("費用：會員 $800 / 非會員 $1,200", "$800"),
            ("收費標準：$1500（含教材）", "$1500（含教材）"),
            ("報名費：新台幣 2,000 元整", "2,000"),
        ],
    )
    def test_extract_fee(self, raw_text: str, expected_substring: str) -> None:
        result = extract_fee(raw_text)
        assert expected_substring in result

    def test_extract_fee_empty_when_unspecified(self) -> None:
        assert extract_fee("請於期限內完成線上報名。") == ""


class TestExtractLocationMode:
    """Tests for extract_location_mode."""

    def test_extract_labeled_location(self) -> None:
        text = "上課地點：北醫進修推廣部（台北市信義區吳興街250號）"
        assert "北醫進修推廣部" in extract_location_mode("臨床工作坊", text)

    def test_detect_online_keywords(self) -> None:
        text = "本課程採用 Zoom 線上視訊進行，課前寄發會議連結。"
        assert extract_location_mode("精神分析講座", text) == "線上"

    def test_detect_in_person_from_title_tag(self) -> None:
        assert extract_location_mode("【實體上課】兒童遊戲治療初階工作坊", "詳見簡章") == "實體"

    def test_detect_hybrid_mode(self) -> None:
        text = "辦理方式：實體與線上同步（Google Meet）"
        result = extract_location_mode("年會暨學術研討會", text)
        assert "實體" in result and "線上" in result


class TestExtractRegistrationPeriod:
    """Tests for extract_registration_period."""

    def test_labeled_registration_period(self) -> None:
        text = "報名期間：即日起至 115 年 6 月 20 日止"
        assert "即日起至 115 年 6 月 20 日" in extract_registration_period(text)

    def test_inline_即日起至(self) -> None:
        text = "請於即日起至2026/08/31前完成網路報名。"
        assert "即日起至2026/08/31" in extract_registration_period(text)

    def test_before_開放報名(self) -> None:
        text = "115/05/01~115/05/31 開放報名"
        assert "115/05/01~115/05/31" in extract_registration_period(text)


class TestExtractRegistrationUrl:
    """Tests for extract_registration_url."""

    def test_prefers_google_form_and_excludes_social_share(self) -> None:
        html = """
        <div>
          <a href="https://www.facebook.com/sharer/sharer.php?u=test">分享到FB</a>
          <a href="https://line.naver.jp/R/msg/text/?test">分享到LINE</a>
          <p>報名網址：<a href="https://forms.gle/abcDEF123">點此報名</a></p>
        </div>
        """
        url = extract_registration_url(html, "https://www.atcp.org.tw/modules/news/article.php?storyid=999")
        assert url == "https://forms.gle/abcDEF123"

    def test_falls_back_to_detail_url_when_no_registration_link(self) -> None:
        html = """
        <div>
          <a href="https://www.facebook.com/share.php?u=1">Share</a>
          <p>詳情請見內文說明。</p>
        </div>
        """
        detail_url = "https://www.atcp.org.tw/modules/news/article.php?storyid=888"
        assert extract_registration_url(html, detail_url) == detail_url

    def test_resolves_relative_registration_link(self) -> None:
        html = '<p><a href="/events/register/42">線上報名</a></p>'
        detail_url = "https://psychoanalysis.org.tw/courses/42"
        assert extract_registration_url(html, detail_url) == "https://psychoanalysis.org.tw/events/register/42"


class TestEvaluateClinicalCredit:
    """Tests for all 4 clinical credit judgment scenarios."""

    def test_scenario_1_whitelist_match(self) -> None:
        status, evidence = evaluate_clinical_credit(
            "一般課程內文",
            whitelist_match={"cert_no": "TACP1150088", "category": "專業課程"},
        )
        assert status == "是"
        assert evidence == "台灣臨床心理學會審核通過（認證字號：TACP1150088，性質：專業課程）"

    def test_scenario_2_explicit_clinical_psychologist_credit(self) -> None:
        text = (
            "一、主辦單位：臺灣精神分析學會\n"
            "二、繼續教育積分：臨床心理師、諮商心理師及精神科專科醫師繼續教育積分申請中。\n"
        )
        status, evidence = evaluate_clinical_credit(text)
        assert status == "是"
        assert "臨床心理師" in evidence

    def test_scenario_3a_explicit_no_credit(self) -> None:
        text = "注意事項：本講座為公益推廣性質，恕不提供繼續教育積分。"
        status, evidence = evaluate_clinical_credit(text)
        assert status == "否"
        assert "恕不提供繼續教育積分" in evidence

    def test_scenario_3b_only_other_professions_credit(self) -> None:
        text = "本工作坊將申請諮商心理師、社工師繼續教育積分。"
        status, evidence = evaluate_clinical_credit(text)
        assert status == "否"
        assert "諮商心理師" in evidence

    def test_scenario_4a_ambiguous_psychologist_credit(self) -> None:
        text = "本課程已申請心理師繼續教育積分。"
        status, evidence = evaluate_clinical_credit(text)
        assert status == "未知"
        assert "已申請心理師繼續教育積分" in evidence

    def test_scenario_4b_no_credit_mention_at_all(self) -> None:
        text = "歡迎對客體關係理論有興趣之助人工作者報名參加。"
        status, evidence = evaluate_clinical_credit(text)
        assert status == "未知"
        assert evidence == "課程公告內文未提及繼續教育積分資訊"


class TestExtractCourseFromPage:
    """End-to-end extraction tests on realistic ATCP and Psychoanalysis HTML pages."""

    def test_atcp_transferred_announcement_sample(self) -> None:
        title = "【轉知】臺北榮民總醫院辦理「115年度自殺防治守門人教育訓練」"
        html = """
        <html><body>
        <div class="news-content">
          <p>一、主辦單位：臺北榮民總醫院自殺防治中心</p>
          <p>二、課程日期：115年7月29日（星期三）</p>
          <p>三、上課時間：13:30至16:30</p>
          <p>四、上課地點：線上視訊課程（使用 Webex）</p>
          <p>五、報名期間：即日起至115年7月20日止</p>
          <p>六、費用：免費</p>
          <p>七、繼續教育積分：臨床心理師、諮商心理師、護理師繼續教育積分申請中。</p>
          <p>八、報名網址：<a href="https://www.beclass.com/rid=123456">https://www.beclass.com/rid=123456</a></p>
        </div>
        </body></html>
        """
        detail_url = "https://www.atcp.org.tw/modules/news/article.php?storyid=1024"
        record = extract_course_from_page(
            title=title,
            html=html,
            detail_url=detail_url,
            source_platform="中華民國臨床心理師公會全國聯合會",
            default_organizer="中華民國臨床心理師公會全國聯合會",
            created_at="2026-11-08",
        )
        assert record.course_name == title
        assert record.organizer == "臺北榮民總醫院自殺防治中心"
        assert record.course_date == "115/07/29"
        assert record.course_time == "13:30–16:30"
        assert record.fee == "免費"
        assert "線上" in record.location_mode
        assert record.registration_url == "https://www.beclass.com/rid=123456"
        assert record.has_clinical_credit == "是"
        assert "臨床心理師" in record.credit_evidence
        assert record.source_platform == "中華民國臨床心理師公會全國聯合會"
        assert record.created_at == "2026-11-08"
        assert "即日起至115年7月20日" in record.registration_period

    def test_psychoanalysis_course_sample(self) -> None:
        title = "2026秋季班｜佛洛伊德《夢的解析》導讀課程"
        html = """
        <html><body>
        <article>
          <p>時間：2026/09/12 - 2026/09/13 09:30-16:30</p>
          <p>地點：臺灣精神分析學會教室（台北市大安區復興南路二段）</p>
          <p>費用：一般學員 $3,000 / 學生 $2,000</p>
          <p>本課程預計申請精神科專科醫師、臨床心理師及諮商心理師繼續教育積分。</p>
        </article>
        </body></html>
        """
        detail_url = "https://psychoanalysis.org.tw/events/95"
        record = extract_course_from_page(
            title=title,
            html=html,
            detail_url=detail_url,
            source_platform="臺灣精神分析學會",
            default_organizer="臺灣精神分析學會",
            created_at="2026-11-08",
        )
        assert record.organizer == "臺灣精神分析學會"
        assert record.course_date == "115/09/12–115/09/13"
        assert record.course_time == "09:30–16:30"
        assert "$3,000" in record.fee
        assert "臺灣精神分析學會教室" in record.location_mode
        assert record.registration_url == detail_url
        assert record.has_clinical_credit == "是"
        assert "臨床心理師" in record.credit_evidence
