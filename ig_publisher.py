#!/usr/bin/env python3
"""
Instagram Business Graph API Publisher (Carousel & Single Image Support)
用於將篩選後的癌症知識多圖輪播（Carousel）一鍵發布至 Instagram Business 帳號。
"""
import json
import os
import urllib.parse
import urllib.request
from typing import List, Dict, Any

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def load_config() -> Dict[str, str]:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "ig_user_id": os.environ.get("IG_USER_ID", ""),
        "access_token": os.environ.get("IG_ACCESS_TOKEN", ""),
        "image_host_base_url": os.environ.get("IMAGE_HOST_BASE_URL", "")
    }


def save_config(ig_user_id: str, access_token: str, image_host_base_url: str = "") -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "ig_user_id": ig_user_id.strip(),
            "access_token": access_token.strip(),
            "image_host_base_url": image_host_base_url.strip()
        }, f, ensure_ascii=False, indent=2)


def _graph_post(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{GRAPH_API_BASE}/{endpoint}"
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def publish_carousel_to_instagram(
    ig_user_id: str,
    access_token: str,
    image_urls: List[str],
    caption: str
) -> Dict[str, Any]:
    """
    透過 Meta Instagram Graph API 發布多圖輪播貼文 (Carousel)：
    Step 1: 為每一張輪播圖建立子媒體容器 (is_carousel_item=true)
    Step 2: 建立 CAROUSEL 主容器，綁定 children IDs 與貼文文案 (caption)
    Step 3: 呼叫 media_publish 正式發布至 Instagram
    """
    if not ig_user_id or not access_token:
        raise ValueError("請先設定 Instagram Business 帳號 ID (ig_user_id) 與 Graph API Access Token")
    if len(image_urls) < 2 or len(image_urls) > 10:
        raise ValueError("Instagram 多圖輪播需包含 2 至 10 張圖片 URL")

    child_creation_ids = []
    for img_url in image_urls:
        res = _graph_post(f"{ig_user_id}/media", {
            "image_url": img_url,
            "is_carousel_item": "true",
            "access_token": access_token
        })
        child_creation_ids.append(res["id"])

    carousel_res = _graph_post(f"{ig_user_id}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(child_creation_ids),
        "caption": caption,
        "access_token": access_token
    })
    carousel_container_id = carousel_res["id"]

    publish_res = _graph_post(f"{ig_user_id}/media_publish", {
        "creation_id": carousel_container_id,
        "access_token": access_token
    })
    return {
        "status": "published",
        "ig_media_id": publish_res.get("id"),
        "children_ids": child_creation_ids,
        "carousel_container_id": carousel_container_id
    }
