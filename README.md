# 🎗️ 每日癌症研究 IG 多圖輪播雲端自動化系統 (Oncology IG Curator)

每天台灣時間早上 **08:00** 在雲端（GitHub Actions）自動從國際權威醫藥網站與期刊（NCI、ESMO、ScienceDaily、Nature Medicine、The Lancet 等）篩選 5 則重要癌症研究，自動渲染 **20 張 1080×1350 PNG 繁體中文知識圖卡**，並部署至 **GitHub Pages** 審核與一鍵發布工作台。

## ✨ 雲端版（方案 B）三大優勢
1. **電腦完全關機也能跑**：由 GitHub 官方雲端 `macos-latest` 伺服器每天早上 08:00 自動執行。
2. **手機 / 平板 / 電腦打開網址就能審核**：每天 08:02 直接打開你的專屬 GitHub Pages 網址，即可瀏覽當日 5 則研究、即時微調圖卡文字或下載 PNG。
3. **免費內建 HTTPS 圖床直連 IG Graph API**：Meta 的 Instagram Graph API 規定發布多圖輪播時，圖片必須放在公開的 `https://` 網址。GitHub Pages 會自動託管每日產出的 20 張 PNG 圖卡，讓你在網頁上點擊「🚀 一鍵發布」就能直接透過瀏覽器呼叫 Meta Graph API 完成發文！

---

## 🚀 3 步驟啟用雲端全自動排程

### 步驟 1：將專案上傳至 GitHub
1. 前往 [GitHub 建立一個新的 Repository](https://github.com/new)，名稱設為 `oncology-ig-curator`（建議設為 **Public** 以免費使用 GitHub Pages 與無限 GitHub Actions 額度，且讓 IG Graph API 能讀取圖卡）。
2. 在終端機執行本資料夾內的一鍵打包腳本並推送：
   ```bash
   cd /Users/lu/.gemini/antigravity/scratch/oncology-ig-curator
   sh deploy_cloud.sh
   git remote add origin https://github.com/<你的GitHub帳號>/oncology-ig-curator.git
   git push -u origin main
   ```

### 步驟 2：在 GitHub 設定 Gemini API Key
1. 進入你的 GitHub 儲存庫頁面 ➔ 點擊上方 **Settings** ➔ 左側選單 **Secrets and variables** ➔ **Actions**。
2. 點擊 **New repository secret**：
   - **Name**：`GEMINI_API_KEY`
   - **Secret**：貼上你的 Google AI Studio Gemini API Key（可於 [aistudio.google.com](https://aistudio.google.com/) 免費取得）。

### 步驟 3：開啟 GitHub Pages 網頁後台
1. 在 GitHub 儲存庫的 **Settings** ➔ 左側選單 **Pages**。
2. 在 **Build and deployment** 下方：
   - **Source** 選擇 `Deploy from a branch`
   - **Branch** 選擇 `main`，資料夾選擇 `/docs`，點擊 **Save**。
3. 等待約 1 分鐘後，你的專屬審核與一鍵發布網址就會生效：
   `https://<你的GitHub帳號>.github.io/oncology-ig-curator/`
4. 你也可以隨時到 GitHub 上方的 **Actions** 頁籤，點擊 `Daily Oncology IG Curator (08:00 AM Taiwan Time)` ➔ **Run workflow** 手動立即觸發測試！
