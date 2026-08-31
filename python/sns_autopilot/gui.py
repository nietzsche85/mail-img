"""주소를 넣고 버튼을 누르면 홈페이지를 녹화하고 숏츠로 인코딩하는 작은 창.

tkinter 만 씁니다 (파이썬 기본 포함, 추가 설치 없음).
무거운 모듈은 창을 띄운 뒤 작업 스레드에서 불러옵니다 — 창이 늦게 뜨지 않게.
"""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, W, X, BooleanVar, StringVar, Text, Tk, messagebox
from tkinter import font as tkfont
from tkinter import ttk

from .capture.flows import VIEWPORTS

PAD = 10


def _open_folder(path: Path) -> None:
    """탐색기/파인더로 폴더를 엽니다."""
    if sys.platform == "win32":
        subprocess.Popen(["explorer", str(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class App:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.result_dir: Path | None = None
        self.manual_commands: "queue.Queue[str] | None" = None
        self.manual_state = "idle"     # idle → opened → recording

        root.title("SNS 오토파일럿")
        root.minsize(680, 560)

        outer = ttk.Frame(root, padding=PAD)
        outer.pack(fill=BOTH, expand=True)

        # ── 입력 ────────────────────────────────────────────
        form = ttk.LabelFrame(outer, text="무엇을 찍을까요", padding=PAD)
        form.pack(fill=X)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="홈페이지 주소").grid(row=0, column=0, sticky=W, pady=4)
        self.url = StringVar()
        url_entry = ttk.Entry(form, textvariable=self.url)
        url_entry.grid(row=0, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=4)
        url_entry.focus()

        ttk.Label(form, text="첫 화면 문구").grid(row=1, column=0, sticky=W, pady=4)
        self.caption = StringVar()
        ttk.Entry(form, textvariable=self.caption).grid(
            row=1, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=4
        )
        ttk.Label(form, text="비워두면 문구 없이 화면만 담습니다. **강조** 를 쓰면 포인트 색으로 나옵니다.",
                  foreground="#666").grid(row=2, column=1, columnspan=3, sticky=W, padx=(8, 0))

        ttk.Label(form, text="화면 크기").grid(row=3, column=0, sticky=W, pady=(10, 4))
        self.viewport = StringVar(value=list(VIEWPORTS)[0])
        ttk.Combobox(form, textvariable=self.viewport, values=list(VIEWPORTS),
                     state="readonly", width=18).grid(row=3, column=1, sticky=W, padx=(8, 0), pady=(10, 4))

        ttk.Label(form, text="스크롤 시간").grid(row=3, column=2, sticky=W, padx=(16, 0), pady=(10, 4))
        self.scroll = StringVar(value="6")
        ttk.Spinbox(form, from_=1, to=30, width=5, textvariable=self.scroll).grid(
            row=3, column=3, sticky=W, padx=(8, 0), pady=(10, 4)
        )

        self.headed = BooleanVar(value=False)
        ttk.Checkbutton(form, text="브라우저 창을 띄워서 진행 보기", variable=self.headed).grid(
            row=4, column=1, columnspan=3, sticky=W, padx=(8, 0), pady=(6, 0)
        )

        # ── 버튼 ────────────────────────────────────────────
        buttons = ttk.Frame(outer, padding=(0, PAD))
        buttons.pack(fill=X)
        self.run_button = ttk.Button(buttons, text="캡쳐 + 인코딩", command=lambda: self.start("both"))
        self.run_button.pack(side=LEFT)
        self.capture_button = ttk.Button(buttons, text="캡쳐만", command=lambda: self.start("capture"))
        self.capture_button.pack(side=LEFT, padx=6)
        self.render_button = ttk.Button(buttons, text="인코딩만 (최근 캡쳐)",
                                        command=lambda: self.start("render"))
        self.render_button.pack(side=LEFT)
        self.open_button = ttk.Button(buttons, text="결과 폴더 열기", command=self.open_result,
                                      state="disabled")
        self.open_button.pack(side=RIGHT)

        # ── 수동 녹화 ───────────────────────────────────────
        manual = ttk.LabelFrame(outer, text="수동 녹화 (브라우저를 직접 조작하며 원하는 구간만 담기)",
                                padding=PAD)
        manual.pack(fill=X, pady=(0, PAD))
        self.open_browser_button = ttk.Button(manual, text="브라우저 열기",
                                              command=self.open_browser)
        self.open_browser_button.pack(side=LEFT)
        self.record_button = ttk.Button(manual, text="● 녹화 시작",
                                        command=lambda: self.send_manual("start"), state="disabled")
        self.record_button.pack(side=LEFT, padx=6)
        self.stop_button = ttk.Button(manual, text="■ 녹화 종료 + 인코딩",
                                      command=lambda: self.send_manual("stop"), state="disabled")
        self.stop_button.pack(side=LEFT)
        self.cancel_button = ttk.Button(manual, text="취소",
                                        command=lambda: self.send_manual("cancel"), state="disabled")
        self.cancel_button.pack(side=RIGHT)

        # ── 진행 상황 ───────────────────────────────────────
        self.progress = ttk.Progressbar(outer, mode="determinate", maximum=100)
        self.progress.pack(fill=X)
        self.status = StringVar(value="주소를 넣고 '캡쳐 + 인코딩' 을 누르세요.")
        ttk.Label(outer, textvariable=self.status).pack(fill=X, pady=(4, PAD))

        log_frame = ttk.LabelFrame(outer, text="진행 기록", padding=6)
        log_frame.pack(fill=BOTH, expand=True)
        mono = tkfont.nametofont("TkFixedFont").copy()
        mono.configure(size=9)
        self.log_view = Text(log_frame, height=12, wrap="word", font=mono,
                             state="disabled", borderwidth=0, background="#fbfbfd")
        self.log_view.pack(side=LEFT, fill=BOTH, expand=True)
        bar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_view.yview)
        bar.pack(side=RIGHT, fill="y")
        self.log_view.configure(yscrollcommand=bar.set)
        for kind, color in (("ok", "#1a7f37"), ("warn", "#9a6700"), ("error", "#b42318"),
                            ("step", "#0b3d91"), ("info", "#555")):
            self.log_view.tag_configure(kind, foreground=color)

        self.root.after(120, self.drain)

    # ── 로그 ────────────────────────────────────────────────
    def from_thread(self, kind: str, message: str) -> None:
        """작업 스레드에서 불립니다. UI 는 건드리지 않고 큐에만 넣습니다."""
        self.queue.put(("log", (kind, message)))

    def append_log(self, kind: str, message: str) -> None:
        marker = {"ok": "✓", "warn": "!", "error": "✗", "step": "▸"}.get(kind, " ")
        self.log_view.configure(state="normal")
        for line in str(message).splitlines() or [""]:
            self.log_view.insert(END, f"{marker} {line}\n", kind)
            marker = " "
        self.log_view.configure(state="disabled")
        self.log_view.see(END)
        if kind in ("step", "ok"):
            self.status.set(str(message).splitlines()[0])

    def clear_log(self) -> None:
        self.log_view.configure(state="normal")
        self.log_view.delete("1.0", END)
        self.log_view.configure(state="disabled")

    def drain(self) -> None:
        try:
            while True:
                event, payload = self.queue.get_nowait()
                if event == "log":
                    self.append_log(*payload)
                elif event == "progress":
                    self.progress["value"] = payload
                elif event == "done":
                    self.finish(payload)
                elif event == "manual_state":
                    self.set_manual_state(str(payload))
                elif event == "failed":
                    self.finish(None, error=str(payload))
        except queue.Empty:
            pass
        self.root.after(120, self.drain)

    # ── 실행 ────────────────────────────────────────────────
    def start(self, job: str) -> None:
        if self.busy:
            return
        url = self.url.get().strip()
        if job != "render":
            if not url:
                messagebox.showwarning("주소가 없습니다", "홈페이지 주소를 넣어주세요.")
                return
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"
                self.url.set(url)

        self.busy = True
        for button in (self.run_button, self.capture_button, self.render_button):
            button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.progress["value"] = 0
        self.clear_log()

        params = {
            "url": url,
            "caption": self.caption.get().strip(),
            "viewport": VIEWPORTS[self.viewport.get()],
            "scroll_seconds": float(self.scroll.get() or 6),
            "headed": self.headed.get(),
        }
        threading.Thread(target=self.worker, args=(job, params), daemon=True).start()

    # ── 수동 녹화 ───────────────────────────────────────────
    def set_manual_state(self, state: str) -> None:
        """브라우저가 열렸는지/녹화 중인지에 따라 버튼을 켜고 끕니다."""
        self.manual_state = state
        opened = state == "opened"
        recording = state == "recording"
        self.record_button.configure(state="normal" if opened else "disabled")
        self.stop_button.configure(state="normal" if recording else "disabled")
        self.cancel_button.configure(state="normal" if (opened or recording) else "disabled")
        self.open_browser_button.configure(state="disabled" if (opened or recording) else "normal")
        if recording:
            self.status.set("● 녹화 중 — 브라우저에서 보여줄 동작을 하고 '녹화 종료' 를 누르세요.")
        elif opened:
            self.status.set("브라우저가 열렸습니다. 화면을 맞춘 뒤 '녹화 시작' 을 누르세요.")

    def send_manual(self, command: str) -> None:
        if self.manual_commands:
            self.manual_commands.put(command)

    def open_browser(self) -> None:
        """브라우저를 띄우고, 시작·종료 지시를 기다립니다."""
        if self.busy:
            return
        url = self.url.get().strip()
        if not url:
            messagebox.showwarning("주소가 없습니다", "홈페이지 주소를 넣어주세요.")
            return
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
            self.url.set(url)

        self.busy = True
        for button in (self.run_button, self.capture_button, self.render_button):
            button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.open_browser_button.configure(state="disabled")
        self.progress["value"] = 0
        self.clear_log()

        self.manual_commands = queue.Queue()
        params = {
            "url": url,
            "caption": self.caption.get().strip(),
            "viewport": VIEWPORTS[self.viewport.get()],
        }
        threading.Thread(target=self.manual_worker, args=(params,), daemon=True).start()

    def manual_worker(self, params: dict) -> None:
        from . import log, pipeline
        from .capture import RecordingCancelled

        log.set_sink(self.from_thread)
        try:
            options = {
                **params,
                "commands": self.manual_commands,
                "on_state": lambda state: self.queue.put(("manual_state", state)),
            }
            ctx = pipeline.open_run(options)
            pipeline.step_manual_capture(ctx, options)
            self.queue.put(("progress", 60))
            media = pipeline.step_render(ctx, options)
            self.queue.put(("progress", 100))
            self.queue.put(("done", {"dir": ctx.paths.base, "media": media}))
        except RecordingCancelled:
            self.queue.put(("done", None))
        except Exception as exc:  # noqa: BLE001
            self.queue.put(("failed", exc))
        finally:
            log.set_sink(None)
            self.manual_commands = None
            self.queue.put(("manual_state", "idle"))

    def worker(self, job: str, params: dict) -> None:
        """작업 스레드. 여기서만 무거운 모듈을 불러옵니다."""
        from . import log, pipeline

        log.set_sink(self.from_thread)
        try:
            options = {
                **params,
                "simple_capture": True,
                "latest": job == "render",
            }
            ctx = pipeline.open_run(options)

            if job in ("capture", "both"):
                self.queue.put(("progress", 10))
                pipeline.step_capture(ctx, options)
                self.queue.put(("progress", 60))

            media = None
            if job in ("render", "both"):
                media = pipeline.step_render(ctx, options)
            self.queue.put(("progress", 100))
            self.queue.put(("done", {"dir": ctx.paths.base, "media": media}))
        except Exception as exc:  # noqa: BLE001 - 창에 사람이 읽을 메시지로 띄웁니다
            self.queue.put(("failed", exc))
        finally:
            log.set_sink(None)

    def finish(self, payload: dict | None, error: str = "") -> None:
        self.busy = False
        for button in (self.run_button, self.capture_button, self.render_button):
            button.configure(state="normal")

        if error:
            self.progress["value"] = 0
            self.status.set("실패했습니다. 진행 기록을 확인해주세요.")
            self.append_log("error", error)
            messagebox.showerror("실패", error.splitlines()[0])
            return

        if payload is None:      # 수동 녹화 취소
            self.progress["value"] = 0
            self.status.set("취소했습니다. 다시 시작하실 수 있습니다.")
            return

        self.result_dir = Path(payload["dir"])
        self.open_button.configure(state="normal")
        media = payload.get("media") or {}
        if media:
            self.append_log("ok", f"영상: {media['mp4']}")
            self.append_log("ok", f"GIF : {media['gif']}")
            # 로그를 먼저 넣고 마지막에 상태줄을 덮어씁니다 (로그가 상태줄을 갱신하므로).
            self.status.set(f"완료 · 숏츠 {media['duration']:.1f}초 · {self.result_dir.name}")
        else:
            self.status.set(f"캡쳐 완료 · {self.result_dir.name}")

    def open_result(self) -> None:
        if self.result_dir and self.result_dir.exists():
            _open_folder(self.result_dir)


def main() -> int:
    root = Tk()
    try:
        ttk.Style().theme_use("vista" if sys.platform == "win32" else "clam")
    except Exception:  # noqa: BLE001 - 테마가 없으면 기본값으로
        pass
    App(root)
    root.mainloop()
    return 0
