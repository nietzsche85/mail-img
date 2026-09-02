"""카피의 card 필드로 SNS 규격별 홍보 이미지를 굽습니다."""
from __future__ import annotations

import base64
import html
import mimetypes
import re
from pathlib import Path

import requests

from .. import log
from ..config import resolve
from ..paths import RunPaths, relative
from ..render.html2png import RenderJob, korean_font_face, render_all

_EMPHASIS = re.compile(r"\*\*(.+?)\*\*")
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def _esc(value) -> str:
    return html.escape(str(value or ""), quote=False)


def _emphasize(value) -> str:
    return _EMPHASIS.sub(r"<em>\1</em>", _esc(value))


def _fill(template: str, variables: dict) -> str:
    return _PLACEHOLDER.sub(lambda m: str(variables.get(m.group(1), "")), template)


def _as_data_uri(source: str | Path | None) -> str:
    """배경 사진을 data: URI 로 바꿔 페이지에 심습니다.

    set_content 로 띄운 페이지는 about:blank 출신이라 file:// 이미지를 못 불러오고,
    원격 URL 은 렌더 시점에 죽어 있을 수 있습니다. 둘 다 미리 바이트로 받아 넣습니다.
    실패하면 빈 문자열 — 사진 없는 레이아웃으로 자동 전환됩니다.
    """
    if not source:
        return ""
    text = str(source)
    if text.startswith("data:"):
        return text
    try:
        if text.startswith(("http://", "https://")):
            response = requests.get(text, timeout=15)
            response.raise_for_status()
            data = response.content
            mime = response.headers.get("content-type", "image/jpeg").split(";")[0]
        else:
            path = Path(text)
            data = path.read_bytes()
            mime = mimetypes.guess_type(path.name)[0] or "image/png"
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"
    except Exception as exc:  # noqa: BLE001 - 배경 사진은 없어도 카드가 나옵니다
        log.warn(f"배경 사진을 못 불러왔습니다 — 사진 없는 레이아웃으로 갑니다 ({exc})")
        return ""


def generate_images(copy: dict, brand: dict, image_config: dict, paths: RunPaths,
                    article: dict | None = None, fallback_image: str | None = None) -> list[Path]:
    template_file = resolve(image_config["template"])
    if not template_file.exists():
        raise FileNotFoundError(f"이미지 템플릿이 없습니다: {template_file}")
    template = template_file.read_text(encoding="utf-8")

    card = copy.get("card") or {}
    colors = brand.get("colors") or {}
    background = _as_data_uri((article or {}).get("image") or fallback_image)

    jobs = []
    for size in image_config["sizes"]:
        variables = {
            "FONT_CSS": korean_font_face(),
            "bodyClass": "withphoto" if background else "nophoto",
            "width": size["width"],
            "height": size["height"],
            "bg": colors.get("bg", "#0B3D91"),
            "accent": colors.get("accent", "#4FC3F7"),
            "text": colors.get("text", "#FFFFFF"),
            "highlight": colors.get("highlight", "#FFD54F"),
            "image": background,
            "badge": _esc(card.get("badge") or brand.get("name")),
            "title": _emphasize(card.get("title") or copy.get("hook")),
            "subtitle": _esc(card.get("subtitle") or copy.get("hookSub")),
            "bullets": "".join(f"<li>{_esc(b)}</li>" for b in (card.get("bullets") or [])),
            "brand": _esc(brand.get("name")),
            "cta": _esc(copy.get("cta") or brand.get("cta")),
        }
        jobs.append(RenderJob(
            html=_fill(template, variables),
            width=size["width"],
            height=size["height"],
            out=paths.images / f"{size['name']}.png",
        ))

    files = render_all(jobs)
    log.ok(f"홍보 이미지 {len(files)}장 → {relative(paths.images)}/")
    return files
