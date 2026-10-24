#!/usr/bin/env python3
"""
每日國際權威醫藥網站（NCI / ScienceDaily / Medical News Today / Medscape）
癌症新知 RSS 自動抓取與篩選腳本。
"""
import html
import json
import os
import re
import datetime
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional

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


# ---------------------------------------------------------------------------
# 原文頁面「確切文獻來源」擷取：從新聞原文頁抓出期刊 DOI，並以 Crossref 官方資料庫
# 取得作者 / 題目 / 期刊 / 年份，避免 AI 自行編造參考文獻。
# ---------------------------------------------------------------------------
DOI_RE = re.compile(r'10\.\d{4,9}/[^\s"<>&\']+')
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) OncologyCurator/1.0"}


def _clean_html(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _http_get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


def crossref_lookup(doi: str) -> Optional[Dict[str, str]]:
    """以 Crossref 官方 API 驗證 DOI 並取得標準書目資料（DOI 不存在則回傳 None）"""
    try:
        raw = _http_get("https://api.crossref.org/works/" + urllib.parse.quote(doi), timeout=20)
        msg = json.loads(raw).get("message", {})
    except Exception:
        return None
    authors = msg.get("author", []) or []
    names = []
    for a in authors[:6]:
        family = a.get("family", "")
        given = a.get("given", "")
        initials = "".join(part[0] for part in re.split(r"[\s\-]+", given) if part)
        if family:
            names.append(f"{family} {initials}".strip())
    author_str = ", ".join(names) + (", et al" if len(authors) > 6 else "")
    title = " ".join(msg.get("title", []) or [])
    journal = _clean_html(" ".join(msg.get("container-title", []) or []))
    year = ""
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (msg.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            year = str(parts[0][0])
            break
    if not title:
        return None
    return {
        "doi": msg.get("DOI", doi),
        "first_author": names[0].split(" ")[0] if names else "",
        "authors": author_str,
        "title": _clean_html(title),
        "journal": journal,
        "year": year,
    }


def enrich_article_reference(article: Dict[str, str]) -> Dict[str, str]:
    """抓取新聞原文頁，擷取確切期刊出處（Journal Reference / DOI）與內文摘要"""
    article = dict(article)
    article["verified_reference"] = ""
    article["doi"] = ""
    article["footer_citation"] = f"資料來源：{article.get('source_name', '')}"
    try:
        page = _http_get(article["url"])
    except Exception as exc:
        print(f"[WARN] 無法讀取原文頁 {article['url']}: {exc}")
        return article

    # 內文摘錄（提供 AI 更完整的事實依據，避免只靠 RSS 短摘要）
    paragraphs = [_clean_html(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", page, flags=re.S)]
    body = " ".join(p for p in paragraphs if len(p) > 60)
    article["page_excerpt"] = body[:2500]

    # ScienceDaily 等頁面的 Journal Reference 區塊
    journal_ref_text = ""
    idx = page.find("Journal Reference")
    if idx >= 0:
        end = page.find("Cite This Page", idx)
        journal_ref_text = _clean_html(page[idx:end if end > 0 else idx + 1500])
        journal_ref_text = re.sub(r"^Journal Reference\s*:?\s*", "", journal_ref_text)
        journal_ref_text = re.sub(r"^\d+\.\s*", "", journal_ref_text)

    dois = []
    for d in DOI_RE.findall(journal_ref_text or page):
        d = d.rstrip(".,;)")
        if d not in dois:
            dois.append(d)

    # 只有單一明確 DOI 時才採用（多個 DOI 可能是頁面上的其他文獻）
    if len(dois) == 1:
        meta = crossref_lookup(dois[0])
        if meta:
            article["doi"] = meta["doi"]
            article["verified_reference"] = (
                f"{meta['authors']}. {meta['title']}. {meta['journal']}. {meta['year']}. "
                f"https://doi.org/{meta['doi']}"
            ).replace(" .", ".")
            short_author = f"{meta['first_author']} et al. " if meta["first_author"] else ""
            article["footer_citation"] = f"資料來源：{short_author}{meta['journal']} ({meta['year']})"
            return article

    if journal_ref_text:
        article["verified_reference"] = journal_ref_text
    return article


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
