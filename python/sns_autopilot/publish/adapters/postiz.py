"""Postiz — 한 번 연결해두면 28개 채널에 같은 API 로 예약·발행할 수 있습니다.

필요한 값
  POSTIZ_API_URL       기본 https://api.postiz.com (셀프호스팅이면 그 주소)
  POSTIZ_API_KEY       설정 > Public API 에서 발급
  POSTIZ_INTEGRATIONS  {"instagram":"<integration id>","x":"<id>"} 형태의 JSON
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from ..compose import LIMITS, compose_text
from .base import Adapter


class PostizAdapter(Adapter):
    name = "postiz"
    required_env = ("POSTIZ_API_KEY",)

    @property
    def api(self) -> str:
        return (os.environ.get("POSTIZ_API_URL") or "https://api.postiz.com").rstrip("/")

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": os.environ["POSTIZ_API_KEY"]}

    def _upload(self, file: Path) -> dict:
        with file.open("rb") as handle:
            response = requests.post(
                f"{self.api}/public/v1/upload",
                headers=self.headers,
                files={"file": (file.name, handle)},
                timeout=180,
            )
        if not response.ok:
            raise RuntimeError(f"postiz upload {response.status_code}: {response.text[:200]}")
        return response.json()

    def send(self, post: dict, assets: dict, ctx: dict) -> dict[str, Any]:
        integrations = json.loads(os.environ.get("POSTIZ_INTEGRATIONS") or "{}")
        integration_id = integrations.get(post["platform"])
        if not integration_id:
            raise RuntimeError(f'POSTIZ_INTEGRATIONS 에 "{post["platform"]}" 채널 id 가 없습니다.')

        media = assets.get("video") or assets.get("image")
        uploaded = self._upload(Path(media)) if media and Path(media).exists() else None

        schedule_at = ctx.get("schedule_at")
        value: dict[str, Any] = {"content": compose_text(post, limit=LIMITS.get(post["platform"], 0))}
        if uploaded:
            value["image"] = [{"id": uploaded.get("id"), "path": uploaded.get("path")}]

        body = {
            "type": "schedule" if schedule_at else "now",
            "date": schedule_at or datetime.now().astimezone().isoformat(),
            "shortLink": False,
            "posts": [{
                "integration": {"id": integration_id},
                "value": [value],
                "settings": {"title": post["title"]} if post.get("title") else {},
            }],
        }
        response = requests.post(
            f"{self.api}/public/v1/posts", headers={**self.headers, "content-type": "application/json"},
            json=body, timeout=60,
        )
        if not response.ok:
            raise RuntimeError(f"postiz posts {response.status_code}: {response.text[:300]}")
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return {"ok": True, "target": self.name, "response": payload}
