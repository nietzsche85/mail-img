"""n8n / Make / Zapier / Slack 등으로 통째로 넘깁니다."""
from __future__ import annotations

import os
from typing import Any

import requests

from ..compose import LIMITS, compose_text
from .base import Adapter


class WebhookAdapter(Adapter):
    name = "webhook"
    required_env = ("WEBHOOK_URL",)

    def send(self, post: dict, assets: dict, ctx: dict) -> dict[str, Any]:
        payload = {
            "runId": ctx["run_id"],
            "platform": post["platform"],
            "variant": post["variant"],
            "title": post.get("title") or None,
            "text": compose_text(post, limit=LIMITS.get(post["platform"], 0)),
            "hashtags": post.get("hashtags", []),
            "firstComment": post.get("firstComment") or None,
            "assets": assets,
        }
        response = requests.post(os.environ["WEBHOOK_URL"], json=payload, timeout=30)
        if not response.ok:
            raise RuntimeError(f"webhook {response.status_code}: {response.text[:200]}")
        return {"ok": True, "target": self.name, "status": response.status_code}
