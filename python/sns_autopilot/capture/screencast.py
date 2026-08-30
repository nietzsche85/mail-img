"""CDP 화면 캐스트로 실제 디바이스 픽셀 프레임을 받아 mp4 로 묶습니다.

Playwright 내장 녹화는 CSS 픽셀 크기로만 저장돼서 세로 영상으로 확대하면 뿌옇게 나옵니다.
대신 CDP `Page.startScreencast` 로 1080x1920 프레임을 직접 받습니다.
"""
from __future__ import annotations

import base64
import bisect
import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import ffmpeg, log


@dataclass
class Frame:
    file: Path
    ts: float   # 프레임이 실제로 그려진 시각(epoch 초). 핸들러 실행 시각과 무관해 믿을 수 있습니다.


@dataclass
class Screencast:
    page: object
    dir: Path
    frames: list[Frame] = field(default_factory=list)
    client: object | None = None
    video_duration: float = 0.0
    _wall_axis: list[float] = field(default_factory=list)
    _video_axis: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.dir = Path(self.dir) / "frames"

    def start(self, max_width: int, max_height: int, quality: int = 92) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.client = self.page.context.new_cdp_session(self.page)
        self.client.on("Page.screencastFrame", self._on_frame)
        self.client.send(
            "Page.startScreencast",
            {"format": "jpeg", "quality": quality, "maxWidth": max_width,
             "maxHeight": max_height, "everyNthFrame": 1},
        )

    def _on_frame(self, frame: dict) -> None:
        file = self.dir / f"f_{len(self.frames):06d}.jpg"
        file.write_bytes(base64.b64decode(frame["data"]))
        metadata = frame.get("metadata") or {}
        self.frames.append(Frame(file=file, ts=metadata.get("timestamp") or time.time()))
        try:
            self.client.send("Page.screencastFrameAck", {"sessionId": frame["sessionId"]})
        except Exception:  # noqa: BLE001 - 페이지가 이미 닫혔으면 무시
            pass

    def stop(self) -> None:
        try:
            if self.client:
                self.client.send("Page.stopScreencast")
        except Exception:  # noqa: BLE001 - 이미 정리됨
            pass

    def assemble(self, out_file: Path, width: int, height: int, fps: int = 30, t0: float = 0.0) -> Path | None:
        """프레임마다 실제 간격을 살려 mp4 로 묶고, 자막용 시간 대응표를 만듭니다.

        화면이 안 바뀌면 프레임이 오지 않으므로 영상 길이는 실제 조작 시간보다 짧습니다.
        그래서 "실제 시각 → 영상 시각" 축을 함께 기록해 둡니다.
        """
        if len(self.frames) < 5:
            return None

        list_file = self.dir / "frames.txt"
        lines = ["ffconcat version 1.0"]
        cursor = 0.0
        self._wall_axis.clear()
        self._video_axis.clear()
        for index, frame in enumerate(self.frames):
            nxt = self.frames[index + 1] if index + 1 < len(self.frames) else None
            gap = min(2.0, max(1 / 60, nxt.ts - frame.ts)) if nxt else 1 / fps
            self._wall_axis.append(frame.ts - t0)
            self._video_axis.append(cursor)
            cursor += gap
            lines.append(f"file '{frame.file.name}'")
            lines.append(f"duration {gap:.4f}")
        lines.append(f"file '{self.frames[-1].file.name}'")
        list_file.write_text("\n".join(lines), encoding="utf-8")
        self.video_duration = cursor

        # fps 필터는 여기서 쓰지 않습니다. 화면이 멈춰 있던 구간(긴 duration)을 만나면
        # 앞부분을 통째로 버리고 start 를 밀어버려 영상 뒷부분이 잘립니다.
        # 프레임 간격을 그대로 살린 VFR 로 두고, 30fps 변환은 렌더 단계에서 합니다.
        ffmpeg.run([
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-vf", (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"),
            "-fps_mode", "vfr",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            str(out_file),
        ])
        log.info(f"화면 캐스트 {len(self.frames)}프레임 → {out_file.name} ({cursor:.1f}초)")
        return out_file

    def map_time(self, wall_seconds: float) -> float:
        """녹화 시작 후 n초(실제 시각)가 영상에서는 몇 초인지 환산합니다."""
        axis = self._wall_axis
        if not axis:
            return wall_seconds
        if wall_seconds <= axis[0]:
            return 0.0
        if wall_seconds >= axis[-1]:
            return self.video_duration
        hi = bisect.bisect_right(axis, wall_seconds)
        lo = hi - 1
        span = axis[hi] - axis[lo]
        ratio = (wall_seconds - axis[lo]) / span if span > 0 else 0.0
        return self._video_axis[lo] + (self._video_axis[hi] - self._video_axis[lo]) * ratio
