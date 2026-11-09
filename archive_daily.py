#!/usr/bin/env python3
"""
每日貼文歸檔 (Daily Archive)

每天 cloud_curate.py 產出新的 data/daily_posts.json 後執行，將當日 5 篇完整貼文
另存為 docs/data/archive/YYYY-MM-DD.json，並更新 docs/data/archive/index.json，
讓 GitHub Pages 看板可以瀏覽過去日期、讓週報腳本可以回溯。

用法：
  python3 archive_daily.py              # 歸檔今日 data/daily_posts.json
  python3 archive_daily.py --backfill   # 一次性從 git 歷史還原過去每天的 daily_posts.json
"""
import json
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_DIR = os.path.join(BASE_DIR, "docs", "data", "archive")
SRC = os.path.join(BASE_DIR, "data", "daily_posts.json")


def save_day(data: dict, overwrite: bool = True) -> str:
    date = (data or {}).get("date")
    if not date or not isinstance(data.get("posts"), list) or not data["posts"]:
        return ""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    path = os.path.join(ARCHIVE_DIR, f"{date}.json")
    if os.path.exists(path) and not overwrite:
        return ""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return date


def rebuild_index():
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    dates = sorted(
        (fn[:-5] for fn in os.listdir(ARCHIVE_DIR) if fn.endswith(".json") and fn != "index.json"),
        reverse=True,
    )
    with open(os.path.join(ARCHIVE_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"dates": dates}, f, ensure_ascii=False, indent=2)
    return dates


def backfill_from_git():
    """逐一讀取 git 歷史中每個版本的 data/daily_posts.json，每個日期保留最後一版。"""
    out = subprocess.run(
        ["git", "log", "--format=%H", "--", "data/daily_posts.json"],
        cwd=BASE_DIR, capture_output=True, text=True, check=True,
    ).stdout.split()
    restored = []
    # git log 由新到舊；同一日期只保留最新一版（第一次遇到者）
    for sha in out:
        try:
            raw = subprocess.run(
                ["git", "show", f"{sha}:data/daily_posts.json"],
                cwd=BASE_DIR, capture_output=True, text=True, check=True,
            ).stdout
            data = json.loads(raw)
        except Exception:
            continue
        d = save_day(data, overwrite=False)
        if d:
            restored.append(d)
    return restored


def main():
    if "--backfill" in sys.argv:
        restored = backfill_from_git()
        print(f"📚 已從 git 歷史還原 {len(restored)} 天：{', '.join(sorted(restored))}")
    if os.path.exists(SRC):
        with open(SRC, "r", encoding="utf-8") as f:
            d = save_day(json.load(f), overwrite=True)
        if d:
            print(f"🗂️ 已歸檔 {d} 的每日貼文 → docs/data/archive/{d}.json")
    dates = rebuild_index()
    print(f"📇 archive/index.json 共 {len(dates)} 天")


if __name__ == "__main__":
    main()
