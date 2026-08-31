"""Postiz — 한 번 연결해두면 X/인스타/스레드/유튜브 등 여러 채널에 같은 API 로 발행합니다.

필요한 값 (.env)
  POSTIZ_API_KEY       Postiz 설정 > Public API 에서 발급한 키.
                       ※ 채널 연결용 CLIENT_ID / CLIENT_SECRET 과는 다른 값입니다.
                          그건 셀프호스팅 Postiz 서버의 환경변수로 들어갑니다.
  POSTIZ_API_URL       기본 https://api.postiz.com (셀프호스팅이면 그 주소)
  POSTIZ_INTEGRATIONS  (선택) {"instagram":"<채널 id>"} 형태의 JSON.
                       비워두면 연결된 채널 목록에서 자동으로 찾습니다.

채널 목록과 id 는 `python -m sns_autopilot channels` 로 확인할 수 있습니다.
Public API 는 시간당 30요청 제한이 있습니다 (발행 1건당 업로드 포함 2요청).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from ..compose import LIMITS, compose_text
from .base import Adapter

#: 우리 플랫폼 키 → Postiz 의 provider identifier 후보들.
#: 실제 값은 채널 목록의 identifier 를 그대로 쓰고, 이 표는 자동 매칭에만 씁니다.
PROVIDER_ALIASES: dict[str, tuple[str, ...]] = {
    "x": ("x", "twitter"),
    "instagram": ("instagram", "instagram-standalone"),
    "threads": ("threads",),
    "youtube": ("youtube",),
    "tiktok": ("tiktok",),
    "linkedin": ("linkedin", "linkedin-page"),
    "facebook": ("facebook",),
}


class PostizAdapter(Adapter):
    name = "postiz"
    required_env = ("POSTIZ_API_KEY",)

    def __init__(self) -> None:
        self._cache: list[dict] | None = None

    @property
    def api(self) -> str:
        return (os.environ.get("POSTIZ_API_URL") or "https://api.postiz.com").rstrip("/")

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": os.environ["POSTIZ_API_KEY"]}

    def integrations(self, refresh: bool = False) -> list[dict]:
        """연결된 채널 목록. id, name, identifier(provider), disabled 등이 들어옵니다."""
        if self._cache is None or refresh:
            response = requests.get(f"{self.api}/public/v1/integrations", headers=self.headers, timeout=30)
            if not response.ok:
                raise RuntimeError(f"postiz 채널 목록 조회 실패 {response.status_code}: {response.text[:200]}")
            payload = response.json()
            self._cache = payload if isinstance(payload, list) else payload.get("integrations", [])
        return self._cache

    def _resolve(self, platform: str) -> tuple[str, str]:
        """플랫폼 이름 → (채널 id, provider identifier)."""
        channels = self.integrations()
        mapping = json.loads(os.environ.get("POSTIZ_INTEGRATIONS") or "{}")

        if platform in mapping:
            wanted = mapping[platform]
            found = next((c for c in channels if c.get("id") == wanted), None)
            # 목록에 없어도 사용자가 지정한 id 는 존중합니다 (권한 문제로 안 보일 수 있음).
            return wanted, (found or {}).get("identifier") or platform

        aliases = PROVIDER_ALIASES.get(platform, (platform,))
        found = next(
            (c for c in channels if c.get("identifier") in aliases and not c.get("disabled")), None
        )
        if not found:
            connected = ", ".join(f'{c.get("identifier")}({c.get("name")})' for c in channels) or "없음"
            raise RuntimeError(
                f"Postiz 에 '{platform}' 채널이 연결돼 있지 않습니다.\n"
                f"  연결된 채널: {connected}\n"
                "  python -m sns_autopilot channels 로 확인하거나 Postiz 에서 채널을 먼저 연결하세요."
            )
        return found["id"], found["identifier"]

    def _upload(self, file: Path) -> dict:
        with file.open("rb") as handle:
            response = requests.post(
                f"{self.api}/public/v1/upload", headers=self.headers,
                files={"file": (file.name, handle)}, timeout=180,
            )
        if not response.ok:
            raise RuntimeError(f"postiz 업로드 실패 {response.status_code}: {response.text[:200]}")
        return response.json()

    def send(self, post: dict, assets: dict, ctx: dict) -> dict[str, Any]:
        platform = post["platform"]
        integration_id, provider = self._resolve(platform)

        media = assets.get("video") or assets.get("image")
        uploaded = self._upload(Path(media)) if media and Path(media).exists() else None

        value: dict[str, Any] = {"content": compose_text(post, limit=LIMITS.get(platform, 0))}
        if uploaded:
            value["image"] = [{"id": uploaded.get("id"), "path": uploaded.get("path")}]

        # __type 이 없으면 일부 채널(인스타그램 등)에서 400 이 납니다.
        settings: dict[str, Any] = {"__type": provider}
        if post.get("title"):
            settings["title"] = post["title"]

        schedule_at = ctx.get("schedule_at")
        body = {
            "type": "schedule" if schedule_at else "now",
            "date": schedule_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "shortLink": False,
            "posts": [{"integration": {"id": integration_id}, "value": [value], "settings": settings}],
        }

        response = requests.post(
            f"{self.api}/public/v1/posts",
            headers={**self.headers, "content-type": "application/json"},
            json=body, timeout=60,
        )
        if not response.ok:
            raise RuntimeError(f"postiz 발행 실패 {response.status_code}: {response.text[:300]}")
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return {"ok": True, "target": self.name, "provider": provider, "response": payload}
