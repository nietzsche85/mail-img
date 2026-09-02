"""영상에 얹을 자막·인트로·아웃트로 카드 HTML."""
from __future__ import annotations

import html
import re
from typing import Any

from .html2png import base_css

_EMPHASIS = re.compile(r"\*\*(.+?)\*\*")


def _esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=False)


def _emphasize(text: Any, accent: str) -> str:
    """**강조** 문법을 포인트 색 span 으로 바꿉니다."""
    return _EMPHASIS.sub(rf'<span style="color:{accent}">\1</span>', _esc(text))


def palette(brand: dict) -> dict[str, str]:
    colors = (brand or {}).get("colors") or {}
    return {
        "bg": colors.get("bg", "#0B3D91"),
        "accent": colors.get("accent", "#4FC3F7"),
        "text": colors.get("text", "#FFFFFF"),
        "highlight": colors.get("highlight", "#FFD54F"),
    }


def caption_html(text: str, width: int, height: int, brand: dict) -> str:
    """영상 위에 얹을 자막 (투명 배경). 하단 UI 를 피해 안전 영역에 배치합니다."""
    c = palette(brand)
    return f"""<!doctype html><meta charset="utf-8"><style>{base_css()}
  body{{background:transparent;display:flex;align-items:flex-end;justify-content:center;
    padding:0 64px {round(height * 0.19)}px}}
  .box{{max-width:100%;background:rgba(10,14,24,.82);backdrop-filter:blur(2px);
    border-radius:28px;padding:30px 40px;box-shadow:0 18px 50px rgba(0,0,0,.45)}}
  .t{{font-size:{round(width * 0.062)}px;font-weight:800;color:{c['text']};text-align:center;
    letter-spacing:-.02em;text-shadow:0 3px 12px rgba(0,0,0,.5)}}
  </style><div class="box"><div class="t">{_emphasize(text, c['highlight'])}</div></div>"""


def intro_html(hook: str, sub: str, brand: dict, width: int, height: int) -> str:
    """첫 1.5초를 잡는 훅 카드.

    위쪽 배지는 기본으로 넣지 않습니다. 브랜드 이름이 첫 화면에 박히면
    광고처럼 보여서 이탈이 늘어납니다. 넣고 싶으면 설정에 brand.badge 를 적으세요.
    """
    c = palette(brand)
    sub_block = f'<div class="sub">{_esc(sub)}</div>' if sub else ""
    badge = (brand or {}).get("badge") or ""
    badge_block = f'<div class="badge">{_esc(badge)}</div>' if badge else ""
    return f"""<!doctype html><meta charset="utf-8"><style>{base_css()}
  body{{background:linear-gradient(160deg,{c['bg']} 0%,#04122f 100%);color:{c['text']};
    display:flex;flex-direction:column;align-items:center;justify-content:center;
    padding:0 80px;text-align:center}}
  .badge{{border:2px solid {c['accent']};color:{c['accent']};border-radius:999px;
    padding:12px 28px;font-size:{round(width * 0.031)}px;font-weight:700;margin-bottom:48px}}
  .hook{{font-size:{round(width * 0.098)}px;font-weight:900;letter-spacing:-.035em;line-height:1.22}}
  .sub{{margin-top:36px;font-size:{round(width * 0.041)}px;font-weight:500;opacity:.82}}
  .bar{{margin-top:64px;width:120px;height:8px;border-radius:8px;background:{c['accent']}}}
  </style>
  {badge_block}
  <div class="hook">{_emphasize(hook, c['highlight'])}</div>
  {sub_block}
  <div class="bar"></div>"""


def outro_html(cta: str, brand: dict, width: int, height: int) -> str:
    """마지막 CTA 카드.

    두 줄 다 비우면 그 줄은 아예 안 나옵니다.
    - 큰 문구: 설정의 brand.cta (또는 카피가 만든 cta)
    - 아래 작은 줄: 설정의 brand.signature. 기본은 비어 있어 아무것도 안 나옵니다.
    """
    c = palette(brand)
    signature = (brand or {}).get("signature") or ""
    cta_block = (
        f'<div class="cta">{_emphasize(cta, c["highlight"])}</div>\n  <div class="arrow">↓</div>'
        if cta else ""
    )
    signature_block = f'<div class="name">{_esc(signature)}</div>' if signature else ""

    return f"""<!doctype html><meta charset="utf-8"><style>{base_css()}
  body{{background:linear-gradient(200deg,#04122f 0%,{c['bg']} 100%);color:{c['text']};
    display:flex;flex-direction:column;align-items:center;justify-content:center;
    padding:0 80px;text-align:center}}
  .cta{{font-size:{round(width * 0.078)}px;font-weight:900;letter-spacing:-.03em;line-height:1.25}}
  .arrow{{margin-top:44px;font-size:{round(width * 0.1)}px;color:{c['accent']}}}
  .name{{margin-top:56px;font-size:{round(width * 0.036)}px;font-weight:700;opacity:.75;letter-spacing:.08em}}
  </style>
  {cta_block}
  {signature_block}"""
