"""어떤 자격 증명도 필요 없는 기본 대상. 발행 직전 상태 그대로 파일로 떨궈줍니다."""
from __future__ import annotations

import json
from typing import Any

from ..compose import LIMITS, compose_text
from .base import Adapter


class FileAdapter(Adapter):
    name = "file"

    def configured(self) -> bool:
        return True

    def send(self, post: dict, assets: dict, ctx: dict) -> dict[str, Any]:
        base = ctx["paths"].queue / f"{post['platform']}-v{post['variant']}"
        text = compose_text(post, limit=LIMITS.get(post["platform"], 0))

        lines = []
        if post.get("title"):
            lines.append(f"[제목] {post['title']}")
        lines.append(text)
        if post.get("firstComment"):
            lines.append(f"\n[첫 댓글] {post['firstComment']}")

        txt_file = base.with_suffix(".txt")
        txt_file.write_text("\n".join(lines), encoding="utf-8")
        base.with_suffix(".json").write_text(
            json.dumps({"post": post, "text": text, "assets": assets}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"ok": True, "target": self.name, "output": str(txt_file)}
