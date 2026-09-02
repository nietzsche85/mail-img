"""수동으로 지정한 클릭 좌표를 검사하고 정리합니다.

좌표를 잘못 넣는 사고를 막는 것이 이 파일의 전부입니다. 실수는 거의 항상
아래 세 가지 중 하나라서, 세 가지를 각각 막습니다.

1. 배율 — 브라우저는 CSS 픽셀로 클릭하는데 녹화된 영상은
   CSS 픽셀 × deviceScaleFactor 크기입니다. 모바일(540×960, 배율 2)이면
   영상은 1080×1920 이고, 영상에서 잰 좌표를 그대로 넣으면 정확히 2배
   어긋납니다. :data:`VIDEO` 기준으로 넣으면 여기서 되돌려 줍니다.
2. 화면 밖 — 화면을 벗어난 좌표는 클릭해도 아무 일이 없거나 엉뚱한 곳이
   눌립니다. 브라우저를 띄우기 **전에** 걸러서 알려줍니다.
3. 스크롤 — 좌표는 화면 기준(clientX/clientY)이라 페이지를 내린 상태에서
   찍은 좌표는 맨 위에서 클릭하면 다른 것이 눌립니다. 찍을 때의 스크롤
   위치를 같이 들고 다니다가, 녹화 중 그 위치로 맞춘 뒤 클릭합니다.
"""
from __future__ import annotations

#: 좌표 기준 — 브라우저 창(CSS 픽셀). 파이프라인 안에서는 항상 이 기준으로 저장합니다.
CSS = "css"
#: 좌표 기준 — 완성된 영상 픽셀. 넣을 때만 쓰고 곧바로 CSS 로 환산합니다.
VIDEO = "video"

BASIS_LABELS = {CSS: "브라우저 화면", VIDEO: "영상 픽셀"}


class ClickSpecError(ValueError):
    """클릭 좌표 입력이 잘못됐을 때. 사람이 읽는 문장을 담습니다."""


def viewport_size(viewport: dict | None) -> tuple[int, int, int]:
    """(가로, 세로, 배율) 을 돌려줍니다. 값이 비어 있으면 모바일 기본값."""
    view = viewport or {}
    width = int(view.get("width") or 540)
    height = int(view.get("height") or 960)
    scale = int(view.get("deviceScaleFactor") or 1)
    return width, height, max(1, scale)


def video_size(viewport: dict | None) -> tuple[int, int]:
    """그 화면 크기로 찍었을 때 나오는 영상 픽셀 크기."""
    width, height, scale = viewport_size(viewport)
    return width * scale, height * scale


def to_css(x: float, y: float, basis: str, scale: int) -> tuple[float, float]:
    """영상에서 잰 좌표를 브라우저가 쓰는 CSS 좌표로 되돌립니다."""
    if basis == VIDEO:
        return x / scale, y / scale
    return float(x), float(y)


def _number(value: object, label: str, index: int) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ClickSpecError(f"{index}번째 클릭의 {label} 이(가) 숫자가 아닙니다: {value!r}") from exc


def normalize_clicks(clicks: list[dict] | None, viewport: dict | None,
                     basis: str = CSS) -> list[dict]:
    """입력을 검사해 CSS 좌표로 통일하고 시각순으로 정렬합니다.

    각 항목은 ``{"at": 초, "x": CSS X, "y": CSS Y, "scrollY": 스크롤}`` 이 됩니다.
    항목마다 ``basis`` 를 따로 줄 수 있고, 없으면 인자로 받은 기준을 씁니다.
    이 함수는 여러 번 돌려도 결과가 같습니다(이미 CSS 인 값은 그대로).
    """
    width, height, scale = viewport_size(viewport)
    result: list[dict] = []

    for index, spec in enumerate(clicks or [], start=1):
        if not isinstance(spec, dict):
            raise ClickSpecError(f"{index}번째 클릭의 형식을 알 수 없습니다: {spec!r}")

        at = _number(spec.get("at", 0) or 0, "시각", index)
        if at < 0:
            raise ClickSpecError(f"{index}번째 클릭: 시각은 0초 이상이어야 합니다 (넣은 값 {at}).")

        raw_x = _number(spec.get("x"), "X", index)
        raw_y = _number(spec.get("y"), "Y", index)
        item_basis = spec.get("basis") or basis
        if item_basis not in (CSS, VIDEO):
            raise ClickSpecError(f"{index}번째 클릭: 좌표 기준이 이상합니다 ({item_basis!r}).")
        x, y = to_css(raw_x, raw_y, item_basis, scale)

        if not (0 <= x <= width - 1) or not (0 <= y <= height - 1):
            hint = ""
            # 배율만큼 어긋난 전형적인 실수인지 짚어 줍니다.
            if item_basis == CSS and scale > 1 and 0 <= x / scale <= width - 1 and 0 <= y / scale <= height - 1:
                vw, vh = width * scale, height * scale
                hint = (f"\n  영상({vw}×{vh})에서 잰 값 같습니다 — 좌표 기준을 '영상 픽셀' 로 "
                        f"바꾸거나 {scale} 로 나눠서 ({x / scale:.0f}, {y / scale:.0f}) 로 넣으세요.")
            raise ClickSpecError(
                f"{index}번째 클릭 ({x:.0f}, {y:.0f}) 이(가) 브라우저 화면 {width}×{height} 밖입니다."
                f"{hint}"
            )

        scroll_y = _number(spec.get("scrollY", 0) or 0, "스크롤", index)
        if scroll_y < 0:
            raise ClickSpecError(f"{index}번째 클릭: 스크롤 위치는 0 이상이어야 합니다.")

        # 좌표는 정수로 맞춥니다. 브라우저가 마우스 이벤트의 clientX/clientY 를 정수로
        # 내려주기 때문에, 소수점을 남기면 영상 속 커서 점이 클릭 지점에서 1px 어긋납니다.
        result.append({
            "at": round(at, 2),
            "x": float(round(x)),
            "y": float(round(y)),
            "scrollY": float(round(scroll_y)),
        })

    result.sort(key=lambda click: click["at"])
    return result


def describe(click: dict) -> str:
    """로그에 한 줄로 적기 위한 표현."""
    text = f"{click['at']:.1f}초 · ({click['x']:.0f}, {click['y']:.0f})"
    if click.get("scrollY"):
        text += f" · 스크롤 {click['scrollY']:.0f}px"
    return text
