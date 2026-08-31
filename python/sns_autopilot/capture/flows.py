"""주소만 있을 때 쓰는 기본 녹화 시나리오."""
from __future__ import annotations

from urllib.parse import urlparse

VIEWPORTS: dict[str, dict] = {
    "모바일 (540×960)": {"width": 540, "height": 960, "deviceScaleFactor": 2},
    "태블릿 (768×1024)": {"width": 768, "height": 1024, "deviceScaleFactor": 2},
    "데스크톱 (1280×800)": {"width": 1280, "height": 800, "deviceScaleFactor": 1},
}

#: 쿠키·팝업처럼 어느 사이트에나 흔한 방해 요소
COMMON_DISMISS = [
    "button:has-text('동의')",
    "button:has-text('확인')",
    "button:has-text('닫기')",
    "button:has-text('Accept')",
    "[aria-label='close']",
    "[aria-label='닫기']",
]


def simple_flow(
    url: str,
    caption: str = "",
    scroll_seconds: float = 6.0,
    viewport: dict | None = None,
    name: str = "",
) -> dict:
    """주소 하나로 '들어가서 훑어보는' 시나리오를 만듭니다.

    시나리오 yaml 을 쓰지 않고도 홈페이지를 소개하는 영상이 나오도록,
    위에서 아래까지 천천히 내렸다가 다시 위로 올라옵니다.
    """
    host = urlparse(url).netloc or url
    steps: list[dict] = []

    if caption:
        steps.append({"caption": caption, "pause": 1.4})
    else:
        steps.append({"wait": 1.4})

    steps.append({"scroll": {"to": "bottom", "duration": max(1.0, scroll_seconds)}, "pause": 0.6})
    steps.append({"scroll": {"to": "top", "duration": 1.5}, "pause": 0.6})

    return {
        "name": name or host,
        "url": url,
        "viewport": viewport or VIEWPORTS["모바일 (540×960)"],
        "locale": "ko-KR",
        "timezone": "Asia/Seoul",
        "showCursor": True,
        "dismiss": COMMON_DISMISS,
        "steps": steps,
    }
