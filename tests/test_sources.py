"""Unit tests for HTTP client, TACLIP credit whitelist, ATCP scraper, and catalog scrapers."""

from __future__ import annotations

import httpx
import json
import pytest

from scraper.http_client import HttpClient
from scraper.models import CourseRecord
from scraper.sources import ALL_SCRAPERS, fetch_all_sources
from scraper.sources.atcp import AtcpScraper
from scraper.sources.accupass import AccupassScraper
from scraper.sources.base import (
    COURSE_INDICATOR_KEYWORDS,
    NON_COURSE_KEYWORDS,
    BaseSourceScraper,
    is_likely_course_title,
)
from scraper.sources.catalog_scrapers import (
    AcftEftScraper,
    AtptScraper,
    EcataScraper,
    IaptcScraper,
    MindfulnessScraper,
    PsychoanalysisScraper,
    RmdarocScraper,
    SopScraper,
    TapScraper,
    TasctaiwanScraper,
    TcpuScraper,
    TposScraper,
    TsosScraper,
    TwcpaScraper,
)
from scraper.sources.taclip_whitelist import (
    TaclipWhitelistScraper,
    WhitelistEntry,
    parse_taclip_whitelist_html,
)


class FakeHttpClient:
    """In-memory fake HttpClient for deterministic offline tests."""

    def __init__(
        self,
        responses: dict[str, str | Exception],
        post_responses: dict[str, str | Exception] | None = None,
    ) -> None:
        self.responses = responses
        self.post_responses = post_responses or {}
        self.requested_urls: list[str] = []
        self.post_bodies: list[tuple[str, dict]] = []
    def get_text(self, url: str) -> str:
        self.requested_urls.append(url)
        if url not in self.responses:
            raise httpx.HTTPStatusError(
                f"404 Not Found for {url}",
                request=httpx.Request("GET", url),
                response=httpx.Response(404),
            )
        val = self.responses[url]
        if isinstance(val, Exception):
            raise val
        return val

    def post_json(self, url: str, payload: dict, headers: dict | None = None) -> str:
        self.post_bodies.append((url, payload))
        if url not in self.post_responses:
            raise httpx.RequestError(f"no POST response configured for {url}")
        val = self.post_responses[url]
        if isinstance(val, Exception):
            raise val
        return val


class TestHttpClient:
    """Tests for HttpClient retry and SSL fallback behavior."""

    def test_http_client_retries_on_request_error_and_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        attempts = {"count": 0}

        def fake_request(self_client: httpx.Client, method: str, url: str, **kwargs: object) -> httpx.Response:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise httpx.ConnectTimeout("Simulated timeout")
            return httpx.Response(
                200,
                text="<html><body>OK</body></html>",
                request=httpx.Request(method, url),
            )

        monkeypatch.setattr(httpx.Client, "request", fake_request)
        client = HttpClient(timeout=5.0, retries=2)
        text = client.get_text("https://example.org/test")
        assert "OK" in text
        assert attempts["count"] == 2

    def test_http_client_falls_back_to_verify_false_on_ssl_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[bool] = []

        def fake_get_with_verify(url: str, verify: bool) -> str:
            calls.append(verify)
            if verify:
                raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
            return "<html><body>Legacy SSL Site</body></html>"

        client = HttpClient(timeout=5.0, retries=1)
        monkeypatch.setattr(client, "_fetch_with_verify", fake_get_with_verify)
        result = client.get_text("https://legacy-assoc.org.tw/courses")
        assert "Legacy SSL Site" in result
        assert calls == [True, False]


class TestCourseTitleFiltering:
    """Tests for NON_COURSE_KEYWORDS and is_likely_course_title."""

    def test_non_course_keywords_present(self) -> None:
        for kw in ("誠徵", "徵才", "招募", "職缺", "錄取名單", "理監事", "會員大會紀錄"):
            assert kw in NON_COURSE_KEYWORDS
        assert len(COURSE_INDICATOR_KEYWORDS) >= 5

    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("【誠徵】馬偕紀念醫院精神醫學部誠徵契約臨床心理師一名", False),
            ("【徵才】臺大醫院臨床心理中心職缺公告", False),
            ("115年度第2次理監事聯席會議紀錄", False),
            ("本會端午節連續假期休假公告", False),
            ("組織架構", False),
            ("申訴說明", False),
            ("課程/講座", False),
            ("高雄市政府衛生局長期照顧管理中心約聘照顧管理督導甄選結果", False),
            ("-已額滿-2026台灣遊戲治療學會年會專業工作坊", False),
            ("115年度臨床心理師繼續教育課程：創傷知情實務工作坊", True),
            ("【轉知】2026年自殺防治守門人教育訓練研習會", True),
            ("精神分析取向個別督導與案例討論講座", True),
            ("【招募學員】正念減壓（MBSR）八週線上培訓課程", True),
        ],
    )
    def test_is_likely_course_title(self, title: str, expected: bool) -> None:
        assert is_likely_course_title(title) is expected


class TestTaclipWhitelistScraper:
    """Tests for TACLIP checked-list Ninja Table parsing and announcement scraping."""

    TACLIP_CHECKED_LIST_HTML = """
    <html><body>
      <table id="footable_3078" class="foo-table ninja_table">
        <thead>
          <tr>
            <th>認證字號</th>
            <th>課程性質</th>
            <th>開始日期</th>
            <th>開課單位</th>
            <th>課程名稱</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>TACP1150101</td>
            <td>專業課程</td>
            <td>115/07/29</td>
            <td>臺北榮民總醫院自殺防治中心</td>
            <td>115年度自殺防治守門人教育訓練</td>
          </tr>
          <tr>
            <td>TACP1150102</td>
            <td>專業倫理、專業法規</td>
            <td>2026-08-15</td>
            <td>台灣臨床心理學會</td>
            <td>臨床心理實務倫理與法規案例研討會</td>
          </tr>
        </tbody>
      </table>
    </body></html>
    """

    TACLIP_HOME_HTML = """
    <html><body>
      <section class="news-list">
        <article>
          <h3><a href="https://taclip.org.tw/2026/06/01/course-neuro/">115年臨床神經心理學進階工作坊</a></h3>
        </article>
        <article>
          <h3><a href="https://taclip.org.tw/2026/06/02/job-opening/">【徵才專區】某醫院誠徵臨床心理師</a></h3>
        </article>
      </section>
    </body></html>
    """

    TACLIP_DETAIL_HTML = """
    <html><body>
      <h1>115年臨床神經心理學進階工作坊</h1>
      <div class="entry-content">
        <p>主辦單位：台灣臨床心理學會</p>
        <p>課程日期：115年10月18日（星期日）</p>
        <p>上課時間：09:00-16:30</p>
        <p>上課地點：國立臺灣大學心理學系北館視聽教室</p>
        <p>費用：會員 $1,000 / 非會員 $1,500</p>
        <p>繼續教育積分：臨床心理師繼續教育積分申請中。</p>
        <p>報名期間：即日起至115年10月5日止</p>
        <p>報名連結：<a href="https://forms.gle/taclipNeuro2026">線上報名表單</a></p>
      </div>
    </body></html>
    """

    def test_parse_taclip_whitelist_html_extracts_entries_and_course_records(self) -> None:
        entries, records = parse_taclip_whitelist_html(
            self.TACLIP_CHECKED_LIST_HTML, created_at="2026-11-08"
        )
        assert len(entries) == 2
        assert entries[0] == WhitelistEntry(
            cert_no="TACP1150101",
            category="專業課程",
            start_date_roc="115/07/29",
            organizer="臺北榮民總醫院自殺防治中心",
            course_name="115年度自殺防治守門人教育訓練",
        )
        assert entries[1].start_date_roc == "115/08/15"

        assert len(records) == 2
        r0 = records[0]
        assert r0.course_name == "115年度自殺防治守門人教育訓練"
        assert r0.organizer == "臺北榮民總醫院自殺防治中心"
        assert r0.course_date == "115/07/29"
        assert r0.has_clinical_credit == "是"
        assert "台灣臨床心理學會審核通過（認證字號：TACP1150101，性質：專業課程）" == r0.credit_evidence
        assert r0.source_platform == "台灣臨床心理學會（審核通過課程總表）"
        assert r0.created_at == "2026-11-08"
        assert r0.registration_url != ""

    def test_taclip_scraper_combines_checked_list_and_announcements_excluding_jobs(self) -> None:
        fake_client = FakeHttpClient(
            {
                "https://taclip.org.tw/checked-list/": self.TACLIP_CHECKED_LIST_HTML,
                "https://taclip.org.tw/": self.TACLIP_HOME_HTML,
                "https://taclip.org.tw/2026/06/01/course-neuro/": self.TACLIP_DETAIL_HTML,
            }
        )
        scraper = TaclipWhitelistScraper()
        records = scraper.scrape(fake_client, created_at="2026-11-08")  # type: ignore[arg-type]
        names = [r.course_name for r in records]
        assert "115年度自殺防治守門人教育訓練" in names
        assert "115年臨床神經心理學進階工作坊" in names
        assert not any("徵才" in n for n in names)
        assert len(scraper.last_whitelist_entries) == 2


class TestAtcpScraper:
    """Tests for ATCP (臨床心理師公會全聯會) storytopic=12 & 15 scraper."""

    ATCP_TOPIC_12_HTML = """
    <html><body>
      <table>
        <tr>
          <td><a href="article.php?storyid=2001">【轉知】臺北榮民總醫院辦理「115年度自殺防治守門人教育訓練」</a></td>
        </tr>
        <tr>
          <td><a href="article.php?storyid=2002">【徵才】某診所誠徵專任臨床心理師2名</a></td>
        </tr>
      </table>
    </body></html>
    """

    ATCP_TOPIC_15_HTML = """
    <html><body>
      <table>
        <tr>
          <td><a href="/modules/news/article.php?storyid=2003">全聯會辦理「115年臨床心理師網路繼續教育講座—創傷評估」</a></td>
        </tr>
      </table>
    </body></html>
    """

    ATCP_ARTICLE_2001_HTML = """
    <html><body>
      <div class="header">導覽列無關文字</div>
      <div>NEWS</div>
      <div class="article-body">
        <p>一、主辦單位：臺北榮民總醫院自殺防治中心</p>
        <p>二、課程日期：115年7月29日（星期三）</p>
        <p>三、上課時間：13:30–16:30</p>
        <p>四、上課地點：線上視訊（Webex）</p>
        <p>五、費用：免費</p>
        <p>六、繼續教育積分：臨床心理師繼續教育積分申請中。</p>
        <p>七、報名網址：<a href="https://www.beclass.com/rid=999111">點此報名</a></p>
      </div>
    </body></html>
    """

    ATCP_ARTICLE_2003_HTML = """
    <html><body>
      <div>NEWS</div>
      <div class="article-body">
        <p>主辦單位：中華民國臨床心理師公會全國聯合會</p>
        <p>上課日期：2026/08/22 09:00~12:00</p>
        <p>上課方式：Zoom 線上課程</p>
        <p>報名費用：會員免費，非會員 $500</p>
        <p>報名期間：即日起至2026/08/15止</p>
        <p>本課程提供臨床心理師繼續教育積分 3.6 點。</p>
      </div>
    </body></html>
    """

    def test_atcp_scraper_extracts_courses_and_filters_job_posts(self) -> None:
        fake_client = FakeHttpClient(
            {
                "https://www.atcp.org.tw/modules/news/index.php?storytopic=12": self.ATCP_TOPIC_12_HTML,
                "https://www.atcp.org.tw/modules/news/index.php?storytopic=15": self.ATCP_TOPIC_15_HTML,
                "https://www.atcp.org.tw/modules/news/article.php?storyid=2001": self.ATCP_ARTICLE_2001_HTML,
                "https://www.atcp.org.tw/modules/news/article.php?storyid=2003": self.ATCP_ARTICLE_2003_HTML,
            }
        )
        scraper = AtcpScraper()
        records, status = scraper.safe_scrape(fake_client, created_at="2026-11-08")  # type: ignore[arg-type]

        assert status["status"] == "ok"
        assert len(records) == 2

        # Job post storyid=2002 should never even be fetched or returned
        assert "https://www.atcp.org.tw/modules/news/article.php?storyid=2002" not in fake_client.requested_urls

        r1 = records[0]
        assert "115年度自殺防治守門人教育訓練" in r1.course_name
        assert r1.organizer == "臺北榮民總醫院自殺防治中心"
        assert r1.course_date == "115/07/29"
        assert r1.course_time == "13:30–16:30"
        assert r1.fee == "免費"
        assert r1.registration_url == "https://www.beclass.com/rid=999111"
        assert r1.has_clinical_credit == "是"
        assert r1.source_platform == "中華民國臨床心理師公會全國聯合會"

        r2 = records[1]
        assert r2.course_date == "115/08/22"
        assert r2.course_time == "09:00–12:00"
        assert r2.has_clinical_credit == "是"


class TestAtcpArticleChrome:
    """ATCP pages print the post time next to the title; it is not the course date."""

    LIST_HTML = """
    <html><body><table><tr><td>
      <a href="article.php?storyid=727">臺北市立聯合院失智症中心-115/5/30（六）失智症專業人員培訓課程＜心理師＞</a>
    </td></tr></table></body></html>
    """

    ARTICLE_HTML = """
    <html><body>
    <div class="page-title"><h2>NEWS</h2></div>
    <div class="row page-content"><div class="col-12">
      <div class="news-heading mb-4">
        <h1>臺北市立聯合院失智症中心-115/5/30（六）失智症專業人員培訓課程＜心理師＞</h1>
        <ul class="list-unstyled clearfix">
          <li class="float-start"><a href="#">轉知活動訊息</a></li>
          <li class="float-start">作者：<a href="#">管理員</a></li>
          <li class="float-start">2026-05-11 15:45:50 ‧ 402次閱讀</li>
        </ul>
      </div>
      <ul class="share-buttons clearfix"><li><a href="https://www.facebook.com/sharer/sharer.php?u=x">分享</a></li></ul>
      <div class="news-body">
        115年聯醫失智照護配方 – 心理師<br>
        報名日期：115/4/22～115/5/17開放報名，額滿則提前截止。<br>
        地點 : 臺北市立聯合醫院 中興院區第一會議室<br>
        費用 : 免費<br>
        學分申請中：諮商心理師積分、臨床心理師積分、<br>
        報名連結：https://reurl.cc/zQrzla
      </div>
    </div></div>
    <div class="sidebar"><ul><li>繼續教育相關法規 5</li><li>轉知活動訊息 239</li></ul></div>
    </body></html>
    """

    def test_post_time_and_registration_window_are_not_course_date(self) -> None:
        fake_client = FakeHttpClient(
            {
                "https://www.atcp.org.tw/modules/news/index.php?storytopic=12": self.LIST_HTML,
                "https://www.atcp.org.tw/modules/news/index.php?storytopic=15": "<html></html>",
                "https://www.atcp.org.tw/modules/news/article.php?storyid=727": self.ARTICLE_HTML,
            }
        )
        records, status = AtcpScraper().safe_scrape(fake_client, created_at="2026-11-08")  # type: ignore[arg-type]

        assert status["status"] == "ok"
        assert len(records) == 1
        record = records[0]
        assert record.course_date == "115/05/30"
        assert record.fee == "免費"
        assert record.registration_url == "https://reurl.cc/zQrzla"


class TestAccupassScraper:
    """Tests for the AccuPass SearchEvents JSON API scraper."""

    def test_accupass_searches_keywords_filters_and_builds_records(self) -> None:
        api_payload = json.dumps(
            {
                "total": 3,
                "items": [
                    {
                        "eventIdNumber": "111",
                        "name": "115年度創傷知情臨床實務工作坊",
                        "startDateTime": "2026-12-20T01:00:00Z",
                        "eventPlaceType": "Offline",
                    },
                    {
                        "eventIdNumber": "222",
                        "name": "理監事會議紀錄",
                        "startDateTime": "2026-12-20T01:00:00Z",
                    },
                    {
                        "eventIdNumber": "333",
                        "name": "110年度舊課程回顧講座",
                        "startDateTime": "2020-01-01T01:00:00Z",
                    },
                ],
            }
        )
        detail = json.dumps(
            {
                "eventIdNumber": "111",
                "title": "115年度創傷知情臨床實務工作坊",
                "isFree": True,
                "eventPlaceType": "Offline",
                "eventTimeObj": {
                    "startDateTime": "2026-12-20T14:00:00",
                    "endDateTime": "2026-12-20T17:00:00",
                },
                "registerBtn": {"isDisabled": False, "price": 0, "currency": "NT$"},
                "organizer": {"title": "創傷治療學會"},
                "address": "台北市大安區某路1號",
                "description": "本課程申請臨床心理師繼續教育積分。",
            }
        )
        fake = FakeHttpClient(
            responses={"https://api.accupass.com/v3/events/111": detail},
            post_responses={"https://api.accupass.com/v3/search/SearchEvents": api_payload},
        )
        scraper = AccupassScraper()
        records = scraper.scrape(fake, created_at="2026-11-09")

        assert len(records) == 1
        assert records[0].course_name == "115年度創傷知情臨床實務工作坊"
        assert records[0].course_date == "115/12/20"
        assert records[0].course_time == "14:00–17:00"
        assert records[0].fee == "免費"
        assert records[0].location_mode == "實體"
        assert records[0].organizer == "創傷治療學會"
        assert records[0].has_clinical_credit == "是"
        assert records[0].registration_url == "https://www.accupass.com/event/111"
        assert len(fake.post_bodies) == 3
        assert all(b[1]["keyword"] for b in fake.post_bodies)
        assert "https://api.accupass.com/v3/events/222" not in fake.requested_urls

    def test_accupass_zero_price_with_free_tag_marks_fee_free(self) -> None:
        api_payload = json.dumps(
            {
                "total": 1,
                "items": [
                    {
                        "eventIdNumber": "444",
                        "name": "115年度免費公開講座",
                        "startDateTime": "2026-12-20T01:00:00Z",
                    },
                ],
            }
        )
        detail = json.dumps(
            {
                "eventIdNumber": "444",
                "isFree": False,
                "eventPlaceType": "Online",
                "eventTimeObj": {
                    "startDateTime": "2026-12-20T14:00:00",
                    "endDateTime": "2026-12-20T15:00:00",
                },
                "registerBtn": {"isDisabled": False, "price": 0, "currency": "NT$"},
                "tags": [{"name": "免費"}],
            }
        )
        fake = FakeHttpClient(
            responses={"https://api.accupass.com/v3/events/444": detail},
            post_responses={"https://api.accupass.com/v3/search/SearchEvents": api_payload},
        )
        records = AccupassScraper().scrape(fake, created_at="2026-11-09")
        assert len(records) == 1
        assert records[0].fee == "免費"


class TestCatalogScrapersAndFaultIsolation:
    """Tests for the 17 association/platform catalog scrapers, ALL_SCRAPERS registry, and HTTP 503 fault isolation."""

    def test_all_20_scrapers_registered(self) -> None:
        scraper_ids = [s.source_id for s in ALL_SCRAPERS]
        expected_ids = [
            "taclip",
            "atcp",
            "atpt",
            "tcpu",
            "twcpa",
            "psychoanalysis",
            "sop",
            "rmdaroc",
            "tap",
            "tpos",
            "iaptc",
            "tasctaiwan",
            "acft_eft",
            "ecata",
            "mindfulness",
            "tsos",
            "beclass",
            "taipei_health",
            "kaohsiung_health",
            "accupass",
        ]
        assert scraper_ids == expected_ids

    def test_catalog_scraper_parses_listing_and_detail_pages(self) -> None:
        listing_html = """
        <html><body>
          <ul class="course-list">
            <li>
              <a href="/courses/play-therapy-101">【實體工作坊】2026年沙遊與兒童遊戲治療初階訓練課程</a>
            </li>
            <li>
              <a href="/news/board-minutes">第十二屆第二次理監事會議紀錄</a>
            </li>
          </ul>
        </body></html>
        """
        detail_html = """
        <html><body>
          <h1>【實體工作坊】2026年沙遊與兒童遊戲治療初階訓練課程</h1>
          <div class="content">
            <p>主辦單位：台灣遊戲治療學會</p>
            <p>課程日期：115年9月12日-9月13日</p>
            <p>上課時間：09:00~16:30</p>
            <p>上課地點：國立臺灣師範大學進修推廣學院</p>
            <p>課程費用：$3,600</p>
            <p>繼續教育積分：臨床心理師、諮商心理師繼續教育積分申請中。</p>
            <p>報名網址：<a href="https://forms.gle/atptPlay101">點我報名</a></p>
          </div>
        </body></html>
        """
        scraper = AtptScraper()
        fake_client = FakeHttpClient(
            {
                scraper.base_url: listing_html,
                "https://www.atpt.org.tw/courses/play-therapy-101": detail_html,
            }
        )
        records, status = scraper.safe_scrape(fake_client, created_at="2026-11-08")  # type: ignore[arg-type]
        assert status["status"] == "ok"
        assert len(records) == 1
        rec = records[0]
        assert rec.course_name == "【實體工作坊】2026年沙遊與兒童遊戲治療初階訓練課程"
        assert rec.course_date == "115/09/12–115/09/13"
        assert rec.course_time == "09:00–16:30"
        assert rec.fee == "$3,600"
        assert rec.registration_url == "https://forms.gle/atptPlay101"
        assert rec.has_clinical_credit == "是"

    def test_fault_isolation_when_tsos_returns_http_503(self) -> None:
        scraper = TsosScraper()
        http_503 = httpx.HTTPStatusError(
            "503 Service Unavailable",
            request=httpx.Request("GET", scraper.base_url),
            response=httpx.Response(503),
        )
        fake_client = FakeHttpClient({scraper.base_url: http_503})
        records, status = scraper.safe_scrape(fake_client, created_at="2026-11-08")  # type: ignore[arg-type]
        assert records == []
        assert status["source"] == scraper.source_name
        assert status["status"] == "error"
        assert "503" in status["error"]

    def test_fetch_all_sources_isolates_errors_and_returns_whitelist_and_statuses(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_client = FakeHttpClient(
            {
                "https://taclip.org.tw/checked-list/": TestTaclipWhitelistScraper.TACLIP_CHECKED_LIST_HTML,
                "https://taclip.org.tw/": "<html><body></body></html>",
            }
        )
        courses, whitelist_entries, statuses = fetch_all_sources(
            client=fake_client,  # type: ignore[arg-type]
            created_at="2026-11-08",
        )
        assert len(courses) == 2
        assert len(whitelist_entries) == 2
        assert len(statuses) == len(ALL_SCRAPERS)
        ok_sources = [s for s in statuses if s["status"] == "ok"]
        err_sources = [s for s in statuses if s["status"] == "error"]
        assert len(ok_sources) == 1
        assert len(err_sources) == len(ALL_SCRAPERS) - 1
