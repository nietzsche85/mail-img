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


def _glide_to(page: Page, locator: Locator, state: dict) -> None:
    """사람이 움직인 것처럼 마우스를 옮깁니다. 영상에서 클릭이 눈에 보이게 하려는 목적."""
    box = locator.bounding_box()
    if not box:
        return
    x = box["x"] + box["width"] / 2
    y = box["y"] + box["height"] / 2
    start = state.get("mouse") or {"x": box["x"], "y": max(0.0, box["y"] - 220)}
    steps = 22
    for i in range(1, steps + 1):
        t = i / steps
        ease = 2 * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 2) / 2
        page.mouse.move(start["x"] + (x - start["x"]) * ease, start["y"] + (y - start["y"]) * ease)
        page.wait_for_timeout(10)
    state["mouse"] = {"x": x, "y": y}


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
        spec = step["scroll"]
        page.evaluate(_SMOOTH_SCROLL, {
            "to": spec.get("to", "bottom"),
            "pixels": spec.get("pixels"),
            "duration": spec.get("duration", 2),
        })
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
