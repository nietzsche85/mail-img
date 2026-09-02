"""브라우저를 띄워 두고 사람이 직접 조작하는 동안 녹화합니다.

자동 시나리오(yaml)로 담기 어려운 화면 — 로그인이 필요하거나, 그때그때 다르게
보여주고 싶은 흐름 — 을 손으로 조작하면서 원하는 구간만 잘라 담을 때 씁니다.

Playwright 동기 API 객체는 만든 스레드에서만 쓸 수 있어서, 이 함수가 브라우저를
통째로 소유하고 GUI 는 큐로 명령만 보냅니다.
"""
from __future__ import annotations

import os
import queue
import time
from pathlib import Path
from typing import Callable

from playwright.sync_api import sync_playwright

from .. import log
from ..paths import RunPaths, write_json
from .cursor import CURSOR_INIT_SCRIPT
from .screencast import Screencast

class RecordingCancelled(RuntimeError):
    """사람이 취소를 눌렀을 때. 실패가 아니라 정상 종료로 다룹니다."""


#: 명령을 기다리는 동안 이 간격으로 깨어납니다.
#: wait_for_timeout 이어야 그 사이 화면 캐스트 프레임이 흘러 들어옵니다.
_TICK_MS = 100


def record_manually(
    url: str,
    paths: RunPaths,
    viewport: dict | None = None,
    caption: str = "",
    commands: queue.Queue | None = None,
    on_state: Callable[[str], None] | None = None,
) -> dict:
    """브라우저를 열고 `commands` 로 들어오는 지시에 따라 녹화합니다.

    받는 명령: "start"(녹화 시작) · "stop"(녹화 끝내고 저장) · "cancel"(버리고 닫기)
    """
    commands = commands or queue.Queue()
    directory = paths.capture
    view = viewport or {"width": 540, "height": 960, "deviceScaleFactor": 2}
    scale = view.get("deviceScaleFactor", 2)
    frame_size = {"width": view["width"] * scale, "height": view["height"] * scale}

    def announce(state: str) -> None:
        if on_state:
            on_state(state)

    captions: list[dict] = []
    shots: list[str] = []
    video_path: str | None = None
    recorded = 0.0
    t0 = 0.0
    cancelled = False

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,      # 손으로 조작해야 하니 항상 창을 띄웁니다
            executable_path=os.environ.get("CHROMIUM_PATH") or None,
            args=["--force-color-profile=srgb", "--font-render-hinting=none"],
        )
        context = browser.new_context(
            viewport={"width": view["width"], "height": view["height"]},
            device_scale_factor=scale,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            is_mobile=view["width"] < 700,
            has_touch=view["width"] < 700,
        )
        context.add_init_script(CURSOR_INIT_SCRIPT)
        page = context.new_page()
        screencast = Screencast(page=page, dir=directory)

        try:
            if url:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            log.ok("브라우저를 열었습니다. 화면을 원하는 상태로 맞춘 뒤 '녹화 시작' 을 누르세요.")
            announce("opened")

            recording = False
            while True:
                if page.is_closed():
                    log.warn("브라우저 창이 닫혔습니다.")
                    break

                try:
                    command = commands.get_nowait()
                except queue.Empty:
                    command = None

                if command == "start" and not recording:
                    screencast.start(max_width=frame_size["width"], max_height=frame_size["height"])
                    t0 = time.time()
                    recording = True
                    page.screenshot(path=str(directory / "step-01.png"))
                    shots.append(str(directory / "step-01.png"))
                    log.ok("녹화를 시작했습니다. 브라우저에서 보여주고 싶은 동작을 하세요.")
                    announce("recording")

                elif command == "stop":
                    if not recording:
                        log.warn("아직 녹화를 시작하지 않았습니다.")
                    else:
                        recorded = time.time() - t0
                        page.screenshot(path=str(directory / "step-02.png"))
                        shots.append(str(directory / "step-02.png"))
                        screencast.stop()
                        log.ok(f"녹화를 멈췄습니다 · {recorded:.1f}초")
                    break

                elif command == "cancel":
                    log.warn("녹화를 취소했습니다.")
                    screencast.stop()
                    cancelled = True
                    break

                # 기다리는 동안에도 화면 캐스트 프레임이 들어오도록 페이지 쪽에서 대기합니다.
                page.wait_for_timeout(_TICK_MS)
        finally:
            announce("closing")
            try:
                context.close()
            finally:
                browser.close()

            if screencast.frames and not cancelled:
                video_path = screencast.assemble(
                    directory / "recording.mp4", width=frame_size["width"],
                    height=frame_size["height"], fps=30, t0=t0,
                )
                video_path = str(video_path) if video_path else None

    if cancelled:
        raise RecordingCancelled("녹화를 취소했습니다.")
    if not video_path:
        raise RuntimeError(
            "녹화된 화면이 없습니다. '녹화 시작' 을 누른 뒤 브라우저에서 무언가 움직인 다음 "
            "'녹화 종료' 를 눌러주세요."
        )

    duration = screencast.video_duration or recorded
    if caption:
        captions.append({"text": caption, "start": 0.0, "end": duration})

    timeline = {
        "name": url or "수동 녹화",
        "url": url,
        "recordedAt": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0 or time.time())),
        "wallDuration": recorded,
        "duration": duration,
        "captions": captions,
        "events": [],
        "manual": True,
    }
    write_json(Path(directory) / "timeline.json", timeline)
    log.ok(f"녹화 저장 완료 · {duration:.1f}초 · 스크린샷 {len(shots)}장")
    return {"video": video_path, "timeline": timeline, "shots": shots}
