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
