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
