# 🧬 Oncology IG Curator 系統架構與維運留存手冊

> **最後更新日期**：2026-11-01  
> **GitHub 儲存庫**：`https://github.com/Lu2527/oncology-ig-curator`  
> **GitHub Pages 線上看版**：`https://lu2527.github.io/oncology-ig-curator/`  
> **本機專案路徑**：`/Users/lu/.gemini/antigravity/scratch/oncology-ig-curator`

---

## 1. 系統核心功能與資料來源

本系統於每日台灣時間 **早上 08:00**（UTC `00:00`）透過 GitHub Actions 自動執行，亦可隨時手動觸發（`Run workflow`），完成以下工作：

1. **多源權威癌症研究抓取 (`fetch_and_curate.py`)**：
   - **六大國際腫瘤醫學會（透過 NCBI PubMed E-Utilities API 檢索最新發表與會議摘要）**：
     - **ASCO**（美國臨床腫瘤學會 / *Journal of Clinical Oncology*）
     - **ESMO**（歐洲腫瘤內科學會 / *Annals of Oncology* & *ESMO Open*）
     - **AACR**（美國癌症研究協會 / *Cancer Discovery* & *Clinical Cancer Research*）
     - **WCLC**（世界肺癌大會 / IASLC *Journal of Thoracic Oncology*）
     - **SITC**（癌症免疫治療學會 / *Journal for ImmunoTherapy of Cancer*）
     - **SABCS**（聖安東尼奧乳癌研討會）
   - **權威醫藥新聞 RSS**：
     - National Cancer Institute (NCI)
     - ScienceDaily Cancer News
     - Medscape Oncology
     - Oncology Congress News
   - **Crossref DOI 官方書目驗證**：自動自原文頁面擷取 DOI 並向 Crossref API 驗證作者、標題、期刊名與發表年份。
   - **去重機制 (`data/seen_history.json`)**：自動記錄最近發布過的 60 篇論文標題，優先挑選未曾發布過的全新研究，確保同日多次觸發或跨日執行皆不重複。

2. **AI 雙引擎專業醫學編譯 (`cloud_curate.py`)**：
   - 精選前 10 篇具備官方會議或確切期刊驗證出處之候選研究，交由頂尖推理模型編譯為 **5 篇完整貼文**。
   - 每篇包含 **4 張 `1080×1350` 輪播圖卡結構**（第 1 張封面 `cover`、第 2 張分子機制 `points_mechanism`、第 3 張關鍵數據 `points_data`、第 4 張學術意義與展望 `takeaway`）與附帶完整 `■ 資料來源 (References)：` 之 IG 貼文內文。
   - **嚴格學術把關**：禁止任何社群推銷用語（如「往左滑、歡迎留言、收藏＋分享」）與個人化醫療諮詢建議（如「與主治醫師討論評估」）。

3. **高解析度圖卡渲染與自動部署 (`render_cards.js` & `docs/index.html`)**：
   - 在 macOS Runner 上以原生 `PingFang TC` 繁體中文字型渲染 20 張 `1080×1350` PNG 圖卡（含第 4 張底部結論框智慧自動換行與字級縮放防溢出）。
   - 自動 Commit 並推送到 GitHub Pages，前端使用 `?t=Date.now()` 強制穿透 CDN 快取。

---

## 2. AI 模型優先順序與 GitHub Secrets 設定

系統支援在 GitHub Secrets **同時存放兩家廠商的 API Key**（互為備援），也支援只放其中一把：

### 🔑 GitHub Secrets 設定路徑
前往 `https://github.com/Lu2527/oncology-ig-curator/settings/secrets/actions`，點擊 **`New repository secret`**：

| Secret 名稱 | 金鑰開頭特徵 | 申請與加值後台 | 系統呼叫之模型優先順序 |
| :--- | :--- | :--- | :--- |
| **`ANTHROPIC_API_KEY`** | `sk-ant-...` | [Anthropic Console](https://console.anthropic.com/settings/billing) | 1. **`claude-sonnet-5-5`** (Claude Sonnet 5.5)<br>2. `claude-sonnet-4-5-20250929`<br>3. `claude-3-7-sonnet-latest` |
| **`GEMINI_API_KEY`** | `AIzaSy...` | [Google AI Studio Billing](https://aistudio.google.com/billing) | 1. **`gemini-4-argon`** (Gemini 4 Argon 旗艦推理模型)<br>2. `gemini-3.8-flash`<br>3. `gemini-2.5-pro`<br>4. `gemini-2.5-flash` |

- **雙引擎自動備援**：若兩把 Key 都設定，系統會**第一優先使用 `claude-sonnet-5-5`**；萬一 Anthropic 額度用完或瞬斷，會**自動無縫切換至 Google 的 `gemini-4-argon`** 完成編譯。
- **防呆自動識別**：就算不小心把 `sk-ant-...` 貼進 `GEMINI_API_KEY` 欄位，`cloud_curate.py` 也會自動識別前綴並改用 Claude 引擎。

---

## 3. 本機關鍵檔案清單與 Finder 快速開啟方式

### 📁 本機檔案對照表

| 檔案名稱 | 本機完整路徑 | GitHub 對應位置 | 用途說明 |
| :--- | :--- | :--- | :--- |
| `cloud_curate.py` | `/Users/lu/.gemini/antigravity/scratch/oncology-ig-curator/cloud_curate.py` | 根目錄 `cloud_curate.py` | 雙 AI 引擎（Claude Sonnet 5.5 + Gemini 4 Argon）編譯與結構驗證主程式 |
| `fetch_and_curate.py` | `/Users/lu/.gemini/antigravity/scratch/oncology-ig-curator/fetch_and_curate.py` | 根目錄 `fetch_and_curate.py` | 六大醫學會 PubMed 檢索（含防 429 限流延遲）、RSS 抓取與 Crossref DOI 驗證 |
| `render_cards.js` | `/Users/lu/.gemini/antigravity/scratch/oncology-ig-curator/render_cards.js` | 根目錄 `render_cards.js` | macOS Cocoa 原生渲染 20 張 `1080×1350` PNG 輪播圖卡 |
| `docs/index.html` | `/Users/lu/.gemini/antigravity/scratch/oncology-ig-curator/docs/index.html` | `docs/index.html` | GitHub Pages 雙模式網頁（Today Oncology IG Posts 總覽 ＋ IG Curator 編輯器） |
| `.github/workflows/main.yml` | `/Users/lu/.gemini/antigravity/scratch/oncology-ig-curator/.github/workflows/main.yml` | `.github/workflows/main.yml` | GitHub Actions 每日排程與雙 API Key 環境變數設定檔 |

### 🖥️ Mac Finder 快速開啟與永久顯示隱藏檔
- **快速前往專案資料夾**：在 Finder 按 **`Command + Shift + G`**，貼上：
  ```text
  ~/.gemini/antigravity/scratch/oncology-ig-curator
  ```
- **切換顯示隱藏檔案快速鍵**：在 Finder 視窗按 **`Command + Shift + .`**（句點）。
- **終端機永久顯示隱藏檔指令**：
  ```bash
  defaults write com.apple.finder AppleShowAllFiles -bool true && killall Finder
  ```

---

## 4. 常見錯誤碼診斷速查表

若 GitHub Actions 出現紅燈（Failed），點開 **`curate-and-render` → Step 4 (`Fetch Oncology News & Curate 5 Posts`)** 查看日誌：

| 錯誤訊息 / 狀態碼 | 原因說明 | 解決方式 |
| :--- | :--- | :--- |
| `HTTP 402` (`prepayment credits are depleted` / `credit balance is too low`) | Google AI Studio 或 Anthropic 的預付額度已歸零（`NT$0.00`） | 前往 [Google AI Studio Billing](https://aistudio.google.com/billing) 點擊 **Buy credits** 加值，或至 Anthropic Billing 儲值 |
| `HTTP 404` (`model is not found`) | 舊版模型下架或帳號未開通該預覽模型 | 系統會自動跳過並改用備援模型（如 `gemini-4-argon` → `gemini-3.8-flash`） |
| `HTTP 429` (`Too Many Requests`) | API 瞬間請求頻率過高 | 程式已內建自動退避重試（Exponential Backoff）與多模型切換 |
| `HTTP 401` / `HTTP 403` | API Key 複製不完整、已撤銷或貼錯欄位 | 重新複製 API Key 並更新至 GitHub Secrets |

---

## 5. 📰 每週腫瘤臨床深度週報（模式 B）

**流程**：每天在看板挑 1–3 篇發 IG → 按 **「☆ 加入本週週報」** → 每週日 21:00（台灣時間）自動針對這些貼文產出深度臨床分析。

| 元件 | 說明 |
| :--- | :--- |
| `archive_daily.py` | 每日排程歸檔當天 5 篇至 `docs/data/archive/YYYY-MM-DD.json`；看板右上「📅」可切換瀏覽過去日期並補挑選 |
| `docs/data/weekly_picks.json` | 網頁按 ⭐ 時透過 GitHub API 寫入（存當下完整貼文內容，含編輯器微調）；`issue` 欄位為 `null` 表示待收錄 |
| `curate_weekly_newsletter.py` | 以 DOI 向 PubMed 取回原始摘要作為事實依據 → AI 撰寫：試驗設計與族群／療效與安全性／與標準治療及 NCCN·ESMO 比較／台灣 TFDA·健保意涵／進行中試驗 → 主編導讀 |
| `.github/workflows/weekly_newsletter.yml` | 每週日 UTC 13:00 執行，亦可手動 `Run workflow` |
| 產出 | `docs/newsletter/YYYY-MM-DD.html`（可貼入 Gmail/Outlook）、`.md`（可貼入 Substack/Beehiiv）、歷期目錄 `https://lu2527.github.io/oncology-ig-curator/newsletter/` |

**一次性設定（⭐ 按鈕寫入權限）**：至 `https://github.com/settings/personal-access-tokens/new` 建立 Fine-grained token → Repository access 只選 `oncology-ig-curator` → Permissions：**Contents: Read and write** → 在看板點「🔑 週報 GitHub 設定」貼上（只存在該裝置瀏覽器）。手機與電腦需各設定一次。

**本機測試**：`python3 curate_weekly_newsletter.py --dry-run` 只列出待收錄貼文、不呼叫 AI。

