"""X(트위터) — OAuth 1.0a User Context.

필요한 값: X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_SECRET
(개발자 포털에서 앱 권한을 Read and Write 로 올린 뒤 토큰을 재발급해야 합니다.)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlsplit

import requests

from ..compose import LIMITS, compose_text
from .base import Adapter

CHUNK = 5 * 1024 * 1024


# .env 는 import 이후에 읽히므로 호출 시점에 꺼냅니다.
def _upload_host() -> str:
    return os.environ.get("X_UPLOAD_HOST", "https://upload.twitter.com/1.1/media/upload.json")


def _api_host() -> str:
    return os.environ.get("X_API_HOST", "https://api.x.com")


def _enc(value) -> str:
    return quote(str(value), safe="-._~")


def _auth_header(method: str, url: str) -> str:
    """쿼리스트링까지 포함해 서명합니다. multipart/JSON 바디는 서명 대상이 아닙니다."""
    parts = urlsplit(url)
    oauth = {
        "oauth_consumer_key": os.environ["X_API_KEY"],
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": os.environ["X_ACCESS_TOKEN"],
        "oauth_version": "1.0",
    }
    params = {**oauth, **dict(parse_qsl(parts.query))}
    param_string = "&".join(f"{_enc(k)}={_enc(params[k])}" for k in sorted(params))
    base_url = f"{parts.scheme}://{parts.netloc}{parts.path}"
    base = f"{method.upper()}&{_enc(base_url)}&{_enc(param_string)}"
    key = f'{_enc(os.environ["X_API_SECRET"])}&{_enc(os.environ["X_ACCESS_SECRET"])}'
    oauth["oauth_signature"] = base64.b64encode(
        hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
    ).decode()
    return "OAuth " + ", ".join(f'{_enc(k)}="{_enc(oauth[k])}"' for k in sorted(oauth))


def _call(method: str, url: str, *, files=None, json_body=None) -> dict:
    response = requests.request(
        method, url, headers={"Authorization": _auth_header(method, url)},
        files=files, json=json_body, timeout=180,
    )
    if not response.ok:
        raise RuntimeError(f"X {method} {urlsplit(url).path} {response.status_code}: {response.text[:300]}")
    return response.json() if response.text else {}


class XAdapter(Adapter):
    name = "x"
    required_env = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")

    def _upload_video(self, file: Path) -> str:
        """INIT → APPEND(5MB 청크) → FINALIZE → STATUS 폴링."""
        data = file.read_bytes()
        init = _call(
            "POST",
            f"{_upload_host()}?command=INIT&total_bytes={len(data)}"
            f"&media_type=video%2Fmp4&media_category=tweet_video",
        )
        media_id = init["media_id_string"]

        for index, offset in enumerate(range(0, len(data), CHUNK)):
            _call(
                "POST",
                f"{_upload_host()}?command=APPEND&media_id={media_id}&segment_index={index}",
                files={"media": ("chunk", data[offset:offset + CHUNK])},
            )
        _call("POST", f"{_upload_host()}?command=FINALIZE&media_id={media_id}")

        for _ in range(40):
            status = _call("GET", f"{_upload_host()}?command=STATUS&media_id={media_id}")
            info = status.get("processing_info")
            if not info or info.get("state") == "succeeded":
                return media_id
            if info.get("state") == "failed":
                raise RuntimeError(f"X 동영상 처리 실패: {info.get('error', {})}")
            time.sleep(info.get("check_after_secs", 3))
        raise RuntimeError("X 동영상 처리 시간 초과")

    def _upload_image(self, file: Path) -> str:
        result = _call("POST", _upload_host(), files={"media": (file.name, file.read_bytes())})
        return result["media_id_string"]

    def send(self, post: dict, assets: dict, ctx: dict) -> dict[str, Any]:
        media_id = None
        video, image = assets.get("video"), assets.get("image")
        if video and Path(video).exists():
            media_id = self._upload_video(Path(video))
        elif image and Path(image).exists():
            media_id = self._upload_image(Path(image))

        payload: dict[str, Any] = {"text": compose_text(post, limit=LIMITS["x"])}
        if media_id:
            payload["media"] = {"media_ids": [media_id]}
        tweet = _call("POST", f"{_api_host()}/2/tweets", json_body=payload)
        tweet_id = (tweet.get("data") or {}).get("id")

        if post.get("firstComment"):
            _call("POST", f"{_api_host()}/2/tweets", json_body={
                "text": post["firstComment"][: LIMITS["x"]],
                "reply": {"in_reply_to_tweet_id": tweet_id},
            })
        return {"ok": True, "target": self.name, "id": tweet_id, "url": f"https://x.com/i/status/{tweet_id}"}
