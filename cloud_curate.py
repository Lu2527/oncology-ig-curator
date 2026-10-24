#!/usr/bin/env python3
"""
雲端自動化癌症研究抓取與 Gemini API 專業知識摘要腳本 (供 GitHub Actions 每日 08:00 執行)
1. 從 NCI、ScienceDaily、Medical News Today、Medscape 抓取最新癌症研究
2. 進入每篇原文頁擷取期刊 DOI，並以 Crossref 官方資料庫驗證作者 / 題目 / 期刊（不交給 AI 產生）
3. 呼叫 Gemini API 篩選最重要的 5 則，依「專業知識傳遞、無推銷、無醫療建議」規範撰寫內文與圖卡
4. 由程式（而非 AI）在每篇文末組裝確切的「■ 資料來源 (References)」與圖卡頁尾出處
5. 輸出不符格式時保留前一天資料，避免網站壞掉
"""
import datetime
import json
import os
import re
import sys
import urllib.request
from fetch_and_curate import fetch_latest_rss_articles, enrich_article_reference

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")

BANNED_PHRASES = [
    "往左滑", "左滑", "留言", "收藏", "分享", "追蹤", "按讚", "小盒子", "點擊連結",
    "主治醫師", "諮詢醫師", "請教醫師", "與醫師討論", "建議定期", "定期篩檢", "就醫", "尋求醫療",
]

PALETTES = [
    ("#0F766E", "#14B8A6"), ("#1D4ED8", "#60A5FA"), ("#7C3AED", "#A78BFA"),
    ("#B45309", "#F59E0B"), ("#BE123C", "#FB7185"),
]

SYSTEM_PROMPT = """你是一位專業的腫瘤學（Oncology）學術編譯專家，以繁體中文（台灣用語）撰寫。
請從提供的候選清單中，篩選出最具臨床與科學價值的 5 則癌症研究（優先選擇 has_verified_reference 為 true 者），
轉換為 Instagram 1080x1350 多圖輪播（每則 4 張圖卡）的內容。

【嚴格內容規範】
1. 純專業知識傳遞：聚焦分子機制、臨床試驗數據（HR、PFS、OS、ORR 等）、流行病學與學術轉譯意義。
2. 只能使用候選資料（title、summary、page_excerpt）中明確出現的事實與數字，絕對不可自行補充或推測任何數據、作者、期刊、試驗編號。
3. 嚴禁推銷與社群互動引導：不可出現「往左滑、留言、收藏、分享、追蹤」等字眼。
4. 嚴禁醫療建議：不可出現「找主治醫師、建議定期篩檢、就醫」等對個人的建議。
5. 不要撰寫任何參考文獻、DOI 或資料來源段落（系統會自動附上經過驗證的確切出處）。

【輸出格式】只輸出一個 JSON 物件，結構必須完全如下：
{
  "posts": [
    {
      "source_index": 0,
      "category": "4~8 字繁中分類，例如：膠質母細胞瘤",
      "body": "貼文內文（繁中，含【標題】、研究背景、■ 核心機制 / ■ 關鍵數據 等段落，300~600 字，不含參考文獻與 hashtag）",
      "hashtags": ["#腫瘤學", "#癌症研究"],
      "slides": [
        {"type": "cover", "tag": "研究類型（例如：基礎研究 / 臨床三期）", "headline": "封面主標題，可用 \\n 換行，每行不超過 12 字，最多 3 行", "subheadline": "副標題 40 字內", "meta_badge": "研究設計或機構，20 字內"},
        {"type": "points", "tag": "研究背景", "headline": "本頁標題，可用 \\n 換行", "points": ["要點一 45 字內", "要點二 45 字內", "要點三 45 字內"]},
        {"type": "points", "tag": "關鍵發現", "headline": "本頁標題，可用 \\n 換行", "points": ["要點一 45 字內", "要點二 45 字內", "要點三 45 字內"]},
        {"type": "takeaway", "tag": "學術意義", "headline": "本頁標題，可用 \\n 換行", "summary": "學術與臨床意義 90 字內", "cta": "後續研究觀察重點 40 字內（不可為醫療建議）"}
      ]
    }
  ]
}
source_index 為候選清單中的 index，5 則必須來自不同的 source_index。
"""


def call_gemini(candidates: list, today_str: str) -> dict:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    user_content = (
        f"今日日期：{today_str}\n候選清單：\n"
        f"{json.dumps(candidates, ensure_ascii=False, indent=2)}"
    )
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": user_content}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    text = result["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def scrub(text: str) -> str:
    """移除含禁用字眼的句子（推銷互動語 / 醫療建議）"""
    if not text:
        return ""
    lines = []
    for line in str(text).split("\n"):
        sentences = re.split(r"(?<=[。！？!?])", line)
        kept = [s for s in sentences if not any(b in s for b in BANNED_PHRASES)]
        lines.append("".join(kept))
    return "\n".join(lines).strip()


def build_references(article: dict) -> str:
    refs = []
    if article.get("verified_reference"):
        refs.append(article["verified_reference"])
    refs.append(f"{article['source_name']}. {article['title']}. {article['url']}")
    return "\n".join(f"{i}. {r}" for i, r in enumerate(refs, 1))


def assemble_post(raw: dict, article: dict, n: int, today_compact: str) -> dict:
    slides_in = raw.get("slides") or []
    if len(slides_in) != 4:
        raise ValueError("slides 數量不是 4 張")
    expected = ["cover", "points", "points", "takeaway"]
    slides = []
    for i, (s, t) in enumerate(zip(slides_in, expected), 1):
        slide = {"slide_num": i, "type": t, "tag": scrub(s.get("tag", "")),
                 "headline": scrub(s.get("headline", "")), "footer": article["footer_citation"]}
        if not slide["headline"]:
            raise ValueError(f"第 {i} 張缺少 headline")
        if t == "cover":
            slide["subheadline"] = scrub(s.get("subheadline", ""))
            slide["meta_badge"] = scrub(s.get("meta_badge", "")) or f"研究來源：{article['source_name']}"
        elif t == "points":
            pts = [scrub(p) for p in (s.get("points") or []) if scrub(p)]
            if len(pts) < 2:
                raise ValueError(f"第 {i} 張要點不足")
            slide["points"] = pts[:3]
        else:
            slide["summary"] = scrub(s.get("summary", ""))
            slide["cta"] = scrub(s.get("cta", ""))
        slides.append(slide)

    hashtags = " ".join(h if h.startswith("#") else "#" + h for h in (raw.get("hashtags") or []))
    body = scrub(raw.get("body", ""))
    # 若 AI 仍自行寫了參考文獻段落，一律移除，改用經驗證的出處
    body = re.split(r"■\s*資料來源|參考文獻|References", body)[0].strip()
    caption = f"{body}\n\n■ 資料來源 (References)：\n{build_references(article)}"
    if hashtags:
        caption += f"\n\n{hashtags}"

    theme, accent = PALETTES[(n - 1) % len(PALETTES)]
    return {
        "id": f"post_{today_compact}_{n}",
        "selected": True,
        "category": scrub(raw.get("category", "")) or "癌症研究",
        "source_name": article["source_name"],
        "source_url": article["url"],
        "original_title": article["title"],
        "doi": article.get("doi", ""),
        "theme_color": theme,
        "accent_color": accent,
        "caption": caption,
        "slides": slides,
    }


def write_outputs(base_dir: str, data: dict):
    for rel in ["data/daily_posts.json", "docs/data/daily_posts.json"]:
        path = os.path.join(base_dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def sync_existing(base_dir: str):
    src = os.path.join(base_dir, "data", "daily_posts.json")
    dst = os.path.join(base_dir, "docs", "data", "daily_posts.json")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(src, "r", encoding="utf-8") as fi, open(dst, "w", encoding="utf-8") as fo:
        fo.write(fi.read())


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    tz = datetime.timezone(datetime.timedelta(hours=8))
    now = datetime.datetime.now(tz)
    today_str, today_compact = now.strftime("%Y-%m-%d"), now.strftime("%Y%m%d")

    if not GEMINI_API_KEY:
        print("ℹ️ 未提供 GEMINI_API_KEY，保留現有資料")
        sync_existing(base_dir)
        sys.exit(0)

    articles = fetch_latest_rss_articles(max_per_source=6)
    print(f"已抓取 {len(articles)} 則最新癌症外電，開始擷取原文期刊出處…")
    articles = [enrich_article_reference(a) for a in articles]
    verified = sum(1 for a in articles if a.get("verified_reference"))
    print(f"其中 {verified} 則取得經驗證的期刊出處")

    candidates = [
        {
            "index": i,
            "source_name": a["source_name"],
            "title": a["title"],
            "summary": a.get("summary", ""),
            "page_excerpt": a.get("page_excerpt", ""),
            "has_verified_reference": bool(a.get("verified_reference")),
        }
        for i, a in enumerate(articles)
    ]

    try:
        result = call_gemini(candidates, today_str)
        posts, used = [], set()
        for raw in result.get("posts", []):
            idx = raw.get("source_index")
            if not isinstance(idx, int) or idx in used or not (0 <= idx < len(articles)):
                continue
            try:
                posts.append(assemble_post(raw, articles[idx], len(posts) + 1, today_compact))
                used.add(idx)
            except ValueError as exc:
                print(f"[WARN] 略過一則格式不符的貼文：{exc}")
            if len(posts) == 5:
                break
        if len(posts) < 3:
            raise ValueError(f"有效貼文僅 {len(posts)} 則")
    except Exception as exc:
        print(f"⚠️ 本次產生失敗（{exc}），保留前一次的資料以免網站壞掉")
        sync_existing(base_dir)
        sys.exit(0)

    write_outputs(base_dir, {
        "date": today_str,
        "generated_at": now.isoformat(),
        "posts": posts,
    })
    print(f"✅ 已完成 {today_str} 共 {len(posts)} 則癌症研究專業編譯（出處皆由原文頁 / Crossref 驗證）")
