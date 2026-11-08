# Proposal

## Why

臨床心理師與相關系所學生在尋找繼續教育積分課程時，必須逐一造訪十多個公會與學會網站，且各網站公告格式不一、常混雜諮商心理師積分或徵才訊息，難以快速確認「是否有臨床心理師積分」與報名資訊。建立一套免 API 費用的自動彙整爬蟲與靜態查詢網站（同時產出 CSV 供 Google Sheets 同步），能讓同事與學生在單一介面篩選、查驗積分依據並直接報名。

## What Changes

- 新增 **A 類學會官網自動爬蟲與純規則抽取引擎**：
  - 針對 15 個實測可連線之台灣臨床／心理治療相關公學會官網（含修正後之真實網域：`atcp.org.tw`、`taclip.org.tw`、`atpt.org.tw`、`tcpu.org.tw`、`rmdaroc`、`tap.org.tw`、`twcpa.org.tw/recentcourses`、`tsos.org.tw`、`tpos-society.org`、`iaptc.asia.edu.tw`、`psychoanalysis.org.tw`、`tasctaiwan.tw`、`acft.org.tw`、`asia-eft.com`、`ecata.org.tw`、`mindfulness.org.tw`、`sop.org.tw`）抓取近期課程列表與內頁。
  - 同步抓取台灣臨床心理學會「審核通過課程」官方總表（`https://taclip.org.tw/checked-list/`）作為臨床心理師積分白名單。
  - 以純程式規則（HTML DOM + 台灣公文／簡章 Regex 規則庫，不依賴付費 LLM API Key）抽取 12 個指定欄位，並執行跨來源去重與民國年日期正規化。
- 新增 **課程資料匯出與 Google Sheets 同步機制**：
  - 產出結構化 `data/courses.json` 與 `data/courses.csv`（UTF-8 with BOM，支援 Excel 直接開啟與 Google Sheets `=IMPORTDATA()` 自動同步）。
- 新增 **GitHub Pages 課程查詢網站（GUI）与 GitHub Actions 自動排程**：
  - 提供給同事與學生使用的響應式網頁介面，支援依「是否有臨床心理師積分（是／否／未知）」、「上課方式（線上／實體）」、「免費／付費」、「月份」、「來源平台」及關鍵字即時篩選，並可展開檢視「積分判斷依據段落」原文、一鍵下載 CSV 或複製 Google Sheets 同步公式。
  - 設定 GitHub Actions 每日定時執行爬蟲並自動更新網站與 CSV 資料檔。

## Capabilities

### New Capabilities
- `course-scraping`: 自動抓取 A 類心理公學會課程公告、對照 `taclip` 審核通過名單，並以純規則（DOM + Regex）抽取 12 個標準欄位與去重合併。
- `course-catalog-ui`: 供同事與學生瀏覽、篩選繼續教育課程的靜態網頁 GUI，以及 CSV 匯出、Google Sheets 同步與 GitHub Actions 定時更新工作流。

### Modified Capabilities
- None

## Impact

- **新增程式碼與目錄**：
  - `scraper/`：Python 爬蟲、站點解析器、12 欄位規則抽取器、去重與 CSV/JSON 輸出模組。
  - `docs/`（或 `web/` 發佈至 GitHub Pages）：前端靜態查詢 GUI（HTML/CSS/JS）與最新產出的 `data/courses.json`、`data/courses.csv`。
  - `.github/workflows/update-courses.yml`：每日定時抓取與手動觸發（`workflow_dispatch`）之自動化排程。
- **外部依賴**：僅使用免費開源 Python 套件（如 `httpx`、`beautifulsoup4`、`lxml`），無需任何 LLM API Key 或付費雲端主機。
