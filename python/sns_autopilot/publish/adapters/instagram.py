"""Instagram — 릴스(동영상) 또는 피드 이미지.

필요한 값: IG_USER_ID / IG_ACCESS_TOKEN (프로페셔널 계정 + 페이지 연결 필요)
미디어는 공개 URL 이어야 하므로 PUBLIC_MEDIA_BASE_URL 을 반드시 설정하세요.
"""
from __future__ import annotations

import os
import time
from typing import Any

import requests

from ..compose import LIMITS, compose_text, public_url
from .base import Adapter

BASE = "https://graph.facebook.com/v21.0"


def _request(method: str, url: str, params: dict | None = None) -> dict:
    response = (
        requests.post(url, data=params, timeout=60) if method == "POST"
        else requests.get(url, params=params, timeout=60)
    )
    if not response.ok:
        raise RuntimeError(f"Instagram {response.status_code}: {response.text[:300]}")
    return response.json()


class InstagramAdapter(Adapter):
    name = "instagram"
    required_env = ("IG_USER_ID", "IG_ACCESS_TOKEN")

    def send(self, post: dict, assets: dict, ctx: dict) -> dict[str, Any]:
        uid = os.environ["IG_USER_ID"]
        token = os.environ["IG_ACCESS_TOKEN"]

        video_url = public_url(assets["video"]) if assets.get("video") else None
        image_url = public_url(assets["image"]) if assets.get("image") else None
        if not video_url and not image_url:
            raise RuntimeError("인스타그램은 공개 URL 이 필요합니다. PUBLIC_MEDIA_BASE_URL 을 설정하세요.")

        params = {"access_token": token, "caption": compose_text(post, limit=LIMITS["instagram"])}
        if video_url:
            params |= {"media_type": "REELS", "video_url": video_url, "share_to_feed": "true"}
        else:
            params["image_url"] = image_url

        container = _request("POST", f"{BASE}/{uid}/media", params)

        # 동영상은 서버에서 인코딩이 끝나야 발행할 수 있습니다.
        if video_url:
            for _ in range(30):
                status = _request("GET", f"{BASE}/{container['id']}",
                                  {"fields": "status_code", "access_token": token})
                if status.get("status_code") == "FINISHED":
                    break
                if status.get("status_code") == "ERROR":
                    raise RuntimeError("인스타그램 동영상 처리 실패")
                time.sleep(10)

        published = _request("POST", f"{BASE}/{uid}/media_publish", {
            "access_token": token, "creation_id": container["id"],
        })
        return {"ok": True, "target": self.name, "id": published.get("id")}
