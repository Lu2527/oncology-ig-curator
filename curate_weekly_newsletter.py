#!/usr/bin/env python3
"""
每週腫瘤臨床深度週報 (Oncology Weekly Deep Dive)

讀取使用者於 GitHub Pages 看板按下「⭐ 加入本週週報」所記錄的貼文
（docs/data/weekly_picks.json 中尚未發刊的項目），針對每一篇：
  1. 以 DOI 向 PubMed 取回原始摘要作為事實依據（降低 AI 幻覺）
  2. 由 Claude / Gemini 撰寫深度臨床分析：
     - 試驗設計與受試族群
     - 療效與安全性數據
     - 與現行標準治療及 NCCN / ESMO 指引之比較
     - 對台灣臨床實務之意涵（TFDA / 健保給付）
     - 相關進行中試驗與未來方向
  3. 產出本期主編導讀
輸出：
  docs/newsletter/YYYY-MM-DD.html   （可直接貼入 Gmail / Outlook 的響應式 HTML）
  docs/newsletter/YYYY-MM-DD.md     （可貼入 Substack / Beehiiv）
  docs/newsletter/index.html        （歷期週報目錄）
並將已收錄的 picks 標記 issue 日期，避免下期重複。

用法：
  python3 curate_weekly_newsletter.py            # 正式產出
  python3 curate_weekly_newsletter.py --dry-run  # 只列出將收錄的貼文，不呼叫 AI
"""
import datetime
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from cloud_curate import (
    ANTHROPIC_API_KEY,
    GEMINI_API_KEY,
    CLAUDE_FALLBACK_MODELS,
    FALLBACK_MODELS,
    BillingError,
)
from fetch_and_curate import _http_get, _clean_html

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PICKS_PATH = os.path.join(BASE_DIR, "docs", "data", "weekly_picks.json")
NL_DIR = os.path.join(BASE_DIR, "docs", "newsletter")
ISSUES_PATH = os.path.join(NL_DIR, "issues.json")
SITE_URL = os.environ.get("SITE_URL", "https://lu2527.github.io/oncology-ig-curator")
TZ = datetime.timezone(datetime.timedelta(hours=8))

# ---------------------------------------------------------------------------
# Prompts & schemas
# ---------------------------------------------------------------------------

ANALYSIS_SYSTEM = """你是一位資深腫瘤內科主治醫師兼臨床試驗方法學專家，為台灣腫瘤科醫師、藥師、臨床研究人員撰寫「每週腫瘤臨床深度週報」。
請以繁體中文（台灣醫學慣用語，專有名詞附英文縮寫）針對一篇研究做深度臨床分析。

【事實依據規則（最重要）】
1. 研究本身的數據（受試人數、HR、95% CI、p 值、中位 PFS/OS、ORR、≥3 級不良事件比例等）只能取自提供的「PubMed 原始摘要」與「IG 貼文內容」。
   摘要中沒有的數字，一律寫「摘要未揭露」，嚴禁推測或編造。
2. 若該文獻並非臨床試驗（例如綜述、流行病學、轉譯/基礎研究、政策分析），請在試驗設計欄如實說明研究類型與方法，療效欄改寫主要發現，不要硬套 RCT 架構。
3. 「現行標準治療 / NCCN、ESMO 指引」「台灣 TFDA 核准與健保給付」「進行中試驗」可運用你的醫學知識，但：
   - 只寫你有把握的內容；不確定時明確寫「截至撰稿時資訊有限，需再確認」。
   - 台灣給付狀態變動頻繁，請以保守語氣陳述，並指出需查證的重點（例如：是否限定特定生物標記、線別、事前審查）。
   - 試驗名稱/NCT 編號只列你確定存在者。
4. 嚴禁任何對個別病患之醫療建議，嚴禁行銷或社群互動語。
5. 每個條列項目 30～90 字，資訊密度高、避免空話。"""

ANALYSIS_SCHEMA = {
    "type": "object",
    "required": [
        "title_zh", "study_type", "bottom_line", "trial_design", "efficacy_safety",
        "soc_comparison", "taiwan_implications", "ongoing_trials", "limitations_note",
    ],
    "properties": {
        "title_zh": {"type": "string", "description": "20～36 字的週報標題，點出療法/族群/關鍵結果"},
        "study_type": {"type": "string", "description": "例如：第三期隨機對照試驗、前瞻性世代研究、系統性回顧、轉譯研究"},
        "bottom_line": {"type": "string", "description": "60～110 字的一段式臨床重點（Bottom line）"},
        "trial_design": {
            "type": "object",
            "required": ["phase_design", "population", "intervention", "comparator", "primary_endpoint", "key_criteria"],
            "properties": {
                "phase_design": {"type": "string"},
                "population": {"type": "string"},
                "intervention": {"type": "string"},
                "comparator": {"type": "string"},
                "primary_endpoint": {"type": "string"},
                "key_criteria": {"type": "array", "items": {"type": "string"}},
            },
        },
        "efficacy_safety": {
            "type": "object",
            "required": ["key_results", "safety", "interpretation"],
            "properties": {
                "key_results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["endpoint", "result"],
                        "properties": {
                            "endpoint": {"type": "string", "description": "例如：中位 PFS、OS HR、ORR"},
                            "result": {"type": "string", "description": "數值（含 95% CI / p 值），或「摘要未揭露」"},
                        },
                    },
                },
                "safety": {"type": "array", "items": {"type": "string"}},
                "interpretation": {"type": "array", "items": {"type": "string"}},
            },
        },
        "soc_comparison": {"type": "array", "items": {"type": "string"}, "description": "與現行標準治療、NCCN / ESMO 指引之定位比較，2～4 點"},
        "taiwan_implications": {"type": "array", "items": {"type": "string"}, "description": "TFDA 核准、健保給付、在地流行病學（如 EGFR 盛行率）等，2～4 點"},
        "ongoing_trials": {"type": "array", "items": {"type": "string"}, "description": "相關進行中試驗與未來方向，2～4 點"},
        "limitations_note": {"type": "string", "description": "一句話說明本分析的資訊來源限制（例如僅依據摘要）"},
    },
}

EDITORIAL_SYSTEM = """你是「腫瘤臨床深度週報」的主編，讀者為台灣腫瘤科醫療專業人員。
根據本期收錄文章的分析結果，以繁體中文撰寫本期導讀：點出本期文章之間的共同脈絡或臨床趨勢，語氣專業精煉，不誇大、不推銷、不提供個人醫療建議。"""

EDITORIAL_SCHEMA = {
    "type": "object",
    "required": ["issue_title", "editor_note", "themes"],
    "properties": {
        "issue_title": {"type": "string", "description": "本期主題標題，18～30 字"},
        "editor_note": {"type": "string", "description": "180～320 字主編導讀"},
        "themes": {"type": "array", "items": {"type": "string"}, "description": "本期 2～4 個關鍵字主題（每個 2～8 字）"},
    },
}


def to_gemini_schema(s):
    """將小寫 JSON Schema 轉為 Gemini responseSchema（大寫 type、移除不支援欄位）。"""
    if isinstance(s, dict):
        out = {}
        for k, v in s.items():
            if k == "type":
                out[k] = str(v).upper()
            elif k == "properties":
                out[k] = {pk: to_gemini_schema(pv) for pk, pv in v.items()}
            elif k == "items":
                out[k] = to_gemini_schema(v)
            elif k in ("required", "description"):
                out[k] = v
        return out
    return s


# ---------------------------------------------------------------------------
# LLM callers (Claude first, Gemini fallback) — mirrors cloud_curate.py behaviour
# ---------------------------------------------------------------------------

def _unique(seq):
    out = []
    for x in seq:
        if x and x not in out:
            out.append(x)
    return out


def _claude(system: str, user: str, schema: dict, tool_name: str) -> dict:
    last_err = None
    for model in _unique(CLAUDE_FALLBACK_MODELS):
        payload = {
            "model": model,
            "max_tokens": 8192,
            "temperature": 0.2,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "tools": [{"name": tool_name, "description": "輸出結構化週報內容", "input_schema": schema}],
            "tool_choice": {"type": "tool", "name": tool_name},
        }
        body = json.dumps(payload).encode("utf-8")
        for attempt in (1, 2):
            try:
                print(f"🤖 Claude {model}（第 {attempt} 次）...")
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/messages", data=body, method="POST",
                    headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_API_KEY,
                             "anthropic-version": "2023-06-01"},
                )
                with urllib.request.urlopen(req, timeout=240) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                for block in result.get("content", []):
                    if block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
                        return block["input"]
                raise ValueError("未找到 tool_use 區塊")
            except urllib.error.HTTPError as he:
                err = he.read().decode("utf-8", "ignore")[:300] if he.fp else ""
                last_err = f"HTTP {he.code} on {model}: {err}"
                print(f"[WARN] {last_err}")
                if "credit balance is too low" in err.lower():
                    raise BillingError(last_err)
                if he.code in (400, 401, 403, 404):
                    break
                time.sleep(4 * attempt)
            except Exception as exc:
                last_err = f"{type(exc).__name__} on {model}: {exc}"
                print(f"[WARN] {last_err}")
                time.sleep(3 * attempt)
    raise RuntimeError(f"Claude 全部失敗：{last_err}")


def _gemini(system: str, user: str, schema: dict) -> dict:
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 16384,
            "responseMimeType": "application/json",
            "responseSchema": to_gemini_schema(schema),
        },
    }
    body = json.dumps(payload).encode("utf-8")
    last_err = None
    for model in _unique(FALLBACK_MODELS):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        for attempt in (1, 2):
            try:
                print(f"🤖 Gemini {model}（第 {attempt} 次）...")
                req = urllib.request.Request(url, data=body, method="POST",
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=240) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                parts = (result.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
                text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
                return json.loads(text)
            except urllib.error.HTTPError as he:
                err = he.read().decode("utf-8", "ignore")[:300] if he.fp else ""
                last_err = f"HTTP {he.code} on {model}: {err}"
                print(f"[WARN] {last_err}")
                if he.code == 402:
                    raise BillingError(last_err)
                if he.code in (400, 403, 404):
                    break
                time.sleep(4 * attempt)
            except Exception as exc:
                last_err = f"{type(exc).__name__} on {model}: {exc}"
                print(f"[WARN] {last_err}")
                time.sleep(3 * attempt)
    raise RuntimeError(f"Gemini 全部失敗：{last_err}")


def call_llm(system: str, user: str, schema: dict, tool_name: str) -> dict:
    if ANTHROPIC_API_KEY:
        try:
            return _claude(system, user, schema, tool_name)
        except Exception as e:
            if not GEMINI_API_KEY or GEMINI_API_KEY.startswith("sk-ant-"):
                raise
            print(f"[WARN] Claude 失敗（{e}），改用 Gemini")
    return _gemini(system, user, schema)


# ---------------------------------------------------------------------------
# PubMed grounding
# ---------------------------------------------------------------------------

def extract_doi(post: dict) -> str:
    for text in (post.get("source_url", ""), post.get("caption", "")):
        m = re.search(r"(10\.\d{4,9}/[^\s\"'<>)\]，。]+)", text or "")
        if m:
            return m.group(1).rstrip(".")
    return ""


def fetch_pubmed_abstract(doi: str) -> dict:
    if not doi:
        return {}
    try:
        q = urllib.parse.urlencode({"db": "pubmed", "term": f"{doi}[doi]", "retmode": "json"})
        ids = json.loads(_http_get(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{q}", 15)) \
            .get("esearchresult", {}).get("idlist", [])
        if not ids:
            return {}
        q = urllib.parse.urlencode({"db": "pubmed", "id": ids[0], "retmode": "xml"})
        root = ET.fromstring(_http_get(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?{q}", 20))
        art = root.find(".//PubmedArticle")
        if art is None:
            return {}
        parts = []
        for ab in art.findall(".//AbstractText"):
            label = ab.attrib.get("Label", "")
            txt = _clean_html("".join(ab.itertext()))
            if txt:
                parts.append(f"{label}: {txt}" if label else txt)
        pub_types = [_clean_html(pt.text or "") for pt in art.findall(".//PublicationType")]
        return {
            "pmid": ids[0],
            "title": _clean_html(art.findtext(".//ArticleTitle") or ""),
            "journal": _clean_html(art.findtext(".//Journal/Title") or ""),
            "publication_types": pub_types,
            "abstract": " ".join(parts),
        }
    except Exception as e:
        print(f"[WARN] PubMed 查詢失敗 ({doi}): {e}")
        return {}


def post_digest(post: dict) -> str:
    lines = [f"原文標題：{post.get('original_title','')}", f"出處：{post.get('source_name','')}",
             f"連結：{post.get('source_url','')}", "", "IG 貼文內文：", post.get("caption", "")]
    for s in post.get("slides", []):
        lines.append(f"[圖卡 {s.get('slide_num')}｜{s.get('tag','')}] {s.get('headline','').replace(chr(10),' ')}")
        for p in s.get("points", []) or []:
            lines.append(f"  - {p}")
        if s.get("summary"):
            lines.append(f"  {s['summary']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

E = lambda s: html.escape(str(s or ""))


def _li(items):
    return "".join(f'<li style="margin:0 0 6px 0;">{E(x)}</li>' for x in (items or []) if x)


def _section(title, inner):
    return (f'<h3 style="font-size:15px;color:#0f766e;margin:22px 0 8px 0;border-left:4px solid #14b8a6;'
            f'padding-left:8px;">{E(title)}</h3>{inner}')


def render_article_html(i: int, a: dict) -> str:
    an, post, pm = a["analysis"], a["post"], a.get("pubmed") or {}
    td, es = an.get("trial_design", {}), an.get("efficacy_safety", {})
    design_rows = [
        ("研究設計", td.get("phase_design")), ("受試族群", td.get("population")),
        ("試驗組", td.get("intervention")), ("對照組", td.get("comparator")),
        ("主要指標", td.get("primary_endpoint")),
    ]
    design_tbl = "".join(
        f'<tr><td style="padding:6px 10px;background:#f1f5f9;width:88px;font-weight:600;vertical-align:top;'
        f'border-bottom:1px solid #e2e8f0;">{E(k)}</td><td style="padding:6px 10px;border-bottom:1px solid #e2e8f0;">'
        f'{E(v)}</td></tr>' for k, v in design_rows if v)
    results_tbl = "".join(
        f'<tr><td style="padding:6px 10px;border-bottom:1px solid #e2e8f0;font-weight:600;">{E(r.get("endpoint"))}</td>'
        f'<td style="padding:6px 10px;border-bottom:1px solid #e2e8f0;">{E(r.get("result"))}</td></tr>'
        for r in es.get("key_results", []))
    doi = a.get("doi")
    src_link = post.get("source_url") or (f"https://doi.org/{doi}" if doi else "")
    pm_link = f'https://pubmed.ncbi.nlm.nih.gov/{pm["pmid"]}/' if pm.get("pmid") else ""

    body = [
        f'<div style="margin:0 0 36px 0;padding:0 0 28px 0;border-bottom:1px solid #e2e8f0;">',
        f'<div style="font-size:12px;color:#64748b;">STUDY {i}｜{E(post.get("category"))}｜{E(an.get("study_type"))}｜IG 發佈日 {E(a["date"])}</div>',
        f'<h2 style="font-size:20px;line-height:1.45;margin:6px 0 4px 0;color:#0f172a;">{E(an.get("title_zh"))}</h2>',
        f'<div style="font-size:12px;color:#64748b;font-style:italic;margin-bottom:12px;">{E(post.get("original_title"))}<br>{E(pm.get("journal") or post.get("source_name"))}</div>',
        f'<div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:10px;padding:12px 14px;margin:10px 0;">'
        f'<b style="color:#047857;">Bottom line：</b>{E(an.get("bottom_line"))}</div>',
        _section("一、試驗設計與受試族群",
                 f'<table role="presentation" style="width:100%;border-collapse:collapse;font-size:14px;">{design_tbl}</table>'
                 + (f'<div style="font-size:13px;margin-top:8px;"><b>關鍵收案條件：</b></div><ul style="padding-left:20px;margin:6px 0;font-size:14px;">{_li(td.get("key_criteria"))}</ul>' if td.get("key_criteria") else "")),
        _section("二、療效與安全性數據",
                 (f'<table role="presentation" style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:8px;">'
                  f'<tr><th style="text-align:left;padding:6px 10px;background:#0f766e;color:#fff;">指標</th>'
                  f'<th style="text-align:left;padding:6px 10px;background:#0f766e;color:#fff;">結果</th></tr>{results_tbl}</table>' if results_tbl else "")
                 + (f'<div style="font-size:13px;"><b>安全性：</b></div><ul style="padding-left:20px;margin:6px 0;font-size:14px;">{_li(es.get("safety"))}</ul>' if es.get("safety") else "")
                 + (f'<div style="font-size:13px;"><b>數據解讀：</b></div><ul style="padding-left:20px;margin:6px 0;font-size:14px;">{_li(es.get("interpretation"))}</ul>' if es.get("interpretation") else "")),
        _section("三、與現行標準治療及 NCCN / ESMO 指引比較",
                 f'<ul style="padding-left:20px;margin:6px 0;font-size:14px;">{_li(an.get("soc_comparison"))}</ul>'),
        _section("四、對台灣臨床實務之意涵",
                 f'<ul style="padding-left:20px;margin:6px 0;font-size:14px;">{_li(an.get("taiwan_implications"))}</ul>'
                 '<div style="font-size:12px;color:#92400e;background:#fffbeb;border-radius:8px;padding:6px 10px;">'
                 'TFDA 核准與健保給付狀態以衛福部食藥署及健保署最新公告為準。</div>'),
        _section("五、相關進行中試驗與未來方向",
                 f'<ul style="padding-left:20px;margin:6px 0;font-size:14px;">{_li(an.get("ongoing_trials"))}</ul>'),
        '<div style="margin-top:14px;font-size:13px;">',
        (f'<a href="{E(src_link)}" style="display:inline-block;background:#0f766e;color:#fff;text-decoration:none;'
         f'padding:8px 14px;border-radius:8px;margin:0 6px 6px 0;">閱讀原始論文{(" (DOI: " + E(doi) + ")") if doi else ""}</a>' if src_link else ""),
        (f'<a href="{E(pm_link)}" style="display:inline-block;border:1px solid #0f766e;color:#0f766e;text-decoration:none;'
         f'padding:7px 14px;border-radius:8px;margin:0 6px 6px 0;">PubMed PMID {E(pm["pmid"])}</a>' if pm_link else ""),
        '</div>',
        f'<div style="font-size:11px;color:#94a3b8;margin-top:6px;">分析依據：{E(an.get("limitations_note"))}</div>',
        '</div>',
    ]
    return "\n".join(body)


def render_issue_html(issue: dict) -> str:
    themes = "".join(
        f'<span style="display:inline-block;background:#ccfbf1;color:#115e59;border-radius:999px;padding:3px 10px;'
        f'font-size:12px;margin:0 6px 6px 0;">{E(t)}</span>' for t in issue["editorial"].get("themes", []))
    toc = "".join(
        f'<li style="margin:0 0 6px 0;">{E(a["analysis"].get("title_zh"))}</li>' for a in issue["articles"])
    articles = "\n".join(render_article_html(i + 1, a) for i, a in enumerate(issue["articles"]))
    return f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>腫瘤臨床深度週報 第 {issue['number']} 期｜{E(issue['editorial'].get('issue_title'))}</title></head>
<body style="margin:0;background:#f1f5f9;font-family:-apple-system,'PingFang TC','Noto Sans TC','Microsoft JhengHei',sans-serif;color:#1e293b;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;"><tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:680px;background:#ffffff;border-radius:14px;overflow:hidden;">
<tr><td style="background:linear-gradient(135deg,#0f766e,#1d4ed8);background-color:#0f766e;color:#fff;padding:26px 28px;">
  <div style="font-size:12px;letter-spacing:1px;opacity:.85;">ONCOLOGY WEEKLY DEEP DIVE｜第 {issue['number']} 期｜{E(issue['date'])}</div>
  <div style="font-size:24px;font-weight:700;margin-top:6px;line-height:1.4;">{E(issue['editorial'].get('issue_title'))}</div>
</td></tr>
<tr><td style="padding:24px 28px 8px 28px;font-size:15px;line-height:1.75;">
  <div style="margin-bottom:10px;">{themes}</div>
  <h3 style="font-size:15px;color:#0f766e;margin:0 0 6px 0;">主編導讀</h3>
  <p style="margin:0 0 14px 0;">{E(issue['editorial'].get('editor_note'))}</p>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:12px 16px;">
    <b style="font-size:13px;">本期收錄（{len(issue['articles'])} 篇）</b>
    <ol style="padding-left:20px;margin:8px 0 0 0;font-size:14px;">{toc}</ol>
  </div>
</td></tr>
<tr><td style="padding:16px 28px;font-size:15px;line-height:1.75;">
{articles}
</td></tr>
<tr><td style="padding:18px 28px 26px 28px;font-size:11px;line-height:1.6;color:#64748b;background:#f8fafc;">
  本週報由 AI 依據 PubMed 原始摘要與國際腫瘤醫學會公開資料彙整分析，僅供醫療專業人員學術交流參考，
  不構成任何個別病患之診斷或治療建議。數據請以原始論文為準；台灣核准與給付資訊請以食藥署、健保署最新公告為準。<br>
  線上版：<a href="{SITE_URL}/newsletter/{issue['date']}.html" style="color:#0f766e;">{SITE_URL}/newsletter/{issue['date']}.html</a>
</td></tr>
</table></td></tr></table></body></html>"""


def render_issue_md(issue: dict) -> str:
    ed = issue["editorial"]
    out = [f"# 腫瘤臨床深度週報 第 {issue['number']} 期｜{ed.get('issue_title','')}",
           f"*{issue['date']}*　" + "　".join(f"`{t}`" for t in ed.get("themes", [])), "",
           "## 主編導讀", "", ed.get("editor_note", ""), "", "**本期收錄**", ""]
    out += [f"{i+1}. {a['analysis'].get('title_zh','')}" for i, a in enumerate(issue["articles"])]
    for i, a in enumerate(issue["articles"]):
        an, post, pm = a["analysis"], a["post"], a.get("pubmed") or {}
        td, es = an.get("trial_design", {}), an.get("efficacy_safety", {})
        out += ["", "---", "", f"## STUDY {i+1}｜{an.get('title_zh','')}", "",
                f"*{post.get('original_title','')}* — {pm.get('journal') or post.get('source_name','')}　",
                f"{post.get('category','')}｜{an.get('study_type','')}｜IG 發佈日 {a['date']}", "",
                f"> **Bottom line：** {an.get('bottom_line','')}", "",
                "### 一、試驗設計與受試族群", "", "| 項目 | 內容 |", "|---|---|"]
        for k, v in [("研究設計", td.get("phase_design")), ("受試族群", td.get("population")),
                     ("試驗組", td.get("intervention")), ("對照組", td.get("comparator")),
                     ("主要指標", td.get("primary_endpoint"))]:
            if v:
                out.append(f"| {k} | {str(v).replace('|','/')} |")
        if td.get("key_criteria"):
            out += ["", "**關鍵收案條件：**"] + [f"- {x}" for x in td["key_criteria"]]
        out += ["", "### 二、療效與安全性數據", ""]
        if es.get("key_results"):
            out += ["| 指標 | 結果 |", "|---|---|"] + [
                f"| {r.get('endpoint','')} | {str(r.get('result','')).replace('|','/')} |" for r in es["key_results"]]
        if es.get("safety"):
            out += ["", "**安全性：**"] + [f"- {x}" for x in es["safety"]]
        if es.get("interpretation"):
            out += ["", "**數據解讀：**"] + [f"- {x}" for x in es["interpretation"]]
        out += ["", "### 三、與現行標準治療及 NCCN / ESMO 指引比較", ""] + [f"- {x}" for x in an.get("soc_comparison", [])]
        out += ["", "### 四、對台灣臨床實務之意涵", ""] + [f"- {x}" for x in an.get("taiwan_implications", [])]
        out += ["", "*TFDA 核准與健保給付狀態以衛福部食藥署及健保署最新公告為準。*"]
        out += ["", "### 五、相關進行中試驗與未來方向", ""] + [f"- {x}" for x in an.get("ongoing_trials", [])]
        links = []
        if post.get("source_url"):
            links.append(f"[閱讀原始論文]({post['source_url']})" + (f"（DOI: {a['doi']}）" if a.get("doi") else ""))
        if pm.get("pmid"):
            links.append(f"[PubMed PMID {pm['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{pm['pmid']}/)")
        out += ["", "　".join(links), "", f"<sub>分析依據：{an.get('limitations_note','')}</sub>"]
    out += ["", "---", "",
            "<sub>本週報由 AI 依據 PubMed 原始摘要與國際腫瘤醫學會公開資料彙整分析，僅供醫療專業人員學術交流參考，"
            "不構成任何個別病患之診斷或治療建議。數據請以原始論文為準；台灣核准與給付資訊請以食藥署、健保署最新公告為準。</sub>"]
    return "\n".join(out) + "\n"


def render_index(issues: list) -> str:
    rows = "".join(
        f'<a href="./{E(x["date"])}.html" class="block rounded-xl border border-slate-700 bg-slate-900 p-4 hover:border-teal-500 transition">'
        f'<div class="text-xs text-slate-400">第 {x["number"]} 期｜{E(x["date"])}｜{x["count"]} 篇</div>'
        f'<div class="font-bold mt-1">{E(x["title"])}</div>'
        f'<div class="text-xs text-teal-400 mt-2">HTML 版 → 　<span onclick="event.preventDefault();location.href=\'./{E(x["date"])}.md\'" class="underline">Markdown 版</span></div></a>'
        for x in sorted(issues, key=lambda r: r["date"], reverse=True))
    return f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>腫瘤臨床深度週報｜歷期目錄</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-[#0b0f19] text-slate-100 p-6" style="font-family:-apple-system,'PingFang TC',sans-serif;">
<div class="max-w-3xl mx-auto space-y-4">
<div class="flex items-center justify-between"><h1 class="text-2xl font-bold">📰 腫瘤臨床深度週報｜歷期目錄</h1>
<a href="../" class="text-xs text-teal-400 underline">← 回每日 IG 看板</a></div>
<p class="text-sm text-slate-400">每週日自動針對當週加入週報的 IG 貼文，產出深度臨床分析。</p>
{rows or '<p class="text-slate-400">尚無週報。</p>'}
</div></body></html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    dry = "--dry-run" in sys.argv
    today = datetime.datetime.now(TZ).strftime("%Y-%m-%d")
    picks_doc = load_json(PICKS_PATH, {"picks": []})
    pending = [p for p in picks_doc.get("picks", []) if not p.get("issue") and p.get("post")]
    pending.sort(key=lambda p: (p.get("date", ""), p.get("post_id", "")))

    print(f"📋 待收錄貼文：{len(pending)} 篇")
    for p in pending:
        print(f"   - {p.get('date')} {p.get('post_id')}｜{p['post'].get('original_title','')[:70]}")
    if not pending:
        print("ℹ️ 本週沒有加入週報的貼文，略過發刊。")
        return
    if dry:
        return
    if not (ANTHROPIC_API_KEY or GEMINI_API_KEY):
        print("❌ 未設定 ANTHROPIC_API_KEY / GEMINI_API_KEY，無法產生週報。")
        sys.exit(1)

    articles = []
    for p in pending:
        post = p["post"]
        doi = extract_doi(post)
        pm = fetch_pubmed_abstract(doi)
        print(f"🔬 分析：{post.get('original_title','')[:60]}（DOI {doi or '無'}｜PubMed {'有摘要' if pm.get('abstract') else '無摘要'}）")
        user = (
            f"撰稿日期：{today}\n\n"
            f"【PubMed 原始摘要】\n"
            + (json.dumps(pm, ensure_ascii=False, indent=2) if pm else "（查無 PubMed 摘要，請僅依據下方 IG 貼文內容，並於 limitations_note 註明）")
            + f"\n\n【本站 IG 貼文內容】\n{post_digest(post)}\n\n"
            "請呼叫工具輸出深度臨床分析。"
        )
        analysis = call_llm(ANALYSIS_SYSTEM, user, ANALYSIS_SCHEMA, "emit_clinical_analysis")
        articles.append({"date": p.get("date"), "post_id": p.get("post_id"), "doi": doi,
                         "pubmed": {k: v for k, v in pm.items() if k != "abstract"}, "post": post,
                         "analysis": analysis})

    brief = [{"title": a["analysis"].get("title_zh"), "study_type": a["analysis"].get("study_type"),
              "bottom_line": a["analysis"].get("bottom_line"), "category": a["post"].get("category")}
             for a in articles]
    editorial = call_llm(EDITORIAL_SYSTEM,
                         f"本期日期：{today}\n本期收錄：\n{json.dumps(brief, ensure_ascii=False, indent=2)}\n\n請呼叫工具輸出本期導讀。",
                         EDITORIAL_SCHEMA, "emit_editorial")

    issues = load_json(ISSUES_PATH, {"issues": []})
    existing = [x for x in issues["issues"] if x["date"] != today]
    number = next((x["number"] for x in issues["issues"] if x["date"] == today), len(existing) + 1)
    issue = {"number": number, "date": today, "editorial": editorial, "articles": articles}

    os.makedirs(NL_DIR, exist_ok=True)
    with open(os.path.join(NL_DIR, f"{today}.html"), "w", encoding="utf-8") as f:
        f.write(render_issue_html(issue))
    with open(os.path.join(NL_DIR, f"{today}.md"), "w", encoding="utf-8") as f:
        f.write(render_issue_md(issue))
    save_json(os.path.join(NL_DIR, f"{today}.json"), issue)

    existing.append({"number": number, "date": today, "title": editorial.get("issue_title", ""),
                     "count": len(articles)})
    issues["issues"] = sorted(existing, key=lambda r: r["date"])
    save_json(ISSUES_PATH, issues)
    with open(os.path.join(NL_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_index(issues["issues"]))

    keys = {(p.get("date"), p.get("post_id")) for p in pending}
    for p in picks_doc["picks"]:
        if (p.get("date"), p.get("post_id")) in keys:
            p["issue"] = today
    save_json(PICKS_PATH, picks_doc)
    print(f"✅ 第 {number} 期週報完成：docs/newsletter/{today}.html / .md（{len(articles)} 篇）")


if __name__ == "__main__":
    main()
