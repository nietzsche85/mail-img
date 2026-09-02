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
from tkinter import (
    BOTH, END, LEFT, RIGHT, W, X,
    BooleanVar, StringVar, Text, Tk, Toplevel, filedialog, messagebox,
)
from tkinter import font as tkfont
from tkinter import ttk

from .capture.clicks import CSS, VIDEO, ClickSpecError, normalize_clicks, video_size, viewport_size
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
        self.picker_commands: "queue.Queue[str] | None" = None
        #: 직접 지정한 클릭들. 항상 브라우저 화면(CSS) 기준으로만 들고 있습니다.
        self.clicks: list[dict] = []

        root.title("SNS 오토파일럿")
        root.minsize(720, 780)

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

        ttk.Label(form, text="영상 자막").grid(row=1, column=0, sticky=W, pady=4)
        self.caption = StringVar()
        ttk.Entry(form, textvariable=self.caption).grid(
            row=1, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=4
        )
        ttk.Label(form, text="녹화 화면 위에 깔리는 문구입니다. **강조** 를 쓰면 포인트 색으로 나옵니다. 비워도 됩니다.",
                  foreground="#666").grid(row=2, column=1, columnspan=3, sticky=W, padx=(8, 0))

        ttk.Label(form, text="화면 크기").grid(row=3, column=0, sticky=W, pady=(10, 4))
        self.viewport = StringVar(value=list(VIEWPORTS)[0])
        viewport_box = ttk.Combobox(form, textvariable=self.viewport, values=list(VIEWPORTS),
                                    state="readonly", width=18)
        viewport_box.grid(row=3, column=1, sticky=W, padx=(8, 0), pady=(10, 4))
        # 화면 크기가 바뀌면 좌표 기준도 바뀌므로 안내와 검사를 다시 합니다.
        viewport_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_size_hint())

        ttk.Label(form, text="스크롤 시간").grid(row=3, column=2, sticky=W, padx=(16, 0), pady=(10, 4))
        self.scroll = StringVar(value="6")
        ttk.Spinbox(form, from_=1, to=30, width=5, textvariable=self.scroll).grid(
            row=3, column=3, sticky=W, padx=(8, 0), pady=(10, 4)
        )

        ttk.Label(form, text="브라우저 창 크기입니다. 결과물은 항상 1080×1920 세로예요. "
                             "가로가 긴 화면은 잘리지 않게 위아래 여백이 생깁니다.",
                  foreground="#666").grid(row=4, column=1, columnspan=3, sticky=W, padx=(8, 0))

        self.headed = BooleanVar(value=False)
        ttk.Checkbutton(form, text="브라우저 창을 띄워서 진행 보기", variable=self.headed).grid(
            row=5, column=1, columnspan=3, sticky=W, padx=(8, 0), pady=(6, 0)
        )

        # ── 앞뒤 카드 ───────────────────────────────────────
        cards = ttk.LabelFrame(outer, text="앞뒤 카드 (비워두면 카드 없이 녹화 화면만 나갑니다)", padding=PAD)
        cards.pack(fill=X, pady=(PAD, 0))
        cards.columnconfigure(1, weight=1)
        ttk.Label(cards, text="문구를 적거나 직접 만든 이미지를 고르세요. 이미지를 고르면 문구 대신 그 이미지가 쓰입니다.",
                  foreground="#666").grid(row=0, column=0, columnspan=6, sticky=W, pady=(0, 8))

        self.card_vars = {}
        for row, (key, label, default_seconds) in enumerate(
            (("intro", "앞 카드", "1.6"), ("outro", "뒤 카드", "2.0")), start=1
        ):
            ttk.Label(cards, text=label).grid(row=row, column=0, sticky=W, pady=4)
            text_var = StringVar()
            ttk.Entry(cards, textvariable=text_var).grid(row=row, column=1, sticky="ew", padx=(8, 8), pady=4)

            image_var = StringVar()
            name_var = StringVar(value="이미지 없음")
            ttk.Button(cards, text="이미지…", width=9,
                       command=lambda k=key: self.pick_image(k)).grid(row=row, column=2, pady=4)
            ttk.Label(cards, textvariable=name_var, foreground="#444", width=18).grid(
                row=row, column=3, sticky=W, padx=(8, 0), pady=4
            )
            ttk.Button(cards, text="지우기", width=7,
                       command=lambda k=key: self.clear_image(k)).grid(row=row, column=4, pady=4)

            seconds_var = StringVar(value=default_seconds)
            ttk.Spinbox(cards, from_=0.5, to=10, increment=0.1, width=5,
                        textvariable=seconds_var).grid(row=row, column=5, sticky=W, padx=(12, 2), pady=4)
            ttk.Label(cards, text="초").grid(row=row, column=6, sticky=W, pady=4)

            self.card_vars[key] = {"text": text_var, "image": image_var,
                                   "name": name_var, "seconds": seconds_var}

        # ── 클릭 지정 ───────────────────────────────────────
        clicks = ttk.LabelFrame(
            outer, text="클릭 지정 (자동으로 찾아 누르는 대신, 누를 자리를 직접 정하기)", padding=PAD
        )
        clicks.pack(fill=X, pady=(PAD, 0))
        clicks.columnconfigure(0, weight=1)

        toggles = ttk.Frame(clicks)
        toggles.grid(row=0, column=0, sticky="ew")
        self.auto_dismiss = BooleanVar(value=True)
        ttk.Checkbutton(toggles, text="팝업 자동 닫기 (동의·확인·닫기 버튼을 찾아서 누름)",
                        variable=self.auto_dismiss).pack(side=LEFT)
        self.use_clicks = BooleanVar(value=False)
        ttk.Checkbutton(toggles, text="아래 좌표를 직접 클릭", variable=self.use_clicks,
                        command=self.refresh_size_hint).pack(side=LEFT, padx=(18, 0))

        table = ttk.Frame(clicks)
        table.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        table.columnconfigure(0, weight=1)
        self.click_table = ttk.Treeview(
            table, columns=("no", "at", "x", "y", "scroll"), show="headings", height=4,
            selectmode="browse",
        )
        for column, title, width, anchor_at in (
            ("no", "#", 40, "center"),
            ("at", "시각(초)", 90, "e"),
            ("x", "X", 80, "e"),
            ("y", "Y", 80, "e"),
            ("scroll", "스크롤", 90, "e"),
        ):
            self.click_table.heading(column, text=title)
            self.click_table.column(column, width=width, anchor=anchor_at, stretch=False)
        self.click_table.grid(row=0, column=0, sticky="ew")
        self.click_table.bind("<Double-1>", lambda _event: self.edit_click())
        table_bar = ttk.Scrollbar(table, orient="vertical", command=self.click_table.yview)
        table_bar.grid(row=0, column=1, sticky="ns")
        self.click_table.configure(yscrollcommand=table_bar.set)

        click_buttons = ttk.Frame(clicks)
        click_buttons.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.pick_button = ttk.Button(click_buttons, text="좌표 찍기…", command=self.pick_coords)
        self.pick_button.pack(side=LEFT)
        self.pick_done_button = ttk.Button(click_buttons, text="찍기 완료", state="disabled",
                                           command=lambda: self.send_picker("done"))
        self.pick_done_button.pack(side=LEFT, padx=6)
        self.pick_cancel_button = ttk.Button(click_buttons, text="찍기 취소", state="disabled",
                                             command=lambda: self.send_picker("cancel"))
        self.pick_cancel_button.pack(side=LEFT)
        ttk.Button(click_buttons, text="모두 지우기", command=self.clear_clicks).pack(side=RIGHT)
        ttk.Button(click_buttons, text="삭제", command=self.remove_click).pack(side=RIGHT, padx=6)
        ttk.Button(click_buttons, text="수정", command=self.edit_click).pack(side=RIGHT)
        ttk.Button(click_buttons, text="직접 추가", command=self.add_click).pack(side=RIGHT, padx=6)

        self.size_hint = StringVar()
        self.size_hint_label = ttk.Label(clicks, textvariable=self.size_hint,
                                         foreground="#666", wraplength=660, justify=LEFT)
        self.size_hint_label.grid(row=3, column=0, sticky=W, pady=(8, 0))

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

        # 무언가 도는 동안 같이 잠기는 버튼들
        self.job_buttons = (self.run_button, self.capture_button,
                            self.render_button, self.pick_button)
        self.refresh_click_table()
        self.root.after(120, self.drain)

    # ── 앞뒤 카드 이미지 ────────────────────────────────────
    def pick_image(self, key: str) -> None:
        path = filedialog.askopenfilename(
            title=f"{'앞' if key == 'intro' else '뒤'} 카드에 쓸 이미지",
            filetypes=[("이미지", "*.png *.jpg *.jpeg *.webp *.bmp"), ("모든 파일", "*.*")],
        )
        if not path:
            return
        self.card_vars[key]["image"].set(path)
        self.card_vars[key]["name"].set(Path(path).name)

    def clear_image(self, key: str) -> None:
        self.card_vars[key]["image"].set("")
        self.card_vars[key]["name"].set("이미지 없음")

    def card_params(self) -> dict:
        """앞뒤 카드 입력을 파이프라인이 쓰는 키로 바꿉니다."""
        params = {}
        for key, group in self.card_vars.items():
            params[f"{key}_text"] = group["text"].get().strip()
            params[f"{key}_image"] = group["image"].get().strip()
            params[f"{key}_seconds"] = float(group["seconds"].get() or 0)
        return params

    # ── 클릭 지정 ───────────────────────────────────────────
    def current_viewport(self) -> dict:
        return VIEWPORTS[self.viewport.get()]

    def refresh_size_hint(self) -> None:
        """좌표의 기준과, 지금 목록이 그 기준에 맞는지 알려줍니다."""
        view = self.current_viewport()
        width, height, scale = viewport_size(view)
        video_width, video_height = video_size(view)

        lines = [f"좌표는 브라우저 화면 {width}×{height} 기준입니다 (왼쪽 위가 0, 0)."]
        if scale > 1:
            lines.append(
                f"완성된 영상은 {video_width}×{video_height} 라서, 영상에서 잰 값을 그대로 넣으면 "
                f"{scale}배 어긋납니다 — '직접 추가' 창에서 좌표 기준을 '영상 픽셀' 로 고르면 알아서 환산합니다."
            )
        lines.append("시각은 녹화가 시작된 뒤 몇 초인지입니다 (페이지 여는 시간 포함).")

        # 실제로 쓰이는 좌표만 따집니다 — 꺼둔 목록까지 빨갛게 경고하면 헷갈립니다.
        problem = ""
        if self.use_clicks.get():
            if not self.clicks:
                lines.append("목록이 비어 있어 아무 데도 누르지 않습니다.")
            try:
                normalize_clicks(self.clicks, view)
            except ClickSpecError as exc:
                problem = str(exc).splitlines()[0]

        if problem:
            self.size_hint.set(problem + "\n" + lines[0])
            self.size_hint_label.configure(foreground="#b42318")
        else:
            self.size_hint.set("\n".join(lines))
            self.size_hint_label.configure(foreground="#666")

    def refresh_click_table(self) -> None:
        self.clicks.sort(key=lambda click: click["at"])
        self.click_table.delete(*self.click_table.get_children())
        for index, click in enumerate(self.clicks, start=1):
            self.click_table.insert(
                "", END, iid=str(index - 1),
                values=(index, f"{click['at']:.1f}", f"{click['x']:.0f}",
                        f"{click['y']:.0f}", f"{click.get('scrollY', 0):.0f}"),
            )
        self.refresh_size_hint()

    def selected_click(self) -> int | None:
        selection = self.click_table.selection()
        return int(selection[0]) if selection else None

    def click_dialog(self, title: str, initial: dict | None = None) -> dict | None:
        """시각·좌표를 넣는 작은 창. 확인을 누를 때 그 자리에서 검사합니다."""
        view = self.current_viewport()
        width, height, scale = viewport_size(view)
        video_width, video_height = video_size(view)

        dialog = Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.resizable(False, False)

        body = ttk.Frame(dialog, padding=PAD)
        body.pack(fill=BOTH, expand=True)

        fields = {
            "at": StringVar(value=f"{(initial or {}).get('at', 3.0):.1f}"),
            "x": StringVar(value=f"{(initial or {}).get('x', width // 2):.0f}"),
            "y": StringVar(value=f"{(initial or {}).get('y', height // 2):.0f}"),
            "scrollY": StringVar(value=f"{(initial or {}).get('scrollY', 0):.0f}"),
        }
        for row, (key, label) in enumerate(
            (("at", "시각 (초)"), ("x", "X"), ("y", "Y"), ("scrollY", "스크롤 (px)"))
        ):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky=W, pady=4)
            ttk.Entry(body, textvariable=fields[key], width=12).grid(
                row=row, column=1, sticky=W, padx=(10, 0), pady=4
            )

        basis = StringVar(value=CSS)
        ttk.Label(body, text="좌표 기준").grid(row=4, column=0, sticky=W, pady=(10, 4))
        basis_frame = ttk.Frame(body)
        basis_frame.grid(row=4, column=1, sticky=W, padx=(10, 0), pady=(10, 4))
        ttk.Radiobutton(basis_frame, text=f"브라우저 {width}×{height}",
                        variable=basis, value=CSS).pack(anchor=W)
        ttk.Radiobutton(basis_frame, text=f"영상 {video_width}×{video_height}",
                        variable=basis, value=VIDEO,
                        state="normal" if scale > 1 else "disabled").pack(anchor=W)

        ttk.Label(body, text="스크롤은 '페이지를 몇 px 내린 상태의 화면인지' 입니다.\n"
                             "0 이면 맨 위 화면 기준이에요. '좌표 찍기' 로 넣으면 자동으로 채워집니다.",
                  foreground="#666").grid(row=5, column=0, columnspan=2, sticky=W, pady=(6, 0))

        error = StringVar()
        ttk.Label(body, textvariable=error, foreground="#b42318", wraplength=340,
                  justify=LEFT).grid(row=6, column=0, columnspan=2, sticky=W, pady=(6, 0))

        result: dict = {}

        def confirm() -> None:
            candidate = {key: var.get() for key, var in fields.items()}
            candidate["basis"] = basis.get()
            try:
                checked = normalize_clicks([candidate], view)[0]
            except ClickSpecError as exc:
                error.set(str(exc))
                return
            result.update(checked)
            dialog.destroy()

        row = ttk.Frame(body)
        row.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(row, text="확인", command=confirm).pack(side=RIGHT)
        ttk.Button(row, text="취소", command=dialog.destroy).pack(side=RIGHT, padx=6)
        dialog.bind("<Return>", lambda _event: confirm())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())

        dialog.grab_set()
        self.root.wait_window(dialog)
        return result or None

    def add_click(self) -> None:
        click = self.click_dialog("클릭 추가")
        if not click:
            return
        self.clicks.append(click)
        self.use_clicks.set(True)
        self.refresh_click_table()

    def edit_click(self) -> None:
        index = self.selected_click()
        if index is None:
            messagebox.showinfo("고른 줄이 없습니다", "수정할 줄을 먼저 눌러주세요.")
            return
        click = self.click_dialog("클릭 수정", self.clicks[index])
        if not click:
            return
        self.clicks[index] = click
        self.refresh_click_table()

    def remove_click(self) -> None:
        index = self.selected_click()
        if index is None:
            messagebox.showinfo("고른 줄이 없습니다", "지울 줄을 먼저 눌러주세요.")
            return
        self.clicks.pop(index)
        self.refresh_click_table()

    def clear_clicks(self) -> None:
        self.clicks.clear()
        self.use_clicks.set(False)
        self.refresh_click_table()

    def click_params(self) -> dict:
        """녹화에 넘길 클릭 설정. 끄면 좌표를 아예 넘기지 않습니다."""
        return {
            "clicks": [dict(click) for click in self.clicks] if self.use_clicks.get() else [],
            "auto_dismiss": self.auto_dismiss.get(),
        }

    # ── 좌표 찍기 ───────────────────────────────────────────
    def send_picker(self, command: str) -> None:
        if self.picker_commands:
            self.picker_commands.put(command)

    def set_picker_state(self, state: str) -> None:
        picking = state == "picking"
        self.pick_done_button.configure(state="normal" if picking else "disabled")
        self.pick_cancel_button.configure(state="normal" if picking else "disabled")
        if picking:
            self.status.set("좌표 찍기 — 브라우저에서 누를 자리를 클릭한 뒤 '찍기 완료' 를 누르세요.")
        else:
            self.busy = False
            for button in self.job_buttons:
                button.configure(state="normal")

    def pick_coords(self) -> None:
        """녹화와 같은 창 크기로 브라우저를 열고, 누른 자리의 좌표를 받아옵니다."""
        if self.busy:
            return
        url = self.require_url()
        if not url:
            return

        self.busy = True
        for button in self.job_buttons:
            button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.clear_log()

        self.picker_commands = queue.Queue()
        params = {"url": url, "viewport": self.current_viewport()}
        threading.Thread(target=self.picker_worker, args=(params,), daemon=True).start()

    def picker_worker(self, params: dict) -> None:
        from . import log, pipeline

        log.set_sink(self.from_thread)
        try:
            points = pipeline.step_pick_points({
                **params,
                "commands": self.picker_commands,
                "on_state": lambda state: self.queue.put(("picker_state", state)),
            })
            self.queue.put(("picked", points))
        except Exception as exc:  # noqa: BLE001
            self.queue.put(("failed", exc))
        finally:
            log.set_sink(None)
            self.picker_commands = None
            self.queue.put(("picker_state", "idle"))

    def apply_picked(self, points: list[dict]) -> None:
        """찍은 좌표를 목록에 넣습니다. 시각은 2초 간격으로 임시로 매겨 둡니다."""
        if not points:
            return
        base = max((click["at"] for click in self.clicks), default=1.0)
        for order, point in enumerate(points, start=1):
            self.clicks.append({
                "at": round(base + 2.0 * order, 1),
                "x": float(point["x"]),
                "y": float(point["y"]),
                "scrollY": float(point.get("scrollY") or 0),
            })
        self.use_clicks.set(True)
        self.refresh_click_table()
        self.append_log("ok", f"좌표 {len(points)}개를 목록에 넣었습니다.")
        self.append_log("info", "시각은 2초 간격으로 임시로 매겼습니다 — 줄을 두 번 누르면 고칠 수 있어요.")

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
                elif event == "picker_state":
                    self.set_picker_state(str(payload))
                elif event == "picked":
                    self.apply_picked(list(payload or []))
                elif event == "failed":
                    self.finish(None, error=str(payload))
        except queue.Empty:
            pass
        self.root.after(120, self.drain)

    # ── 실행 ────────────────────────────────────────────────
    def require_url(self) -> str:
        """주소칸을 확인하고, http 가 빠졌으면 붙여서 돌려줍니다."""
        url = self.url.get().strip()
        if not url:
            messagebox.showwarning("주소가 없습니다", "홈페이지 주소를 넣어주세요.")
            return ""
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
            self.url.set(url)
        return url

    def start(self, job: str) -> None:
        if self.busy:
            return
        url = self.url.get().strip()
        if job != "render":
            url = self.require_url()
            if not url:
                return

        # 브라우저를 띄우기 전에 좌표부터 검사합니다 — 틀린 채로 녹화하면 시간만 버립니다.
        params_clicks = self.click_params()
        try:
            params_clicks["clicks"] = normalize_clicks(params_clicks["clicks"], self.current_viewport())
        except ClickSpecError as exc:
            messagebox.showerror("클릭 좌표를 확인해주세요", str(exc))
            self.refresh_size_hint()
            return

        self.busy = True
        for button in self.job_buttons:
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
            **self.card_params(),
            **params_clicks,
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
        url = self.require_url()
        if not url:
            return

        self.busy = True
        for button in self.job_buttons:
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
            **self.card_params(),
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
        for button in self.job_buttons:
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
