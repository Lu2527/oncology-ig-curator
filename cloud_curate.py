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
