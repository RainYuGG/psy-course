# 臨床心理師繼續教育課程彙整查詢平台 (`psy-course-aggregator`)

自動從台灣臨床心理學會「審核通過課程總表」與 15 個心理治療／諮商／精神醫學相關學會與公會官網抓取研習課程公告，透過純規則引擎（HTML DOM + 台灣公文／簡章正規表示式，**零付費 LLM API Key**）抽取 12 個標準欄位、跨站去重並互補合併，產出：

1. **GitHub Pages 響應式網頁查詢介面**（`docs/index.html`、`docs/style.css`、`docs/app.js`）
2. **UTF-8 with BOM 編碼之 CSV 檔案**（`docs/data/courses.csv`），支援 Excel 直接開啟不亂碼
3. **Google Sheets 免金鑰 `=IMPORTDATA()` 自動同步**

---

## 12 個標準輸出欄位（CSV 與 JSON 嚴格依序）

1. `課程名稱`
2. `主辦單位`
3. `課程日期`（民國年斜線格式 `YYY/MM/DD`，如 `115/06/25` 或跨日 `115/09/12–115/09/13`）
4. `上課時間`（如 `13:30–16:30`，未載明則留空）
5. `費用`（如 `免費`、`$800`，未載明則留空）
6. `上課地點／方式`（如 `線上`、`實體` 或具體場地名稱）
7. `報名連結`（優先取外部報名表單網址，否則回退至該公告明細頁網址）
8. `是否有臨床心理師積分`（嚴格為 `是`、`否`、`未知` 三擇一）
9. `積分判斷依據段落`（學會審核通過認證字號 `TACP...` 或公告內文提及繼續教育積分之原句）
10. `資料來源平台`（各公學會或審核通過課程總表名稱）
11. `建立時間`（資料抓取日期 `YYYY-MM-DD`）
12. `報名期間`（公告載明之報名起迄期間，未載明則留空）

---

## 支援的官方網站（19 個來源）

| 來源 | 網站 | 類型 |
|---|---|---|
| 中華民國臨床心理師公會全國聯合會 | `atcp.org.tw`（2 個新聞分類） | 課程公告（主要轉知來源） |
| 台灣臨床心理學會 | `taclip.org.tw/checked-list/` | 積分白名單（非課程來源） |
| 台灣遊戲治療學會 | `atpt.org.tw` | 課程目錄 |
| 中華民國諮商心理師公會全國聯合會 | `tcpu.org.tw` | 課程目錄 |
| 臺灣諮商心理學會 | `twcpa.org.tw/recentcourses` | 課程目錄 |
| 臺灣精神分析學會 | `psychoanalysis.org.tw` | 課程目錄 |
| 台灣精神醫學會 | `sop.org.tw` | 課程目錄 |
| 台灣心理復健協會 | `sites.google.com/rmdaroc.org` | 課程目錄 |
| 臺灣心理治療學會 | `tap.org.tw` | 課程目錄 |
| 台灣心理腫瘤醫學學會 | `tpos-society.org`（HTTP） | 課程目錄 |
| 台灣網路成癮防治學會 | `iaptc.asia.edu.tw` | 課程目錄 |
| 台灣性諮商學會 | `tasctaiwan.tw` | 課程目錄 |
| 華人伴侶與家族治療協會／亞太EFT | `acft.org.tw` + `asia-eft.com` | 課程目錄 |
| 台灣表創性藝術治療學會 | `ecata.org.tw` | 課程目錄 |
| 台灣正念發展協會 | `mindfulness.org.tw` | 課程目錄 |
| 台灣自殺防治學會 | `tsos.org.tw` | 課程目錄 |
| Beclass 活動平台 | `beclass.com`（專業講座/訓練分類） | 活動平台（僅當日熱門講座/訓練） |
| 臺北市政府衛生局 | `health.gov.taipei`（新聞公告） | 衛教課程／轉知公告 |
| 高雄市政府衛生局 | `health.kcg.gov.tw`（新聞公告） | 衛教課程／轉知公告 |

各來源獨立容錯隔離：單一站點維護或連線失敗不影響其他網站，網頁頁尾「來源狀態」會顯示本次成功連線的站點數。

## 尚未支援的來源（2026-11 實測）

| 來源 | 原因 |
|---|---|
| KKTIX `kktix.com` | 搜尋結果頁 403 反爬蟲封鎖 |
| EventPal `eventpal.com.tw` | Cloudflare 機器人驗證，純 HTTP 無法通過 |
| AccuPass `accupass.com` | 搜尋結果為 JS 渲染，無伺服器端搜尋列表 |
| Beclass `beclass.com` | 站內關鍵字搜尋為 JS 渲染（現僅支援「當日熱門講座/訓練」分類） |
| 台灣認知行為治療學會 `tcbt.org.tw` | 網域不存在（NXDOMAIN），需重新提供官網網址 |
| 台灣多元文化輔導與諮商學會 `tamic.org.tw` | 網域不存在（NXDOMAIN） |
| 台灣表達性藝術治療學會 `taeta.org.tw` | 網域不存在（NXDOMAIN） |
| 台灣家族治療學會 `familytherapy.org.tw` | 網域不存在（NXDOMAIN） |
| 台灣伴侶與家庭治療學會 `taft.org.tw` | 網域存在但無 A 紀錄，無法連線 |
| [FB 社團] 臨床心理異言堂 | Facebook 登入牆，免 API key 無法抓取 |
| [Facebook] 台灣青少年心理治療與研究學會 | Facebook 登入牆 |
| 台灣分析治療學會 | 未提供官網網址 |
| 台灣藥癮防治協會 | 未提供官網網址 |
| 國軍醫院心理衛生中心 | 無公開官網網址 |
| 醫學中心精神科／心理部門（台大、馬偕、成大、彰基等） | 各院課程公告頁不統一，需提供各院頁面清單 |
| 大學輔導中心／教育推廣部（師大、政大、北醫、亞大等） | 各校頁面結構不同，需提供各校頁面清單 |
| 其他縣市衛生局 | 已支援台北市、高雄市；其餘縣市可補公告頁網址後逐步加入 |

---

## 本地端安裝與執行方式

### 1. 建立虛擬環境並安裝相依套件

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. 執行爬蟲更新 `docs/data/courses.csv` 與 `docs/data/courses.json`

```bash
python -m scraper.cli --output-dir docs/data
```

若在無外網環境測試管道，可使用離線種子模式：

```bash
python -m scraper.cli --output-dir docs/data --offline-seed
```

### 3. 本地預覽網頁查詢 GUI

```bash
python3 -m http.server 8000 --directory docs
```

接著於瀏覽器開啟 `http://localhost:8000` 即可使用關鍵字、臨床心理師積分（是／未知／否）、上課方式（線上／實體）、費用（免費／付費）、課程月份與資料來源平台進行即時篩選。

### 4. 執行自動化測試

```bash
.venv/bin/pytest -v
```

---

## Google Sheets 免金鑰自動同步指南

當本專案部署至 GitHub Pages 後，`docs/data/courses.csv` 會公開於：

```text
https://<您的GitHub帳號>.github.io/<Repo名稱>/data/courses.csv
```

在 Google Sheets 任一空白工作表的 `A1` 儲存格輸入以下公式：

```excel
=IMPORTDATA("https://<您的GitHub帳號>.github.io/<Repo名稱>/data/courses.csv")
```

也可直接點擊網頁右上角的 **「📊 Google Sheets 自動同步公式」** 按鈕一鍵複製完整公式。
