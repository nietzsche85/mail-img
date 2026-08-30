"""HTML 을 크롬으로 그려 PNG 로 굽습니다.

ffmpeg 의 drawtext 는 한글 폰트 문제가 잦아서, 글자는 전부 여기서 그린 뒤 영상에 얹습니다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from playwright.sync_api import sync_playwright

from ..paths import ROOT

FONT_DIR = ROOT / "assets" / "fonts"
_WEIGHTS = (400, 700, 900)


@lru_cache(maxsize=1)
def korean_font_face() -> str:
    """동봉된 한글 웹폰트를 file:// 로 인라인합니다 (인터넷 없이도 동작)."""
    faces = []
    for weight in _WEIGHTS:
        file = FONT_DIR / f"noto-sans-kr-korean-{weight}-normal.woff2"
        if file.exists():
            faces.append(
                f"@font-face{{font-family:'AP Sans';font-style:normal;font-weight:{weight};"
                f"font-display:block;src:url('{file.as_uri()}') format('woff2');}}"
            )
    return "\n".join(faces) or "/* 동봉 폰트를 찾지 못해 시스템 폰트로 대체합니다 */"


def base_css() -> str:
    return f"""
{korean_font_face()}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:100%;height:100%}}
body{{font-family:'AP Sans','Noto Sans KR',system-ui,sans-serif;-webkit-font-smoothing:antialiased;
  word-break:keep-all;line-height:1.35}}
"""


@dataclass
class RenderJob:
    html: str
    width: int
    height: int
    out: Path
    transparent: bool = False


def render_all(jobs: list[RenderJob]) -> list[Path]:
    """HTML 여러 개를 브라우저 한 번 띄워서 전부 굽습니다."""
    if not jobs:
        return []
    results: list[Path] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            executable_path=os.environ.get("CHROMIUM_PATH") or None,
            args=["--force-color-profile=srgb"],
        )
        try:
            for job in jobs:
                page = browser.new_page(
                    viewport={"width": job.width, "height": job.height}, device_scale_factor=1
                )
                page.set_content(job.html, wait_until="load")
                page.evaluate("document.fonts.ready")
                job.out.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(job.out), omit_background=job.transparent)
                page.close()
                results.append(job.out)
        finally:
            browser.close()
    return results
