"""주소만 있을 때 쓰는 기본 녹화 시나리오."""
from __future__ import annotations

from urllib.parse import urlparse

from .clicks import normalize_clicks

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

#: 첫 화면을 보여주는 시간. 지정한 클릭이 이보다 이르면 그만큼 줄입니다.
_LEAD_SECONDS = 1.4


def simple_flow(
    url: str,
    caption: str = "",
    scroll_seconds: float = 6.0,
    viewport: dict | None = None,
    name: str = "",
    clicks: list[dict] | None = None,
    auto_dismiss: bool = True,
) -> dict:
    """주소 하나로 '들어가서 훑어보는' 시나리오를 만듭니다.

    시나리오 yaml 을 쓰지 않고도 홈페이지를 소개하는 영상이 나오도록,
    위에서 아래까지 천천히 내렸다가 다시 위로 올라옵니다.

    ``clicks`` 를 주면 스크롤을 시작하기 전에 지정한 시각·좌표를 순서대로
    클릭합니다. ``auto_dismiss`` 를 끄면 팝업을 자동으로 닫지 않습니다 —
    닫기 버튼을 직접 좌표로 찍고 싶을 때 씁니다.
    """
    host = urlparse(url).netloc or url
    view = viewport or VIEWPORTS["모바일 (540×960)"]
    points = normalize_clicks(clicks, view)

    steps: list[dict] = []

    # 첫 클릭이 이르면 첫 화면을 보여주는 시간을 그만큼 줄입니다 (클릭 시각을 지키려고).
    lead = min(_LEAD_SECONDS, points[0]["at"]) if points else _LEAD_SECONDS
    if caption:
        steps.append({"caption": caption, "pause": lead})
    else:
        steps.append({"wait": lead})

    for point in points:
        steps.append({"clickAt": point, "pause": 0.5})

    steps.append({"scroll": {"to": "bottom", "duration": max(1.0, scroll_seconds)}, "pause": 0.6})
    steps.append({"scroll": {"to": "top", "duration": 1.5}, "pause": 0.6})

    return {
        "name": name or host,
        "url": url,
        "viewport": view,
        "locale": "ko-KR",
        "timezone": "Asia/Seoul",
        "showCursor": True,
        "dismiss": COMMON_DISMISS if auto_dismiss else [],
        "steps": steps,
    }
