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
