#!/usr/bin/env python3
"""
每日國際權威醫藥網站（NCI / ScienceDaily / Medscape）與六大國際腫瘤醫學會
（ASCO、ESMO、AACR、WCLC、SITC、SABCS）最新研究自動抓取與確切文獻驗證腳本。
"""
import datetime
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) OncologyCurator/2.0"}
DOI_RE = re.compile(r'10\.\d{4,9}/[^\s"<>&\']+')

# 1. 國際醫藥新聞與醫學會議外電 RSS 來源
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
        "name": "Medscape Oncology",
        "url": "https://www.medscape.com/cx/rssfeeds/2700.xml"
    },
    {
        "name": "Oncology Congress News (ASCO / ESMO / AACR / WCLC / SITC / SABCS)",
        "url": "https://news.google.com/rss/search?q=(ASCO+OR+ESMO+OR+AACR+OR+WCLC+OR+SITC+OR+SABCS)+(oncology+OR+cancer+OR+phase+3+OR+clinical+trial)&hl=en-US&gl=US&ceid=US:en"
    }
]

# 2. 六大國際腫瘤醫學會（ASCO, ESMO, AACR, WCLC, SITC, SABCS）與官方旗艦期刊 PubMed 檢索設定
CONGRESS_PUBMED_SOURCES = [
    {
        "congress": "ASCO (美國臨床腫瘤學會) / JCO",
        "query": '("J Clin Oncol"[Journal] OR "ASCO"[Title/Abstract]) AND (clinical trial[Title/Abstract] OR phase[Title/Abstract] OR survival[Title/Abstract])'
    },
    {
        "congress": "ESMO (歐洲腫瘤內科學會) / Annals of Oncology",
        "query": '("Ann Oncol"[Journal] OR "ESMO Open"[Journal] OR "ESMO"[Title/Abstract]) AND (trial[Title/Abstract] OR phase[Title/Abstract] OR immunotherapy[Title/Abstract])'
    },
    {
        "congress": "AACR (美國癌症研究協會) / Cancer Discovery",
        "query": '("Cancer Discov"[Journal] OR "Clin Cancer Res"[Journal] OR "AACR"[Title/Abstract]) AND (cancer[Title/Abstract] OR tumor[Title/Abstract])'
    },
    {
        "congress": "WCLC (世界肺癌大會 / IASLC) / JTO",
        "query": '("J Thorac Oncol"[Journal] OR "WCLC"[Title/Abstract] OR "IASLC"[Title/Abstract]) AND (lung cancer[Title/Abstract] OR NSCLC[Title/Abstract] OR SCLC[Title/Abstract])'
    },
    {
        "congress": "SITC (癌症免疫治療學會) / JITC",
        "query": '("J Immunother Cancer"[Journal] OR "SITC"[Title/Abstract]) AND (immunotherapy[Title/Abstract] OR T cell[Title/Abstract] OR checkpoint[Title/Abstract])'
    },
    {
        "congress": "SABCS (聖安東尼奧乳癌研討會)",
        "query": '("SABCS"[Title/Abstract] OR "San Antonio Breast Cancer"[Title/Abstract] OR ("breast cancer"[Title] AND ("Clin Cancer Res"[Journal] OR "J Clin Oncol"[Journal] OR "Ann Oncol"[Journal])))'
    }
]


def _clean_html(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _http_get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


def fetch_congress_pubmed_articles(max_per_congress: int = 2) -> List[Dict[str, str]]:
    """
    透過 NCBI PubMed E-Utilities 官方 API，直接抓取六大醫學會議
    （ASCO, ESMO, AACR, WCLC, SITC, SABCS）及旗艦期刊之最新研究（含完整摘要與確切 DOI）。
    """
    results: List[Dict[str, str]] = []
    seen_pmids = set()

    for item in CONGRESS_PUBMED_SOURCES:
        congress_label = item["congress"]
        query = item["query"]
        try:
            search_url = (
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
                + urllib.parse.urlencode({
                    "db": "pubmed",
                    "term": query,
                    "sort": "date",
                    "retmax": max_per_congress,
                    "retmode": "json"
                })
            )
            search_data = json.loads(_http_get(search_url, timeout=15))
            id_list = [
                pid for pid in (search_data.get("esearchresult", {}).get("idlist") or [])
                if pid not in seen_pmids
            ]
            if not id_list:
                continue

            fetch_url = (
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
                + urllib.parse.urlencode({
                    "db": "pubmed",
                    "id": ",".join(id_list),
                    "retmode": "xml"
                })
            )
            xml_text = _http_get(fetch_url, timeout=20)
            root = ET.fromstring(xml_text)

            for art in root.findall(".//PubmedArticle"):
                pmid = (art.findtext(".//PMID") or "").strip()
                if not pmid or pmid in seen_pmids:
                    continue
                seen_pmids.add(pmid)

                title = _clean_html(art.findtext(".//ArticleTitle") or "")
                journal = _clean_html(
                    art.findtext(".//Journal/Title")
                    or art.findtext(".//Journal/ISOAbbreviation")
                    or ""
                )
                year = (
                    art.findtext(".//JournalIssue/PubDate/Year")
                    or art.findtext(".//ArticleDate/Year")
                    or str(datetime.datetime.now().year)
                )

                # 擷取完整結構化摘要 (Background / Methods / Results / Conclusions)
                abs_parts = []
                for ab in art.findall(".//AbstractText"):
                    label = ab.attrib.get("Label", "")
                    txt = _clean_html("".join(ab.itertext()))
                    if txt:
                        abs_parts.append(f"{label}: {txt}" if label else txt)
                abstract_full = " ".join(abs_parts)

                # 擷取作者名單
                authors = []
                for au in art.findall(".//AuthorList/Author")[:6]:
                    last = (au.findtext("LastName") or "").strip()
                    init = (au.findtext("Initials") or "").strip()
                    if last:
                        authors.append(f"{last} {init}".strip())
                total_authors = len(art.findall(".//AuthorList/Author"))
                author_str = ", ".join(authors) + (", et al" if total_authors > 6 else "")
                first_author = authors[0].split(" ")[0] if authors else ""

                # 擷取確切 DOI
                doi = ""
                for aid in art.findall(".//ArticleIdList/ArticleId"):
                    if aid.attrib.get("IdType") == "doi" and (aid.text or "").strip():
                        doi = aid.text.strip()
                        break

                if not title or not abstract_full:
                    continue

                source_url = f"https://doi.org/{doi}" if doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                verified_ref = (
                    f"{author_str}. {title} {journal} ({congress_label}). {year}. {source_url}"
                ).replace("..", ".")
                short_author = f"{first_author} et al. " if first_author else ""
                footer_citation = f"資料來源：{short_author}{congress_label.split(' ')[0]} / {journal} ({year})"

                results.append({
                    "source_name": f"{congress_label}",
                    "congress_tag": congress_label.split(" ")[0],
                    "title": title,
                    "url": source_url,
                    "summary": abstract_full[:500],
                    "page_excerpt": abstract_full[:2800],
                    "published_at": year,
                    "doi": doi,
                    "verified_reference": verified_ref,
                    "footer_citation": footer_citation[:62]
                })
        except Exception as exc:
            print(f"[WARN] 無法讀取醫學會議來源 {congress_label}: {exc}")

    return results


def fetch_latest_rss_articles(max_per_source: int = 4, include_congresses: bool = True) -> List[Dict[str, str]]:
    """同時從六大國際腫瘤醫學會（ASCO/ESMO/AACR/WCLC/SITC/SABCS）與國際醫藥網站抓取最新癌症研究"""
    articles: List[Dict[str, str]] = []

    if include_congresses:
        congress_articles = fetch_congress_pubmed_articles(max_per_congress=2)
        print(f"已從 ASCO / ESMO / AACR / WCLC / SITC / SABCS 抓取 {len(congress_articles)} 則醫學會議與旗艦期刊研究")
        articles.extend(congress_articles)

    for src in RSS_SOURCES:
        try:
            req = urllib.request.Request(src["url"], headers=UA)
            with urllib.request.urlopen(req, timeout=15) as response:
                xml_data = response.read()
            root = ET.fromstring(xml_data)
            items = root.findall(".//item")[:max_per_source]
            for item in items:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                desc = _clean_html(item.findtext("description") or "")
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
    """若文章已具備 PubMed/會議驗證出處則直接保留；否則進入原文頁擷取期刊 DOI 並以 Crossref 驗證"""
    article = dict(article)
    if article.get("verified_reference") and article.get("page_excerpt"):
        return article

    article.setdefault("verified_reference", "")
    article.setdefault("doi", "")
    article.setdefault("footer_citation", f"資料來源：{article.get('source_name', '')}")
    try:
        page = _http_get(article["url"])
    except Exception as exc:
        print(f"[WARN] 無法讀取原文頁 {article['url']}: {exc}")
        return article

    paragraphs = [_clean_html(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", page, flags=re.S)]
    body = " ".join(p for p in paragraphs if len(p) > 60)
    article["page_excerpt"] = body[:2500]

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
    print(f"已抓取 {len(fetched)} 篇候選癌症文章（含六大醫學會議）並儲存至 {out_file}")
