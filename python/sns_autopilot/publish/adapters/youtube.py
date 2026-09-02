"""YouTube Shorts — refresh token 으로 access token 을 받아 resumable 업로드.

필요한 값: YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN
(세로 영상 + 3분 이하 + 제목이나 설명에 #Shorts 가 있으면 쇼츠로 잡힙니다.)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests

from ..compose import LIMITS, compose_text
from .base import Adapter


def _access_token() -> str:
    response = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }, timeout=60)
    if not response.ok:
        raise RuntimeError(f"YouTube 토큰 발급 실패: {response.text[:200]}")
    return response.json()["access_token"]


class YouTubeAdapter(Adapter):
    name = "youtube"
    required_env = ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")

    def send(self, post: dict, assets: dict, ctx: dict) -> dict[str, Any]:
        video = assets.get("video")
        if not video or not Path(video).exists():
            raise RuntimeError("유튜브에 올릴 동영상이 없습니다.")
        token = _access_token()

        description = compose_text(post, limit=LIMITS["youtube"])
        if "#Shorts" not in description:
            description = f"{description}\n\n#Shorts"
        metadata = {
            "snippet": {
                "title": (post.get("title") or post["text"].split("\n")[0])[:95],
                "description": description,
                "tags": [t.lstrip("#") for t in (post.get("hashtags") or [])][:15],
                "categoryId": "19",             # Travel & Events
            },
            "status": {
                "privacyStatus": os.environ.get("YT_PRIVACY", "public"),
                "selfDeclaredMadeForKids": False,
            },
        }

        body = Path(video).read_bytes()
        start = requests.post(
            "https://www.googleapis.com/upload/youtube/v3/videos",
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Upload-Content-Length": str(len(body)),
                "X-Upload-Content-Type": "video/mp4",
            },
            json=metadata, timeout=60,
        )
        if not start.ok:
            raise RuntimeError(f"YouTube 업로드 세션 실패 {start.status_code}: {start.text[:300]}")

        done = requests.put(
            start.headers["location"], data=body,
            headers={"content-type": "video/mp4"}, timeout=600,
        )
        if not done.ok:
            raise RuntimeError(f"YouTube 업로드 실패 {done.status_code}: {done.text[:300]}")
        video_id = done.json().get("id")
        return {"ok": True, "target": self.name, "id": video_id,
                "url": f"https://youtube.com/shorts/{video_id}"}
