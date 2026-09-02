"""홈페이지를 자동으로 조작하면서 전 과정을 녹화합니다."""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Locator, Page, sync_playwright

from .. import log
from ..paths import ROOT, RunPaths, write_json
from .cursor import CURSOR_INIT_SCRIPT
from .screencast import Screencast

_SELECTORISH = re.compile(r"[#.\[\]>:]")


def _normalize_url(url: str) -> str:
    """로컬 HTML 경로도 열리게 해줍니다 (데모/사내 파일 테스트용)."""
    if not url or re.match(r"^[a-z]+:", url, re.IGNORECASE):
        return url
    return (ROOT / url).resolve().as_uri()


def _resolve_locator(page: Page, spec: Any) -> Locator:
    """문자열 하나만 온 경우도 셀렉터/텍스트 어느 쪽이든 받아줍니다."""
    if isinstance(spec, str):
        looks_like_selector = bool(_SELECTORISH.search(spec)) or spec.isalpha()
        return page.locator(spec).first if looks_like_selector else page.get_by_text(spec).first

    if spec.get("selector"):
        loc = page.locator(spec["selector"])
    elif spec.get("role"):
        loc = page.get_by_role(spec["role"], name=spec["name"]) if spec.get("name") else page.get_by_role(spec["role"])
    elif spec.get("label"):
        loc = page.get_by_label(spec["label"])
    elif spec.get("placeholder"):
        loc = page.get_by_placeholder(spec["placeholder"])
    elif spec.get("testId"):
        loc = page.get_by_test_id(spec["testId"])
    elif spec.get("text"):
        loc = page.get_by_text(spec["text"], exact=bool(spec.get("exact")))
    else:
        raise ValueError(f"대상을 알 수 없는 스텝입니다: {spec}")

    if spec.get("nth") is not None:
        loc = loc.nth(spec["nth"])
    return loc.first


#: 마우스가 목표까지 미끄러져 가는 동안의 프레임 수와 간격.
_GLIDE_STEPS = 22
_GLIDE_STEP_MS = 10
#: 미끄러지는 데 실제로 걸리는 시간은 기기마다 다릅니다(브라우저와 한 번씩 주고받는
#: 시간이 붙어서 계산값보다 깁니다). 첫 클릭은 이 값으로 잡고, 그다음부터는 방금
#: 걸린 시간을 그대로 씁니다.
_GLIDE_LEAD_DEFAULT = 0.5
#: 스크롤이 지정한 위치에 닿기를 기다리는 최대 시간
_SCROLL_SETTLE_MS = 3000


def _glide_to_point(page: Page, x: float, y: float, state: dict) -> None:
    """사람이 움직인 것처럼 마우스를 (x, y) 로 옮깁니다.

    좌표는 브라우저 화면 기준(CSS 픽셀)입니다 — 커서 오버레이가 쓰는
    clientX/clientY 와 같은 기준이라, 영상 속 점과 실제 클릭 지점이 어긋나지
    않습니다.
    """
    started = time.time()
    start = state.get("mouse") or {"x": x, "y": max(0.0, y - 220)}
    for i in range(1, _GLIDE_STEPS + 1):
        t = i / _GLIDE_STEPS
        ease = 2 * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 2) / 2
        page.mouse.move(start["x"] + (x - start["x"]) * ease, start["y"] + (y - start["y"]) * ease)
        page.wait_for_timeout(_GLIDE_STEP_MS)
    state["mouse"] = {"x": x, "y": y}
    state["glideSeconds"] = time.time() - started


def _glide_to(page: Page, locator: Locator, state: dict) -> None:
    """요소 한가운데로 마우스를 옮깁니다."""
    box = locator.bounding_box()
    if not box:
        return
    _glide_to_point(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, state)


def _dismiss_all(page: Page, selectors: list[str] | None) -> None:
    for selector in selectors or []:
        try:
            loc = page.locator(selector).first
            if loc.is_visible(timeout=400):
                loc.click(timeout=1200)
                log.info(f"방해 요소 닫음: {selector}")
                page.wait_for_timeout(250)
        except Exception:  # noqa: BLE001 - 없으면 그냥 넘어갑니다
            pass


_SMOOTH_SCROLL = """
async ({ to, pixels, duration }) => {
  const start = window.scrollY;
  const max = document.documentElement.scrollHeight - window.innerHeight;
  let target = start;
  if (pixels !== undefined && pixels !== null) target = start + pixels;
  else if (to === "bottom") target = max;
  else if (to === "top") target = 0;
  else {
    const el = document.querySelector(to);
    if (el) target = window.scrollY + el.getBoundingClientRect().top - window.innerHeight / 3;
  }
  target = Math.max(0, Math.min(max, target));
  const frames = Math.max(1, Math.round(duration * 60));
  for (let i = 1; i <= frames; i++) {
    const t = i / frames;
    const ease = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    window.scrollTo(0, start + (target - start) * ease);
    await new Promise((r) => requestAnimationFrame(r));
  }
}
"""


def _smooth_scroll(page: Page, spec: dict) -> None:
    """사람처럼 부드럽게 스크롤합니다.

    브라우저 안에서 requestAnimationFrame 으로 내립니다. 파이썬에서 끊어 내리는 것보다
    프레임이 잘 잡힙니다 (실측: 끊어 내리기 269프레임 vs 이 방식 385프레임).
    """
    room = page.evaluate("() => document.documentElement.scrollHeight - window.innerHeight")
    if room < 10:
        log.warn("페이지가 화면보다 짧아 스크롤할 것이 없습니다 — 영상이 정지 화면처럼 나옵니다.")
        log.info("  화면 크기를 더 작게 잡거나, 시나리오 yaml 로 클릭·입력을 넣어보세요.")

    page.evaluate(_SMOOTH_SCROLL, {
        "to": spec.get("to", "bottom"),
        "pixels": spec.get("pixels"),
        "duration": spec.get("duration", 2),
    })


#: 좌표가 정말 원하던 것을 가리키는지 확인하려고, 그 자리에 있는 요소를 읽어옵니다.
_ELEMENT_AT = r"""
([x, y]) => {
  const el = document.elementFromPoint(x, y);
  if (!el) return null;
  const rect = el.getBoundingClientRect();
  const label = (el.innerText || el.value || el.getAttribute("aria-label") || "").trim();
  return {
    tag: el.tagName.toLowerCase(),
    id: el.id || "",
    label: label.replace(/\s+/g, " ").slice(0, 40),
    rect: [Math.round(rect.left), Math.round(rect.top), Math.round(rect.width), Math.round(rect.height)],
    scrollY: Math.round(window.scrollY),
  };
}
"""


def _describe_point(page: Page, x: float, y: float) -> str:
    """(x, y) 자리에 무엇이 있는지 한 줄로. 좌표가 맞았는지 눈으로 확인하는 용도."""
    try:
        found = page.evaluate(_ELEMENT_AT, [x, y])
    except Exception:  # noqa: BLE001 - 확인용이라 실패해도 진행합니다
        return ""
    if not found:
        return "그 자리에 아무 요소도 없습니다"
    name = f"<{found['tag']}"
    if found["id"]:
        name += f"#{found['id']}"
    name += ">"
    return f"{name} {found['label']}".strip() if found["label"] else name


def _wait_for(page: Page, ctx: dict, at: float, lead: float = 0.0) -> float:
    """녹화 시작 기준 ``at - lead`` 초까지 기다리고, 남았던 시간을 돌려줍니다.

    돌려주는 값이 음수면 그만큼 이미 지났다는 뜻입니다. 기다리는 동안에도 화면
    캐스트 프레임이 들어오도록 페이지 쪽 타이머(`wait_for_timeout`)를 씁니다.
    """
    elapsed = ctx.get("elapsed")
    if not elapsed:
        return 0.0
    remaining = at - lead - elapsed()
    if remaining > 0:
        page.wait_for_timeout(remaining * 1000)
    return remaining


def _click_at(page: Page, spec: dict, ctx: dict) -> None:
    """지정한 시각에 지정한 좌표를 클릭합니다."""
    x, y = float(spec["x"]), float(spec["y"])

    size = page.viewport_size or {}
    width, height = size.get("width"), size.get("height")
    if width and height and not (0 <= x <= width - 1 and 0 <= y <= height - 1):
        raise ValueError(
            f"클릭 좌표 ({x:.0f}, {y:.0f}) 가 브라우저 화면 {width}×{height} 밖입니다."
        )

    # 좌표는 화면 기준이라, 찍을 때와 같은 스크롤 위치로 맞춘 뒤에 눌러야 같은 것이 눌립니다.
    # 정해진 시간만 기다리면 부드러운 스크롤이 채 도착하기 전에 눌러 버리므로,
    # 실제로 그 위치에 닿을 때까지(또는 페이지 끝까지) 기다립니다.
    scroll_y = float(spec.get("scrollY") or 0)
    current = float(page.evaluate("() => window.scrollY") or 0)
    if abs(scroll_y - current) > 2:
        page.evaluate("(y) => window.scrollTo({ top: y, behavior: 'smooth' })", scroll_y)
        try:
            page.wait_for_function(
                "(y) => Math.abs(window.scrollY - y) <= 2"
                " || window.scrollY >= document.documentElement.scrollHeight - window.innerHeight - 2",
                arg=scroll_y,
                timeout=_SCROLL_SETTLE_MS,
            )
        except Exception:  # noqa: BLE001 - 아래에서 실제 위치를 보고 알려줍니다
            pass
        page.wait_for_timeout(120)      # 관성이 완전히 멎도록 조금 더
        settled = float(page.evaluate("() => window.scrollY") or 0)
        if abs(settled - scroll_y) > 2:
            log.warn(
                f"스크롤을 {scroll_y:.0f}px 로 맞추려 했지만 {settled:.0f}px 에서 멈췄습니다 "
                "— 페이지가 그만큼 길지 않습니다. 좌표가 가리키는 곳이 달라질 수 있어요."
            )

    # 마우스를 먼저 보내 두고, 남은 시간을 마저 기다린 뒤에 누릅니다.
    # 미끄러지는 데 걸리는 시간이 기기마다 달라서, 이 순서라야 클릭이 지정한
    # 시각에 정확히 떨어집니다 (커서는 조금 먼저 도착 — 영상에서도 자연스럽습니다).
    at = float(spec["at"]) if spec.get("at") is not None else None
    if at is not None:
        _wait_for(page, ctx, at, lead=ctx.get("glideSeconds") or _GLIDE_LEAD_DEFAULT)

    _glide_to_point(page, x, y, ctx)

    if at is not None:
        late = -_wait_for(page, ctx, at)
        if late > 0.25:
            log.warn(f"클릭 시각 {at:.1f}초는 이미 {late:.1f}초 지났습니다 — 곧바로 클릭합니다.")
            log.info("  페이지 여는 시간까지 포함한 시각이라, 느린 사이트는 시각을 더 뒤로 잡아주세요.")

    target = _describe_point(page, x, y)
    page.mouse.click(x, y)

    elapsed = ctx.get("elapsed")
    when = f"{elapsed():.1f}초" if elapsed else "지금"
    log.info(f"클릭 {when} · ({x:.0f}, {y:.0f}) → {target or '확인 못 함'}")

    try:
        page.wait_for_load_state("domcontentloaded")
    except Exception:  # noqa: BLE001 - 이동이 없으면 그대로 진행
        pass


_HIGHLIGHT = """
(s) => {
  const el = document.querySelector(s);
  if (el) { el.classList.add("ap-focus", "ap-pulse"); setTimeout(() => el.classList.remove("ap-pulse"), 2400); }
}
"""


def _run_step(page: Page, step: dict, ctx: dict) -> None:
    if step.get("goto"):
        page.goto(_normalize_url(step["goto"]), wait_until="domcontentloaded")
        _dismiss_all(page, ctx["dismiss"])
        return

    if step.get("clickAt"):
        _click_at(page, step["clickAt"], ctx)
        return

    if step.get("click"):
        loc = _resolve_locator(page, step["click"])
        loc.wait_for(state="visible", timeout=step.get("timeout", 15) * 1000)
        _glide_to(page, loc, ctx)
        loc.click(timeout=10_000)
        try:
            page.wait_for_load_state("domcontentloaded")
        except Exception:  # noqa: BLE001 - 이동이 없으면 그대로 진행
            pass
        return

    if step.get("fill"):
        spec = step["fill"]
        loc = _resolve_locator(page, spec)
        loc.wait_for(state="visible", timeout=step.get("timeout", 15) * 1000)
        _glide_to(page, loc, ctx)
        loc.click(timeout=10_000)
        loc.fill("")
        loc.press_sequentially(str(spec.get("value", "")), delay=spec.get("typeDelay", 80))
        return

    if step.get("press"):
        spec = step["press"]
        if isinstance(spec, str):
            page.keyboard.press(spec)
        elif spec.get("selector") or spec.get("text"):
            _resolve_locator(page, spec).press(spec.get("key", "Enter"))
        else:
            page.keyboard.press(spec.get("key", "Enter"))
        return

    if step.get("hover"):
        loc = _resolve_locator(page, step["hover"])
        _glide_to(page, loc, ctx)
        loc.hover()
        return

    if step.get("select"):
        _resolve_locator(page, step["select"]).select_option(str(step["select"]["value"]))
        return

    if step.get("scroll"):
        _smooth_scroll(page, step["scroll"])
        return

    if step.get("highlight"):
        spec = step["highlight"]
        selector = spec if isinstance(spec, str) else spec["selector"]
        try:
            page.locator(selector).first.scroll_into_view_if_needed()
        except Exception:  # noqa: BLE001 - 이미 보이면 그대로
            pass
        page.evaluate(_HIGHLIGHT, selector)
        return

    if "wait" in step:
        spec = step["wait"]
        if isinstance(spec, (int, float)):
            page.wait_for_timeout(float(spec) * 1000)
        elif spec.get("selector"):
            page.locator(spec["selector"]).first.wait_for(
                state=spec.get("state", "visible"), timeout=spec.get("timeout", 15) * 1000
            )
        else:
            page.wait_for_timeout(float(spec.get("seconds", 1)) * 1000)
        return

    if step.get("screenshot"):
        spec = step["screenshot"]
        name = spec if isinstance(spec, str) else f"shot-{ctx['index']}"
        page.screenshot(path=str(ctx["dir"] / f"{name}.png"))
        return

    # caption / pause 만 있는 스텝은 "화면을 잠깐 보여주는" 용도입니다.


def capture(flow: dict, paths: RunPaths, headless: bool = True) -> dict:
    """시나리오를 실행하며 녹화하고, 영상 경로·자막 타임라인·스크린샷을 돌려줍니다."""
    directory = paths.capture
    viewport = {
        "width": (flow.get("viewport") or {}).get("width", 540),
        "height": (flow.get("viewport") or {}).get("height", 960),
    }
    scale = (flow.get("viewport") or {}).get("deviceScaleFactor", 2)
    frame_width, frame_height = viewport["width"] * scale, viewport["height"] * scale

    log.step(f"녹화 시작: {flow.get('name') or flow.get('url')}")
    captions: list[dict] = []
    events: list[dict] = []
    shots: list[str] = []
    video_path: str | None = None
    used_screencast = False

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            executable_path=os.environ.get("CHROMIUM_PATH") or None,
            args=["--force-color-profile=srgb", "--font-render-hinting=none"],
        )
        context = browser.new_context(
            viewport=viewport,
            device_scale_factor=scale,
            locale=flow.get("locale", "ko-KR"),
            timezone_id=flow.get("timezone", "Asia/Seoul"),
            is_mobile=viewport["width"] < 700,
            has_touch=viewport["width"] < 700,
            # 화면 캐스트가 실패했을 때를 위한 예비 녹화 (CSS 픽셀 크기로 저장됩니다)
            record_video_dir=str(directory),
            record_video_size=viewport,
        )
        if flow.get("showCursor") is not False:
            context.add_init_script(CURSOR_INIT_SCRIPT)

        page = context.new_page()
        screencast = Screencast(page=page, dir=directory)
        try:
            screencast.start(max_width=frame_width, max_height=frame_height)
        except Exception as exc:  # noqa: BLE001
            log.warn(f"화면 캐스트를 못 켰습니다. 예비 녹화로 진행합니다 — {exc}")

        t0 = time.time()
        ctx: dict = {"dismiss": flow.get("dismiss"), "dir": directory, "index": 0}

        def elapsed() -> float:
            return time.time() - t0

        # 좌표 클릭이 "녹화 시작 후 몇 초" 를 지킬 수 있도록 시계를 넘겨줍니다.
        ctx["elapsed"] = elapsed

        def push_caption(text: str) -> None:
            if captions:
                captions[-1]["end"] = elapsed()
            captions.append({"text": text, "start": elapsed(), "end": None})

        try:
            if flow.get("url"):
                page.goto(_normalize_url(flow["url"]), wait_until="domcontentloaded", timeout=45_000)
                _dismiss_all(page, flow.get("dismiss"))
                page.wait_for_timeout(600)

            for index, step in enumerate(flow.get("steps") or []):
                ctx["index"] = index
                if step.get("caption"):
                    push_caption(step["caption"])
                started = elapsed()
                try:
                    _run_step(page, step, ctx)
                except Exception as exc:  # noqa: BLE001
                    first_line = str(exc).splitlines()[0]
                    if step.get("optional"):
                        log.warn(f"스텝 {index + 1} 건너뜀 (optional): {first_line}")
                    else:
                        raise RuntimeError(f"스텝 {index + 1} 실패 — {step}\n  {first_line}") from exc

                page.wait_for_timeout(float(step.get("pause") or 0.4) * 1000)

                shot = directory / f"step-{index + 1:02d}.png"
                try:
                    page.screenshot(path=str(shot))
                    shots.append(str(shot))
                except Exception:  # noqa: BLE001 - 스크린샷 실패는 치명적이지 않습니다
                    pass
                events.append({"index": index + 1, "start": started, "end": elapsed(), "step": step})

            page.wait_for_timeout(800)
            if captions:
                captions[-1]["end"] = elapsed()
        finally:
            wall_duration = time.time() - t0
            screencast.stop()
            video = page.video
            context.close()   # ← 이 시점에 예비 webm 이 디스크로 flush 됩니다
            browser.close()

            try:
                assembled = screencast.assemble(
                    directory / "recording.mp4", width=frame_width, height=frame_height, fps=30, t0=t0
                )
            except Exception as exc:  # noqa: BLE001
                log.warn(f"프레임 합치기 실패 — 예비 녹화를 씁니다: {exc}")
                assembled = None

            if assembled:
                video_path, used_screencast = str(assembled), True
            elif video:
                video_path = video.path()

    # 영상 시간축에 맞춰 자막 시각을 다시 계산합니다.
    to_video = screencast.map_time if used_screencast else (lambda s: s)
    timeline = {
        "name": flow.get("name", ""),
        "url": flow.get("url", ""),
        "recordedAt": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0)),
        "wallDuration": wall_duration,
        "duration": screencast.video_duration if used_screencast else wall_duration,
        "captions": [
            {**c, "start": to_video(c["start"]), "end": to_video(c["end"] if c["end"] is not None else wall_duration)}
            for c in captions
        ],
        "events": [{**e, "start": to_video(e["start"]), "end": to_video(e["end"])} for e in events],
    }
    write_json(Path(directory) / "timeline.json", timeline)
    log.ok(
        f"녹화 완료 · {timeline['duration']:.1f}초 · 자막 {len(captions)}개 · 스크린샷 {len(shots)}장"
    )
    return {"video": video_path, "timeline": timeline, "shots": shots}
