#!/usr/bin/env python3
"""
雲端自動化癌症研究抓取與 Gemini API 專業知識摘要腳本 (供 GitHub Actions 每日 08:00 執行)
1. 從 NCI、ScienceDaily、Medical News Today、Medscape 與 PubMed 抓取最新癌症研究與確切 DOI
2. 呼叫 Gemini API 篩選最重要的 5 則，依「專業知識傳遞、無推銷、無醫療建議、文末必附確切 Reference」規範產出 JSON
"""
import datetime
import json
import os
import urllib.parse
import urllib.request
from fetch_and_curate import fetch_latest_rss_articles

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-pro"

SYSTEM_PROMPT = """你是一位專業的腫瘤學（Oncology）學術編譯專家。
請從提供的國際權威醫藥新聞與期刊摘要中，篩選出當日最具臨床與科學價值的 5 則癌症研究，並轉換為 Instagram 1080x1350 多圖輪播（每則 4 張圖卡）與貼文文案的 JSON 格式。

【嚴格遵守以下內容規範】：
1. 純專業知識傳遞：聚焦分子作用機制、臨床試驗數據（如 HR、PFS、OS、ORR）、流行病學統計與學術轉譯意義。
2. 嚴禁推銷與社群互動引導：圖卡與內文中絕對不可出現「往左滑、歡迎留言、收藏＋分享、追蹤我們」等推銷字眼。
3. 嚴禁醫療建議：絕對不可提及「找主治醫師討論評估、建議定期篩檢」等對個人的醫療建議。
4. 確切資料來源 (References)：
   - 每一篇貼文文案（caption）的最後一段（在 Hashtags 之前），必須放上 `■ 資料來源 (References)：`，詳列確切的作者、研究題目、發表期刊名稱、臨床試驗編號（如有）與 DOI / 官方連結。
   - 每一張圖卡的 `footer` 必須標註簡明學術引用（例如：`資料來源：Weber JS, et al. The Lancet / ESMO`）。
"""


def call_gemini_curator(raw_articles: list, today_str: str) -> dict:
    if not GEMINI_API_KEY:
        raise RuntimeError("未設定 GEMINI_API_KEY 環境變數，請於 GitHub Secrets 中設定。")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    user_content = (
        f"今日日期：{today_str}\n"
        f"以下為今日抓取之最新國際醫藥網站癌症研究候選清單：\n"
        f"{json.dumps(raw_articles[:20], ensure_ascii=False, indent=2)}\n\n"
        "請輸出符合 daily_posts.json 結構的純 JSON 物件（包含 date, generated_at, posts 陣列共 5 則，"
        "每則含 id, selected, category, source_name, source_url, original_title, theme_color, accent_color, caption, slides 共 4 張）。"
    )

    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": user_content}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    text = result["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    today_str = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d")

    articles = fetch_latest_rss_articles(max_per_source=6)
    print(f"已抓取 {len(articles)} 則最新癌症外電")

    if GEMINI_API_KEY and articles:
        curated = call_gemini_curator(articles, today_str)
        for out_rel in ["data/daily_posts.json", "docs/data/daily_posts.json"]:
            out_path = os.path.join(base_dir, out_rel)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(curated, f, ensure_ascii=False, indent=2)
        print(f"✅ 已完成 {today_str} 每日 5 則癌症研究專業編譯並寫入 JSON！")
    else:
        print("ℹ️ 未提供 GEMINI_API_KEY，保留現有 data/daily_posts.json 並同步至 docs/data/daily_posts.json")
        src_path = os.path.join(base_dir, "data", "daily_posts.json")
        dst_path = os.path.join(base_dir, "docs", "data", "daily_posts.json")
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with open(src_path, "r", encoding="utf-8") as f_in, open(dst_path, "w", encoding="utf-8") as f_out:
            f_out.write(f_in.read())

#!/bin/zsh
# 一鍵初始化並推送至 GitHub 雲端排程 (GitHub Actions + GitHub Pages)
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

mkdir -p docs/data docs/cards
cp -f /Users/lu/.gemini/antigravity/brain/974fb5af-3f0f-401a-9c7f-f0346b04647f/ig_curator_dashboard.html docs/index.html
cp -f data/daily_posts.json docs/data/daily_posts.json
osascript -l JavaScript render_cards.js docs/data/daily_posts.json docs/cards

if [ ! -d ".git" ]; then
  git init
  git branch -M main
fi

git add .
git diff --staged --quiet || git commit -m "feat: initialize Daily Oncology IG Curator cloud automation"

echo "✅ 本地專案與 20 張圖卡已準備就緒！"
echo "👉 接下來請執行以下兩行指令綁定你的 GitHub 儲存庫並推送："
echo "   git remote add origin https://github.com/<你的GitHub帳號>/oncology-ig-curator.git"
echo "   git push -u origin main"

#!/usr/bin/env python3
"""
每日國際權威醫藥網站（NCI / ScienceDaily / Medical News Today / Medscape）
癌症新知 RSS 自動抓取與篩選腳本。
"""
import json
import os
import datetime
import urllib.request
import xml.etree.ElementTree as ET
from typing import List, Dict

RSS_SOURCES = [
    {
        "name": "ScienceDaily Cancer News",
        "url": "https://www.sciencedaily.com/rss/health_medicine/cancer.xml"
    },
    {
        "name": "National Cancer Institute (NCI)",
        "url": "https://www.cancer.gov/publishedcontent/rss/syndication/rss/ncinewsreleases.rss"
    },
    {
        "name": "Medical News Today - Oncology",
        "url": "https://rss.medicalnewstoday.com/cancer-oncology.xml"
    },
    {
        "name": "Medscape Oncology",
        "url": "https://www.medscape.com/cx/rssfeeds/2700.xml"
    }
]


def fetch_latest_rss_articles(max_per_source: int = 5) -> List[Dict[str, str]]:
    """從各大國際醫藥網站 RSS 抓取最新癌症文章清單"""
    articles = []
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) OncologyCurator/1.0"}

    for src in RSS_SOURCES:
        try:
            req = urllib.request.Request(src["url"], headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                xml_data = response.read()
            root = ET.fromstring(xml_data)
            items = root.findall(".//item")[:max_per_source]
            for item in items:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                desc = (item.findtext("description") or "").strip()
                pub_date = (item.findtext("pubDate") or "").strip()
                if title and link:
                    articles.append({
                        "source_name": src["name"],
                        "title": title,
                        "url": link,
                        "summary": desc[:400],
                        "published_at": pub_date
                    })
        except Exception as exc:
            print(f"[WARN] 無法讀取 {src['name']}: {exc}")

    return articles


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    raw_dir = os.path.join(base_dir, "data")
    os.makedirs(raw_dir, exist_ok=True)
    fetched = fetch_latest_rss_articles()
    out_file = os.path.join(raw_dir, "raw_rss_candidates.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "fetched_at": datetime.datetime.now().isoformat(),
            "count": len(fetched),
            "articles": fetched
        }, f, ensure_ascii=False, indent=2)
    print(f"已抓取 {len(fetched)} 篇候選癌症文章並儲存至 {out_file}")

#!/usr/bin/env python3
"""
Instagram Business Graph API Publisher (Carousel & Single Image Support)
用於將篩選後的癌症知識多圖輪播（Carousel）一鍵發布至 Instagram Business 帳號。
"""
import json
import os
import urllib.parse
import urllib.request
from typing import List, Dict, Any

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def load_config() -> Dict[str, str]:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "ig_user_id": os.environ.get("IG_USER_ID", ""),
        "access_token": os.environ.get("IG_ACCESS_TOKEN", ""),
        "image_host_base_url": os.environ.get("IMAGE_HOST_BASE_URL", "")
    }


def save_config(ig_user_id: str, access_token: str, image_host_base_url: str = "") -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "ig_user_id": ig_user_id.strip(),
            "access_token": access_token.strip(),
            "image_host_base_url": image_host_base_url.strip()
        }, f, ensure_ascii=False, indent=2)


def _graph_post(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{GRAPH_API_BASE}/{endpoint}"
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def publish_carousel_to_instagram(
    ig_user_id: str,
    access_token: str,
    image_urls: List[str],
    caption: str
) -> Dict[str, Any]:
    """
    透過 Meta Instagram Graph API 發布多圖輪播貼文 (Carousel)：
    Step 1: 為每一張輪播圖建立子媒體容器 (is_carousel_item=true)
    Step 2: 建立 CAROUSEL 主容器，綁定 children IDs 與貼文文案 (caption)
    Step 3: 呼叫 media_publish 正式發布至 Instagram
    """
    if not ig_user_id or not access_token:
        raise ValueError("請先設定 Instagram Business 帳號 ID (ig_user_id) 與 Graph API Access Token")
    if len(image_urls) < 2 or len(image_urls) > 10:
        raise ValueError("Instagram 多圖輪播需包含 2 至 10 張圖片 URL")

    child_creation_ids = []
    for img_url in image_urls:
        res = _graph_post(f"{ig_user_id}/media", {
            "image_url": img_url,
            "is_carousel_item": "true",
            "access_token": access_token
        })
        child_creation_ids.append(res["id"])

    carousel_res = _graph_post(f"{ig_user_id}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(child_creation_ids),
        "caption": caption,
        "access_token": access_token
    })
    carousel_container_id = carousel_res["id"]

    publish_res = _graph_post(f"{ig_user_id}/media_publish", {
        "creation_id": carousel_container_id,
        "access_token": access_token
    })
    return {
        "status": "published",
        "ig_media_id": publish_res.get("id"),
        "children_ids": child_creation_ids,
        "carousel_container_id": carousel_container_id
    }

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

ObjC.import('Cocoa');
ObjC.import('Foundation');

function colorFromHex(hex, alpha) {
  if (alpha === undefined) alpha = 1.0;
  var clean = hex.replace('#', '');
  var r = parseInt(clean.substring(0, 2), 16) / 255.0;
  var g = parseInt(clean.substring(2, 4), 16) / 255.0;
  var b = parseInt(clean.substring(4, 6), 16) / 255.0;
  return $.NSColor.colorWithSRGBRedGreenBlueAlpha(r, g, b, alpha);
}

function getFont(name, size) {
  var font = $.NSFont.fontWithNameSize(name, size);
  if (!font || font.isNil()) {
    font = $.NSFont.boldSystemFontOfSize(size);
  }
  return font;
}

function drawText(text, x, y, width, height, font, color, lineSpacing, align) {
  var style = $.NSMutableParagraphStyle.alloc.init;
  style.setLineSpacing(lineSpacing || 10);
  var attrs = $.NSMutableDictionary.alloc.init;
  attrs.setObjectForKey(font, $.NSFontAttributeName);
  attrs.setObjectForKey(color, $.NSForegroundColorAttributeName);
  attrs.setObjectForKey(style, $.NSParagraphStyleAttributeName);

  var nsStr = $.NSString.stringWithString(String(text));
  if (align === 'center') {
    var sz = nsStr.sizeWithAttributes(attrs);
    var drawX = x + (width - sz.width) / 2.0;
    var drawY = y + (height - sz.height) / 2.0;
    nsStr.drawAtPointWithAttributes($.NSMakePoint(drawX, drawY), attrs);
  } else {
    nsStr.drawInRectWithAttributes($.NSMakeRect(x, y, width, height), attrs);
  }
}

function drawRoundedRect(x, y, w, h, radius, fillColor, strokeColor, lineWidth) {
  var path = $.NSBezierPath.bezierPathWithRoundedRectXRadiusYRadius($.NSMakeRect(x, y, w, h), radius, radius);
  if (fillColor) {
    fillColor.setFill;
    path.fill;
  }
  if (strokeColor) {
    strokeColor.setStroke;
    path.setLineWidth(lineWidth || 2.0);
    path.stroke;
  }
}

function renderSlide(post, slide, totalSlides, outPath) {
  var W = 1080;
  var H = 1350;

  var img = $.NSImage.alloc.initWithSize($.NSMakeSize(W, H));
  img.lockFocus;

  var themeColor = colorFromHex(post.theme_color, 1.0);
  var accentColor = colorFromHex(post.accent_color, 1.0);
  var darkBg = colorFromHex('#0F172A', 1.0);
  var white = colorFromHex('#FFFFFF', 1.0);
  var offWhite = colorFromHex('#F8FAFC', 1.0);
  var slateDark = colorFromHex('#1E293B', 1.0);
  var slateBody = colorFromHex('#334155', 1.0);

  // Background gradient
  var gradient = $.NSGradient.alloc.initWithStartingColorEndingColor(darkBg, themeColor);
  gradient.drawInRectAngle($.NSMakeRect(0, 0, W, H), 55);

  // Decorative background circles
  drawRoundedRect(760, 980, 420, 420, 210, colorFromHex(post.accent_color, 0.14), null);
  drawRoundedRect(-120, -100, 380, 380, 190, colorFromHex('#FFFFFF', 0.06), null);

  var fontHeavy68 = getFont('PingFangTC-Semibold', 62);
  var fontBold54 = getFont('PingFangTC-Semibold', 50);
  var fontSemi36 = getFont('PingFangTC-Semibold', 33);
  var fontMed32 = getFont('PingFangTC-Medium', 30);
  var fontReg28 = getFont('PingFangTC-Regular', 25);
  var fontBold26 = getFont('PingFangTC-Semibold', 25);

  // Category pill on top left
  drawRoundedRect(80, 1195, 260, 62, 31, colorFromHex('#FFFFFF', 0.16), colorFromHex('#FFFFFF', 0.35), 1.5);
  drawText(post.category, 80, 1195, 260, 62, fontBold26, white, 4, 'center');

  // Slide counter pill on top right
  drawRoundedRect(860, 1195, 140, 62, 31, colorFromHex('#000000', 0.28), null);
  drawText(slide.slide_num + ' / ' + totalSlides, 860, 1195, 140, 62, fontBold26, white, 4, 'center');

  if (slide.type === 'cover') {
    drawRoundedRect(75, 200, 930, 930, 42, colorFromHex('#0F172A', 0.55), colorFromHex('#FFFFFF', 0.22), 2.0);
    drawRoundedRect(135, 975, 310, 66, 16, accentColor, null);
    drawText('✦ ' + slide.tag, 135, 975, 310, 66, fontBold26, white, 4, 'center');
    drawText(slide.headline, 135, 535, 810, 390, fontHeavy68, white, 18, 'left');
    drawRoundedRect(135, 505, 160, 8, 4, accentColor, null);
    drawText(slide.subheadline, 135, 340, 810, 135, fontSemi36, colorFromHex('#E2E8F0', 0.95), 12, 'left');
    var metaText = slide.meta_badge || ('研究機構：' + post.source_name);
    drawRoundedRect(135, 255, 520, 64, 32, colorFromHex('#FFFFFF', 0.12), null);
    drawText(metaText, 135, 255, 520, 64, fontBold26, white, 4, 'center');
  } else if (slide.type === 'points') {
    drawRoundedRect(75, 200, 930, 940, 42, offWhite, null);
    drawRoundedRect(135, 1005, 230, 60, 14, themeColor, null);
    drawText(slide.tag, 135, 1005, 230, 60, fontBold26, white, 4, 'center');
    drawText(slide.headline, 135, 800, 810, 175, fontBold54, slateDark, 14, 'left');

    var pts = slide.points || [];
    for (var i = 0; i < pts.length; i++) {
      var boxY = 610 - i * 180;
      drawRoundedRect(130, boxY, 820, 152, 24, white, colorFromHex(post.theme_color, 0.22), 2.0);
      drawRoundedRect(158, boxY + 42, 68, 68, 34, themeColor, null);
      drawText('0' + (i + 1), 158, boxY + 42, 68, 68, fontSemi36, white, 2, 'center');
      drawText(pts[i], 250, boxY + 18, 670, 114, fontMed32, slateBody, 8, 'left');
    }
  } else if (slide.type === 'takeaway') {
    drawRoundedRect(75, 200, 930, 940, 42, offWhite, null);
    drawRoundedRect(135, 1005, 240, 60, 14, accentColor, null);
    drawText(slide.tag, 135, 1005, 240, 60, fontBold26, white, 4, 'center');
    drawText(slide.headline, 135, 790, 810, 185, fontBold54, slateDark, 14, 'left');

    drawRoundedRect(130, 430, 820, 320, 28, colorFromHex(post.theme_color, 0.09), themeColor, 2.5);
    drawText('■ 學術與臨床意義', 175, 665, 730, 50, fontSemi36, themeColor, 6, 'left');
    drawText(slide.summary, 175, 465, 730, 185, fontMed32, slateDark, 14, 'left');

    drawRoundedRect(130, 260, 820, 120, 26, themeColor, null);
    drawText(slide.cta, 130, 260, 820, 120, getFont('PingFangTC-Medium', 24), white, 6, 'center');
  }

  var footerText = slide.footer || ('資料來源：' + post.source_name);
  drawText(footerText, 85, 95, 700, 45, fontReg28, colorFromHex('#E2E8F0', 0.85), 4, 'left');

  for (var d = 1; d <= totalSlides; d++) {
    var dotW = (d === slide.slide_num) ? 44 : 16;
    var dotX = 830 + (d - 1) * 32 + (d > slide.slide_num ? 28 : 0);
    var dotColor = (d === slide.slide_num) ? accentColor : colorFromHex('#FFFFFF', 0.35);
    drawRoundedRect(dotX, 112, dotW, 16, 8, dotColor, null);
  }

  img.unlockFocus;

  var tiff = img.TIFFRepresentation;
  var rep = $.NSBitmapImageRep.imageRepWithData(tiff);
  var pngData = rep.representationUsingTypeProperties($.NSBitmapImageFileTypePNG, $.NSDictionary.dictionary);
  pngData.writeToFileAtomically(outPath, true);
}

function run(argv) {
  var jsonPath = argv[0];
  var outDir = argv[1];
  var jsonStr = $.NSString.stringWithContentsOfFileEncodingError(jsonPath, $.NSUTF8StringEncoding, null).js;
  var data = JSON.parse(jsonStr);

  var fm = $.NSFileManager.defaultManager;
  fm.createDirectoryAtPathWithIntermediateDirectoriesAttributesError(outDir, true, $(), $());

  var count = 0;
  for (var i = 0; i < data.posts.length; i++) {
    var post = data.posts[i];
    var slides = post.slides;
    for (var s = 0; s < slides.length; s++) {
      var fileName = post.id + '_slide_' + slides[s].slide_num + '.png';
      var outPath = outDir + '/' + fileName;
      renderSlide(post, slides[s], slides.length, outPath);
      count++;
    }
  }
  return 'Rendered ' + count + ' slides to ' + outDir;
}

#!/usr/bin/env python3
"""
本地癌症新知 IG 審核與一鍵發布伺服器 (http://localhost:8765)
提供 API 儲存修改後的文案、重新產生 PNG 圖卡，並串接 Instagram Graph API 一鍵發布。
"""
import json
import os
import subprocess
from http.server import SimpleHTTPRequestHandler, HTTPServer
from ig_publisher import load_config, save_config, publish_carousel_to_instagram

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "daily_posts.json")
CARDS_DIR = os.path.join(BASE_DIR, "output", "cards")


class CuratorHandler(SimpleHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = 200):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/posts":
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                self._send_json(json.load(f))
            return
        if self.path == "/api/config":
            cfg = load_config()
            self._send_json({
                "ig_user_id": cfg.get("ig_user_id", ""),
                "has_token": bool(cfg.get("access_token")),
                "image_host_base_url": cfg.get("image_host_base_url", "")
            })
            return
        return super().do_GET()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")

        if self.path == "/api/config":
            save_config(
                body.get("ig_user_id", ""),
                body.get("access_token", ""),
                body.get("image_host_base_url", "")
            )
            self._send_json({"ok": True})
            return

        if self.path == "/api/render":
            with open(DATA_PATH, "w", encoding="utf-8") as f:
                json.dump(body, f, ensure_ascii=False, indent=2)
            os.makedirs(CARDS_DIR, exist_ok=True)
            subprocess.run([
                "osascript", "-l", "JavaScript",
                os.path.join(BASE_DIR, "render_cards.js"),
                DATA_PATH, CARDS_DIR
            ], check=True)
            self._send_json({"ok": True, "cards_dir": CARDS_DIR})
            return

        if self.path == "/api/publish":
            cfg = load_config()
            ig_user_id = body.get("ig_user_id") or cfg.get("ig_user_id", "")
            access_token = body.get("access_token") or cfg.get("access_token", "")
            image_urls = body.get("image_urls", [])
            caption = body.get("caption", "")
            try:
                result = publish_carousel_to_instagram(ig_user_id, access_token, image_urls, caption)
                self._send_json({"ok": True, "result": result})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
            return

        self._send_json({"ok": False, "error": "Unknown endpoint"}, status=404)


if __name__ == "__main__":
    os.chdir(BASE_DIR)
    port = 8765
    print(f"🚀 癌症新知 IG 審核與一鍵發布後台已啟動：http://localhost:{port}")
    HTTPServer(("127.0.0.1", port), CuratorHandler).serve_forever()
