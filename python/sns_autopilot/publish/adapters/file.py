"""어떤 자격 증명도 필요 없는 기본 대상.

발행 직전 상태를 그대로 파일로 떨궈줍니다. 채널 API 없이 손으로 올릴 때는
이 .txt 가 유일한 작업 지시서라, 붙여넣을 본문뿐 아니라 글자 수와
첨부할 파일 경로까지 같이 적어 둡니다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..compose import LABELS, LIMITS, compose_text
from .base import Adapter

#: 첨부 종류별 안내 문구
_ASSET_LABELS = {"video": "동영상", "image": "이미지", "gif": "GIF"}


class FileAdapter(Adapter):
    name = "file"

    def configured(self) -> bool:
        return True

    def send(self, post: dict, assets: dict, ctx: dict) -> dict[str, Any]:
        platform = post["platform"]
        base = ctx["paths"].queue / f"{platform}-v{post['variant']}"
        limit = LIMITS.get(platform, 0)
        text = compose_text(post, limit=limit)

        header = f"── {LABELS.get(platform, platform)} · 시안 {post['variant']} "
        counted = f"글자수 {len(text)}" + (f" / {limit}" if limit else "")

        lines = [header + "─" * max(0, 52 - len(header)), counted, ""]
        if post.get("title"):
            lines += [f"[제목] {post['title']}", ""]
        lines.append(text)
        if post.get("firstComment"):
            lines += ["", f"[첫 댓글] {post['firstComment']}"]

        attachments = [
            (_ASSET_LABELS.get(kind, kind), value)
            for kind, value in assets.items()
            if value and Path(value).exists()
        ]
        if attachments:
            lines += ["", "[첨부]"]
            width = max(len(label) for label, _ in attachments)
            lines += [f"  {label.ljust(width)}  {value}" for label, value in attachments]

        txt_file = base.with_suffix(".txt")
        txt_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        base.with_suffix(".json").write_text(
            json.dumps({"post": post, "text": text, "assets": assets}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"ok": True, "target": self.name, "output": str(txt_file)}
