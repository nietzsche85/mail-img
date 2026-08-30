"""Threads (Meta) — 컨테이너 생성 후 publish 하는 2단계 방식.

필요한 값: THREADS_USER_ID / THREADS_ACCESS_TOKEN
미디어는 "공개 URL" 이어야 해서 PUBLIC_MEDIA_BASE_URL 이 필요합니다.
"""
from __future__ import annotations

import os
import time
from typing import Any

import requests

from ..compose import LIMITS, compose_text, public_url
from .base import Adapter

BASE = "https://graph.threads.net/v1.0"


def _post(url: str, params: dict) -> dict:
    response = requests.post(url, data=params, timeout=60)
    if not response.ok:
        raise RuntimeError(f"Threads {response.status_code}: {response.text[:300]}")
    return response.json()


class ThreadsAdapter(Adapter):
    name = "threads"
    required_env = ("THREADS_USER_ID", "THREADS_ACCESS_TOKEN")

    def send(self, post: dict, assets: dict, ctx: dict) -> dict[str, Any]:
        uid = os.environ["THREADS_USER_ID"]
        token = os.environ["THREADS_ACCESS_TOKEN"]

        video_url = public_url(assets["video"]) if assets.get("video") else None
        image_url = public_url(assets["image"]) if assets.get("image") else None

        params = {"access_token": token, "text": compose_text(post, limit=LIMITS["threads"])}
        if video_url:
            params |= {"media_type": "VIDEO", "video_url": video_url}
        elif image_url:
            params |= {"media_type": "IMAGE", "image_url": image_url}
        else:
            params["media_type"] = "TEXT"

        container = _post(f"{BASE}/{uid}/threads", params)
        if params["media_type"] != "TEXT":
            time.sleep(20)   # 미디어 처리 대기

        published = _post(f"{BASE}/{uid}/threads_publish", {
            "access_token": token, "creation_id": container["id"],
        })
        return {"ok": True, "target": self.name, "id": published.get("id")}
