"""브라우저를 띄워 놓고 클릭할 자리를 직접 찍어 좌표를 받아옵니다.

좌표를 손으로 적으면 배율·스크롤 때문에 틀리기 쉽습니다. 여기서는 실제 녹화와
**똑같은 창 크기**로 페이지를 열고, 사람이 누른 지점의 clientX/clientY 를 그대로
가져옵니다. 녹화할 때 쓰는 좌표와 같은 기준이라 환산이 아예 필요 없습니다.

Playwright 동기 API 객체는 만든 스레드에서만 쓸 수 있어서, 이 함수가 브라우저를
통째로 소유하고 창(GUI)은 큐로 "완료/취소" 만 보냅니다 — 수동 녹화와 같은 방식.
"""
from __future__ import annotations

import os
import queue
import time
from typing import Callable

from playwright.sync_api import sync_playwright

from .. import log
from .clicks import viewport_size

#: 명령을 기다리는 간격
_TICK_MS = 120

#: 페이지 위에 얹는 도우미. 클릭을 가로채 좌표만 기록하고, 페이지 동작은 막습니다.
#: (좌표를 찍는 동안 링크를 눌러 다른 데로 넘어가면 안 되니까요.)
_PICKER_SCRIPT = r"""
(() => {
  if (window.__apPick) return;
  const S = (window.__apPick = { points: [], done: false });

  const install = () => {
    if (!document.body || document.getElementById("ap-pick-style")) return;

    const style = document.createElement("style");
    style.id = "ap-pick-style";
    style.textContent = `
      #ap-pick-xy{position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;
        font:600 12px/1.4 ui-monospace,Consolas,monospace;color:#fff;white-space:pre;
        background:rgba(11,61,145,.92);padding:4px 8px;border-radius:6px;
        box-shadow:0 2px 10px rgba(0,0,0,.35)}
      /* box-sizing 이 없으면 테두리 2px 만큼 표시가 밀려서, 찍은 자리와 어긋나 보입니다. */
      .ap-pick-mark{position:absolute;width:24px;height:24px;margin:-12px 0 0 -12px;
        box-sizing:border-box;
        border-radius:50%;border:2px solid #4FC3F7;background:rgba(79,195,247,.28);
        color:#062b52;font:700 12px/20px sans-serif;text-align:center;
        pointer-events:none;z-index:2147483646}
      #ap-pick-cross{position:fixed;left:0;top:0;width:100%;height:100%;
        pointer-events:none;z-index:2147483645}
      #ap-pick-cross i{position:absolute;background:rgba(79,195,247,.55)}
    `;
    document.head.appendChild(style);

    const readout = document.createElement("div");
    readout.id = "ap-pick-xy";
    readout.textContent = "클릭할 자리를 누르세요";
    document.body.appendChild(readout);

    const cross = document.createElement("div");
    cross.id = "ap-pick-cross";
    const vertical = document.createElement("i");
    const horizontal = document.createElement("i");
    vertical.style.cssText = "width:1px;height:100%;top:0";
    horizontal.style.cssText = "height:1px;width:100%;left:0";
    cross.append(vertical, horizontal);
    document.body.appendChild(cross);

    const keepInside = (el) => { if (!el.isConnected && document.body) document.body.appendChild(el); };

    addEventListener("mousemove", (e) => {
      [readout, cross].forEach(keepInside);
      vertical.style.left = e.clientX + "px";
      horizontal.style.top = e.clientY + "px";
      readout.textContent = `X ${Math.round(e.clientX)}  Y ${Math.round(e.clientY)}`;
      // 커서를 가리지 않게, 화면 끝에서는 반대쪽으로 붙입니다.
      const right = e.clientX + 130 > innerWidth;
      const bottom = e.clientY + 40 > innerHeight;
      readout.style.left = (right ? e.clientX - 126 : e.clientX + 16) + "px";
      readout.style.top = (bottom ? e.clientY - 34 : e.clientY + 18) + "px";
    }, true);

    const record = (e) => {
      // 페이지가 반응하지 못하게 완전히 가로챕니다.
      e.preventDefault();
      e.stopPropagation();
      if (e.type !== "click") return;

      const point = {
        x: Math.round(e.clientX),
        y: Math.round(e.clientY),
        scrollY: Math.round(window.scrollY),
      };
      S.points.push(point);

      const mark = document.createElement("div");
      mark.className = "ap-pick-mark";
      mark.textContent = String(S.points.length);
      // 문서 기준으로 붙여서, 스크롤해도 찍은 자리에 그대로 남게 합니다.
      mark.style.left = point.x + window.scrollX + "px";
      mark.style.top = point.y + window.scrollY + "px";
      document.body.appendChild(mark);
    };

    ["mousedown", "mouseup", "click"].forEach((type) => addEventListener(type, record, true));
    addEventListener("submit", (e) => e.preventDefault(), true);
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install);
  else install();
})();
"""


def pick_points(
    url: str,
    viewport: dict | None = None,
    commands: queue.Queue | None = None,
    on_state: Callable[[str], None] | None = None,
) -> list[dict]:
    """브라우저를 열고 사람이 찍은 좌표들을 돌려줍니다.

    받는 명령: "done"(찍은 것을 가지고 닫기) · "cancel"(버리고 닫기).
    브라우저 창을 그냥 닫아도 그때까지 찍은 좌표를 가지고 나옵니다.
    돌려주는 각 항목은 ``{"x", "y", "scrollY"}`` — 모두 브라우저 화면(CSS) 기준입니다.
    """
    commands = commands or queue.Queue()
    width, height, scale = viewport_size(viewport)
    points: list[dict] = []
    cancelled = False

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,      # 눈으로 보고 찍는 기능이라 항상 창을 띄웁니다
            executable_path=os.environ.get("CHROMIUM_PATH") or None,
            args=["--force-color-profile=srgb", "--font-render-hinting=none"],
        )
        context = browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=scale,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            is_mobile=width < 700,
            has_touch=width < 700,
        )
        # 페이지가 넘어가도 도우미가 살아 있도록 init script 로 넣습니다.
        context.add_init_script(_PICKER_SCRIPT)
        page = context.new_page()

        try:
            if url:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.evaluate(_PICKER_SCRIPT)      # 이미 열린 문서에도 즉시 적용
            log.ok(f"좌표 찍기 — 브라우저 {width}×{height} (영상은 {width * scale}×{height * scale})")
            log.info("  누르고 싶은 자리를 차례로 클릭한 뒤, 창에서 '찍기 완료' 를 누르세요.")
            log.info("  이 화면에서는 링크·버튼이 동작하지 않습니다 (좌표만 기록합니다).")
            if on_state:
                on_state("picking")

            deadline = time.time() + 15 * 60      # 창을 열어둔 채 잊어버려도 언젠가는 닫히게
            while True:
                if page.is_closed():
                    log.info("브라우저 창이 닫혔습니다.")
                    break

                snapshot = page.evaluate(
                    "() => window.__apPick ? window.__apPick.points.slice() : null"
                )
                if snapshot is not None:
                    points = snapshot

                try:
                    command = commands.get_nowait()
                except queue.Empty:
                    command = None

                if command == "done":
                    break
                if command == "cancel":
                    cancelled = True
                    break
                if time.time() > deadline:
                    log.warn("15분이 지나 좌표 찍기를 자동으로 닫습니다.")
                    break

                page.wait_for_timeout(_TICK_MS)
        finally:
            try:
                context.close()
            finally:
                browser.close()
            if on_state:
                on_state("idle")

    if cancelled:
        log.warn("좌표 찍기를 취소했습니다.")
        return []

    for index, point in enumerate(points, start=1):
        note = f" · 스크롤 {point['scrollY']}px" if point.get("scrollY") else ""
        log.ok(f"좌표 {index}: ({point['x']}, {point['y']}){note}")
    if not points:
        log.warn("찍은 좌표가 없습니다.")
    return points
