#!/usr/bin/env python3
"""
雲端自動化癌症研究抓取與 Gemini API 專業知識編譯腳本 (供 GitHub Actions 每日 08:00 執行)
- 嚴格對齊「Today Oncology IG Posts」與「IG Curator Dashboard」之黃金品質標準
- 透過原文頁 DOI 擷取 + Crossref 官方 API 驗證確切期刊 Reference（作者、篇名、期刊、年份、DOI）
- 使用 Gemini responseSchema 強制鎖定 4 張圖卡結構（cover / points / points / takeaway），杜絕格式跑掉
"""
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from fetch_and_curate import fetch_latest_rss_articles, enrich_article_reference

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
FALLBACK_MODELS = [
    GEMINI_MODEL,
    "gemini-1.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]

BANNED_PHRASES = [
    "往左滑", "左滑", "歡迎留言", "留言分享", "收藏＋分享", "收藏", "追蹤我們", "按讚", "小盒子",
    "主治醫師", "諮詢醫師", "請教醫師", "與醫師討論", "建議定期篩檢", "尋求醫療建議",
]

PALETTES = [
    ("#0F766E", "#14B8A6"),
    ("#1D4ED8", "#3B82F6"),
    ("#6D28D9", "#8B5CF6"),
    ("#B45309", "#F59E0B"),
    ("#BE123C", "#F43F5E"),
]

SYSTEM_PROMPT = """你是一位頂尖的腫瘤學（Oncology）學術編譯專家，專門為專業醫療知識社群撰寫「Today Oncology IG Posts」等級的高深度繁體中文（台灣醫學慣用語）研究解析與 1080x1350 輪播圖卡。

請從候選清單中，挑選 5 則最具臨床突破性或基礎腫瘤學價值的癌症研究：
- **優先納入近期六大國際腫瘤醫學會議公布之重要研究**：**ASCO**（美國臨床腫瘤學會）、**ESMO**（歐洲腫瘤內科學會）、**AACR**（美國癌症研究協會）、**WCLC**（世界肺癌大會 / IASLC）、**SITC**（癌症免疫治療學會）、**SABCS**（聖安東尼奧乳癌研討會）及其官方旗艦期刊（*JCO*、*Annals of Oncology*、*Cancer Discovery*、*JTO*、*JITC*、*Clinical Cancer Research*）。
- 同時搭配 NCI、ScienceDaily、Medscape 等權威醫藥網站中具 verified_reference 的重大臨床試驗、免疫/標靶新機制、液態切片/生物標記或抗藥性演化研究。
- 若該研究源自上述醫學會議（如 ASCO、ESMO、AACR、WCLC、SITC、SABCS），請於第 1 張圖卡的 `tag` 或 `meta_badge` 以及貼文首段明確標示會議名稱（例如：`ASCO 臨床研究更新`、`WCLC 晚期肺癌數據`、`SABCS 乳癌標靶突破`）。

【黃金品質標準（必須 100% 對齊以下範例之深度與格式）】
1. **分類標籤 (`category`)**：必須為精準的 4～6 字腫瘤學次領域（例如：`mRNA 癌症疫苗`、`液態切片檢測`、`抗藥性演化`、`細胞工程免疫`、`腫瘤微環境`、`單細胞預後模型`），**嚴禁填寫籠統的 `Oncology` 或 `癌症研究`**。
2. **第 1 張封面圖卡 (`cover`)**：
   - `tag`：6～10 字研究性質（如 `臨床三期研究更新`、`分子診斷研究`、`演化腫瘤學研究`、`細胞免疫工程`）。
   - `headline`：必須以 `\\n` 分成 **3 行**，每行 8～13 字，直接點出核心療法/機制與量化成果（例如：`個人化 mRNA 癌症疫苗\\n降低高風險黑色素瘤\\n復發與死亡風險達 42%`）。
   - `subheadline`：22～34 字專業副標題（例如：`mRNA-4157 (V940) 合併 PD-1 抑制劑之術後輔助治療研究解析`）。
   - `meta_badge`：14～22 字研究屬性（例如：`研究設計：多中心隨機對照臨床試驗` 或 `研究焦點：非小細胞肺癌 (NSCLC) 生物標記`）。
3. **第 2 張機制圖卡 (`points_mechanism`) 與第 3 張數據圖卡 (`points_data`)**：
   - `tag`：4～6 字（如 `分子機制`、`評估限制`、`臨床數據`、`研究數據`、`實驗驗證`）。
   - `headline`：以 `\\n` 分成 **2 行**（每行 9～14 字），提出具體科學問題或核心結論（例如：`個人化新抗原疫苗\\n如何精準誘導抗腫瘤免疫？`）。
   - `points`：固定 **3 點**，每一點都**必須以「四至六字專有名詞小標：」開頭**，後接 28～42 字的具體分子機制或實驗/臨床數據說明！
     範例：
     - `"基因體比對：對患者切除之腫瘤進行全外顯子定序，鑑定多達 34 種特異性突變新抗原"`
     - `"序列編碼：將新抗原序列編碼至單一 mRNA 分子中，轉譯後由樹突細胞呈現予免疫系統"`
     - `"T 細胞擴增：專一性活化 CD4+ 與 CD8+ T 細胞，針對微量殘存癌細胞建立免疫記憶"`
4. **第 4 張總結圖卡 (`takeaway`)**：
   - `tag`：固定為 `學術意義與展望` 或 `臨床轉譯意義`。
   - `headline`：以 `\\n` 分成 **2 行**（每行 9～14 字），凝練出領域典範轉移（例如：`從廣譜免疫激活邁向\\n個體化新抗原精準標靶`）。
   - `summary`：65～95 字深度學術與臨床轉譯意義總結。
   - `cta`：必須以 `後續觀察：` 開頭（30～42 字），指出下一階段值得關注的科學指標或臨床終點（例如：`後續觀察：非小細胞肺癌與胰臟癌三期試驗之整體存活期（OS）數據`）。
5. **IG 專業貼文內文 (`body`)**：
   - 第一行必須為 `【具高度專業資訊量之研究標題】`
   - 第一段完整敘述研究發表機構/期刊、研究對象與核心發現（附英文專有名詞與縮寫括號對照，如 `循環腫瘤 DNA（ctDNA）`、`無惡化存活期（PFS）`）。
   - 第二段以 `■ 核心作用機制：` 或 `■ 研究核心發現：` 為小標，下列 `1.`、`2.`、`3.` 三點，每點皆以「專有名詞小標：」開頭深入剖析。
   - 第三段（選填）以 `■ 臨床轉譯與研究展望：` 簡述跨癌種或未來應用。
   - **不要在 `body` 裡自己寫參考文獻或 DOI**（系統會自動將經過 Crossref 驗證的確切 `■ 資料來源 (References)：` 附加在最後一段）。
6. **嚴格禁令**：
   - 嚴禁任何推銷或社群互動語（不可出現「往左滑、歡迎留言、收藏＋分享、追蹤我們」）。
   - 嚴禁任何對個人的醫療建議（不可出現「與主治醫師討論評估、建議定期篩檢」）。
   - 嚴禁編造候選資料中未提及的數據。
"""

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "required": ["posts"],
    "properties": {
        "posts": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": [
                    "source_index", "category", "body", "hashtags",
                    "cover", "points_mechanism", "points_data", "takeaway"
                ],
                "properties": {
                    "source_index": {"type": "INTEGER"},
                    "category": {"type": "STRING"},
                    "body": {"type": "STRING"},
                    "hashtags": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "cover": {
                        "type": "OBJECT",
                        "required": ["tag", "headline", "subheadline", "meta_badge"],
                        "properties": {
                            "tag": {"type": "STRING"},
                            "headline": {"type": "STRING"},
                            "subheadline": {"type": "STRING"},
                            "meta_badge": {"type": "STRING"},
                        },
                    },
                    "points_mechanism": {
                        "type": "OBJECT",
                        "required": ["tag", "headline", "points"],
                        "properties": {
                            "tag": {"type": "STRING"},
                            "headline": {"type": "STRING"},
                            "points": {"type": "ARRAY", "items": {"type": "STRING"}},
                        },
                    },
                    "points_data": {
                        "type": "OBJECT",
                        "required": ["tag", "headline", "points"],
                        "properties": {
                            "tag": {"type": "STRING"},
                            "headline": {"type": "STRING"},
                            "points": {"type": "ARRAY", "items": {"type": "STRING"}},
                        },
                    },
                    "takeaway": {
                        "type": "OBJECT",
                        "required": ["tag", "headline", "summary", "cta"],
                        "properties": {
                            "tag": {"type": "STRING"},
                            "headline": {"type": "STRING"},
                            "summary": {"type": "STRING"},
                            "cta": {"type": "STRING"},
                        },
                    },
                },
            },
        }
    },
}


def call_gemini(candidates: list, today_str: str) -> dict:
    user_content = (
        f"今日日期：{today_str}\n"
        f"以下為今日抓取並附帶原文頁面摘錄與驗證出處之國際醫藥網站癌症研究候選清單：\n"
        f"{json.dumps(candidates, ensure_ascii=False, indent=2)}\n\n"
        "請嚴格依照黃金品質標準，挑選 6 則不同 source_index 的研究（系統將取前 5 則最完整者發布），輸出 JSON。"
    )
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": user_content}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    last_err = None

    # 依序嘗試主力模型與備援模型（解決免費額度 429 或尖峰時段 503 Overloaded 導致中斷的問題）
    models_to_try = []
    for m in FALLBACK_MODELS:
        if m and m not in models_to_try:
            models_to_try.append(m)

    for model_name in models_to_try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_name}:generateContent?key={GEMINI_API_KEY}"
        )
        for attempt in range(1, 3):
            try:
                print(f"🤖 呼叫 Gemini 模型：{model_name} (第 {attempt} 次嘗試)...")
                req = urllib.request.Request(
                    url,
                    data=body_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=180) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                candidates_list = result.get("candidates", [])
                if not candidates_list:
                    raise ValueError("Gemini 回傳結構中無候選內容 candidates")
                parts = candidates_list[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts if "text" in p).strip()
                if not text:
                    raise ValueError("Gemini 回傳之 text 內容為空")
                if text.startswith("```"):
                    text = re.sub(r"^```(?:json)?\s*", "", text)
                    text = re.sub(r"\s*```$", "", text)
                return json.loads(text.strip())
            except urllib.error.HTTPError as he:
                err_body = ""
                try:
                    err_body = he.read().decode("utf-8", errors="ignore")[:300]
                except Exception:
                    pass
                last_err = f"HTTP {he.code} on {model_name}: {err_body}"
                print(f"[WARN] {last_err}")
                time.sleep(4 * attempt)
            except Exception as exc:
                last_err = f"{type(exc).__name__} on {model_name}: {exc}"
                print(f"[WARN] {last_err}")
                time.sleep(3 * attempt)

    raise RuntimeError(f"所有 Gemini 模型嘗試皆失敗，最後錯誤：{last_err}")


def scrub(text: str, keep_line: bool = False) -> str:
    if not text:
        return ""
    if keep_line:
        cleaned = str(text)
        for b in BANNED_PHRASES:
            cleaned = cleaned.replace(b, "")
        return cleaned.strip()
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


def assemble_post(raw: dict, article: dict, n: int) -> dict:
    footer = article.get("footer_citation") or f"資料來源：{article['source_name']}"
    cover = raw["cover"]
    pm = raw["points_mechanism"]
    pd = raw["points_data"]
    tk = raw["takeaway"]

    slides = [
        {
            "slide_num": 1,
            "type": "cover",
            "tag": scrub(cover.get("tag", "重點研究解析"), keep_line=True),
            "headline": scrub(cover.get("headline", ""), keep_line=True),
            "subheadline": scrub(cover.get("subheadline", ""), keep_line=True),
            "meta_badge": scrub(cover.get("meta_badge", ""), keep_line=True) or f"研究來源：{article['source_name']}",
            "footer": footer,
        },
        {
            "slide_num": 2,
            "type": "points",
            "tag": scrub(pm.get("tag", "分子機制"), keep_line=True),
            "headline": scrub(pm.get("headline", ""), keep_line=True),
            "points": [scrub(p, keep_line=True) for p in (pm.get("points") or []) if scrub(p, keep_line=True)][:3],
            "footer": footer,
        },
        {
            "slide_num": 3,
            "type": "points",
            "tag": scrub(pd.get("tag", "關鍵數據"), keep_line=True),
            "headline": scrub(pd.get("headline", ""), keep_line=True),
            "points": [scrub(p, keep_line=True) for p in (pd.get("points") or []) if scrub(p, keep_line=True)][:3],
            "footer": footer,
        },
        {
            "slide_num": 4,
            "type": "takeaway",
            "tag": scrub(tk.get("tag", "學術意義與展望"), keep_line=True),
            "headline": scrub(tk.get("headline", ""), keep_line=True),
            "summary": scrub(tk.get("summary", "")),
            "cta": scrub(tk.get("cta", ""), keep_line=True),
            "footer": footer,
        },
    ]

    for s in slides:
        if not s["headline"]:
            raise ValueError("圖卡缺少 headline")
        if s["type"] == "points" and len(s["points"]) < 3:
            raise ValueError("要點圖卡不足 3 點")

    hashtags = " ".join(
        h if h.startswith("#") else "#" + h
        for h in (raw.get("hashtags") or ["#腫瘤學", "#癌症研究", "#精準醫學"])
    )
    body = scrub(raw.get("body", ""))
    body = re.split(r"■\s*資料來源|參考文獻|References", body)[0].strip()
    caption = f"{body}\n\n■ 資料來源 (References)：\n{build_references(article)}\n\n{hashtags}"

    theme, accent = PALETTES[(n - 1) % len(PALETTES)]
    return {
        "id": f"post-{n}",
        "selected": True,
        "category": scrub(raw.get("category", "")) or "腫瘤學研究",
        "source_name": article["source_name"],
        "source_url": article["url"],
        "original_title": article["title"],
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


def load_seen_titles(base_dir: str) -> set:
    seen = set()
    for rel in ["data/daily_posts.json", "docs/data/daily_posts.json", "data/seen_history.json"]:
        p = os.path.join(base_dir, rel)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict):
                    for post in d.get("posts", []):
                        if post.get("original_title"):
                            seen.add(post["original_title"].strip().lower())
                    for t in d.get("titles", []):
                        seen.add(str(t).strip().lower())
            except Exception:
                pass
    return seen


def save_seen_titles(base_dir: str, seen: set, new_posts: list):
    for p in new_posts:
        if p.get("original_title"):
            seen.add(p["original_title"].strip().lower())
    hist_path = os.path.join(base_dir, "data", "seen_history.json")
    os.makedirs(os.path.dirname(hist_path), exist_ok=True)
    # 保留最近 60 篇紀錄，避免重複挑選；若超過 60 篇則自動循環滾動
    recent_list = list(seen)[-60:]
    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump({"titles": recent_list}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    tz = datetime.timezone(datetime.timedelta(hours=8))
    now = datetime.datetime.now(tz)
    today_str = now.strftime("%Y-%m-%d")

    if not GEMINI_API_KEY:
        print("ℹ️ 未提供 GEMINI_API_KEY，保留現有黃金標準資料並同步至 docs/data/daily_posts.json")
        sync_existing(base_dir)
        sys.exit(0)

    seen_titles = load_seen_titles(base_dir)
    all_articles = fetch_latest_rss_articles(max_per_source=6)
    fresh_articles = [
        a for a in all_articles
        if a.get("title", "").strip().lower() not in seen_titles
    ]
    # 若未看過的新文章夠多（>= 8 篇），優先只從全新文章挑選，確保同一天多次執行也會換一批新文章！
    articles = fresh_articles if len(fresh_articles) >= 8 else all_articles
    print(f"已抓取 {len(all_articles)} 則最新癌症外電（其中未曾發布之全新研究 {len(fresh_articles)} 則），開始擷取原文期刊出處…")
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
            "verified_reference": a.get("verified_reference", ""),
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
                posts.append(assemble_post(raw, articles[idx], len(posts) + 1))
                used.add(idx)
            except Exception as exc:
                print(f"[WARN] 略過一則格式不符的貼文：{exc}")
            if len(posts) == 5:
                break
        if 0 < len(posts) < 5:
            print(f"ℹ️ 本次成功編譯 {len(posts)} 則新研究，自動由現有庫存補足至 5 則")
            existing_path = os.path.join(base_dir, "data", "daily_posts.json")
            if os.path.exists(existing_path):
                with open(existing_path, "r", encoding="utf-8") as ef:
                    existing_posts = json.load(ef).get("posts", [])
                new_titles = {p.get("original_title") for p in posts}
                for ep in existing_posts:
                    if ep.get("original_title") not in new_titles:
                        n_idx = len(posts) + 1
                        ep["id"] = f"post-{n_idx}"
                        ep["theme_color"], ep["accent_color"] = PALETTES[(n_idx - 1) % len(PALETTES)]
                        posts.append(ep)
                        if len(posts) == 5:
                            break
        if len(posts) < 5:
            raise ValueError(f"有效貼文僅 {len(posts)} 則，未達 5 則標準")
    except Exception as exc:
        print(f"⚠️ 本次呼叫 Gemini 或解析過程遇到異常：{exc}")
        print("ℹ️ 正在安全自現有高品質研究資料載入，確保網站持續提供完整 5 則研究並更新發布日期...")
        existing_path = os.path.join(base_dir, "data", "daily_posts.json")
        fallback_posts = []
        if os.path.exists(existing_path):
            with open(existing_path, "r", encoding="utf-8") as ef:
                fallback_posts = json.load(ef).get("posts", [])
        if fallback_posts:
            posts = fallback_posts[:5]
            for n_idx, p in enumerate(posts, 1):
                p["id"] = f"post-{n_idx}"
                p["theme_color"], p["accent_color"] = PALETTES[(n_idx - 1) % len(PALETTES)]
        else:
            sync_existing(base_dir)
            sys.exit(1)

    write_outputs(base_dir, {
        "date": today_str,
        "generated_at": now.isoformat(),
        "posts": posts,
    })
    save_seen_titles(base_dir, seen_titles, posts)
    print(f"✅ 已完成 {today_str} 共 5 則黃金標準癌症研究專業編譯！")
