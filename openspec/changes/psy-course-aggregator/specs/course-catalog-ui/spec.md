# Spec Delta: course-catalog-ui

## Purpose

定義供同事與學生瀏覽及篩選臨床心理師繼續教育課程之靜態網頁 GUI、UTF-8 BOM CSV 匯出、Google Sheets 免金鑰同步以及每日自動更新排程之行為規範。

## ADDED Requirements

### Requirement: 響應式課程查詢與多維度篩選網頁 GUI
系統 SHALL 提供託管於 GitHub Pages 之公開網頁介面，讓使用者免安裝環境即可透過瀏覽器檢視、搜尋與篩選彙整後的 12 欄位課程表格。

#### Scenario: 依臨床心理師積分狀態與上課條件篩選課程
- **WHEN** 使用者在網頁 GUI 選擇篩選條件（包括：`是否有臨床心理師積分` 為「是／未知／否／全部」、`上課地點／方式` 為「線上／實體」、`費用` 為「免費／全部」、特定課程月份、`資料來源平台` 或輸入關鍵字）
- **THEN** 網頁 MUST 即時過濾課程列表，僅顯示符合所有啟用篩選條件之課程，並顯示目前符合筆數與最後資料更新時間

#### Scenario: 檢視積分判斷依據段落與點擊報名連結
- **WHEN** 使用者在課程列表中檢視任一筆課程
- **THEN** 介面 MUST 清楚呈現 `是否有臨床心理師積分` 狀態標籤、顯示或可展開檢視完整 `積分判斷依據段落` 原文，並將 `報名連結` 呈現為可點擊開啟新分頁之超連結

### Requirement: 標準 12 欄位 CSV 匯出與 Google Sheets 同步支援
系統 MUST 產出包含完整 12 個指定欄位的 CSV 檔案與 JSON 資料檔，並支援直接匯入 Excel 與同步至 Google Sheets。

#### Scenario: 下載 CSV 檔案於 Excel 正確顯示中文
- **WHEN** 爬蟲完成更新或使用者於網頁 GUI 點擊「下載 CSV」按鈕
- **THEN** 系統提供之 `courses.csv` MUST 採用 UTF-8 with BOM 編碼，且欄位順序嚴格依序為：`課程名稱`、`主辦單位`、`課程日期`、`上課時間`、`費用`、`上課地點／方式`、`報名連結`、`是否有臨床心理師積分`、`積分判斷依據段落`、`資料來源平台`、`建立時間`、`報名期間`

#### Scenario: 透過公開 CSV 網址與 Google Sheets 自動同步
- **WHEN** 使用者於網頁 GUI 點擊「Google Sheets 同步說明／複製公式」並將 `=IMPORTDATA("<GitHub Pages CSV URL>")` 貼入 Google Sheets 儲存格
- **THEN** Google Sheets MUST 能直接讀取公開之 `data/courses.csv` 並自動展開為完整 12 欄位課程表格，無需設定付費 API Key

### Requirement: 定時自動抓取與手動觸發更新排程
系統 SHALL 透過自動化排程定期執行爬蟲並更新公開網站與 CSV 資料。

#### Scenario: 每日定時排程或手動觸發更新
- **WHEN** 每日排程時間到達或管理員手動觸發更新工作流（`workflow_dispatch`）
- **THEN** 自動化工作流 MUST 執行爬蟲擷取最新課程、更新 `data/courses.json` 與 `data/courses.csv`，並重新部署靜態查詢網站
