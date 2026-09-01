"""녹화본 + 자막 타임라인 → 세로 숏츠 mp4 와 GIF."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .. import ffmpeg, log
from ..paths import RunPaths, relative
from .cards import caption_html, intro_html, outro_html
from .html2png import RenderJob, render_all


def render_shorts(
    video: str | Path,
    timeline: dict,
    brand: dict,
    render_config: dict,
    paths: RunPaths,
    hook: str,
    sub: str = "",
    cta: str = "",
) -> dict[str, Any]:
    shorts = render_config["shorts"]
    width, height, fps = shorts["width"], shorts["height"], shorts["fps"]
    max_duration = shorts["maxDuration"]
    intro_seconds, outro_seconds = shorts["introSeconds"], shorts["outroSeconds"]

    out_mp4 = paths.render / "shorts.mp4"
    out_gif = paths.render / "preview.gif"
    out_cover = paths.render / "cover.png"

    raw_duration = ffmpeg.duration(video) or timeline.get("duration") or 10.0
    if shorts["speed"] == "auto":
        factor = min(2.5, raw_duration / max_duration) if raw_duration > max_duration else 1.0
    else:
        factor = float(shorts["speed"] or 1)
    raw_limit = min(raw_duration, max_duration * factor)
    body_duration = raw_limit / factor
    total = intro_seconds + body_duration + outro_seconds
    log.info(
        f"원본 {raw_duration:.1f}초 → 배속 {factor:.2f}x → 본편 {body_duration:.1f}초 (총 {total:.1f}초)"
    )

    # ── 1) 오버레이용 PNG 굽기 ────────────────────────────────
    captions = []
    for index, item in enumerate(timeline.get("captions") or []):
        if not item.get("text"):
            continue
        # 배속을 걸었으면 자막 시간도 같이 당겨야 합니다.
        start = min(body_duration, item["start"] / factor)
        end = min(body_duration, (item.get("end") or raw_duration) / factor)
        if end - start <= 0.25:
            continue
        captions.append({
            "text": item["text"], "start": round(start, 3), "end": round(end, 3),
            "file": paths.render / f"caption-{index + 1:02d}.png",
        })

    # 인트로·아웃트로는 초를 0 으로 두면 카드 자체가 빠집니다.
    has_intro = intro_seconds > 0
    has_outro = outro_seconds > 0
    intro_png = paths.render / "intro.png"
    outro_png = paths.render / "outro.png"

    jobs = []
    if has_intro:
        jobs.append(RenderJob(intro_html(hook, sub, brand, width, height), width, height, intro_png))
    if has_outro:
        # 비워두면 그 줄이 안 나오도록, 여기서 기본 문구를 끼워넣지 않습니다.
        jobs.append(RenderJob(outro_html(cta or brand.get("cta") or "", brand, width, height),
                              width, height, outro_png))
    jobs += [
        RenderJob(caption_html(c["text"], width, height, brand), width, height, c["file"], transparent=True)
        for c in captions
    ]
    render_all(jobs)

    # 껐는데 예전 실행의 카드가 남아 있으면 헷갈립니다.
    for used, card in ((has_intro, intro_png), (has_outro, outro_png)):
        if not used:
            card.unlink(missing_ok=True)

    # ── 2) ffmpeg 그래프 조립 ─────────────────────────────────
    # 카드를 빼면 입력 번호가 밀리므로 번호를 만들면서 기억해 둡니다.
    inputs = ["-i", str(video)]
    next_index = 1

    intro_index = None
    if has_intro:
        inputs += ["-loop", "1", "-t", f"{intro_seconds:.3f}", "-i", str(intro_png)]
        intro_index, next_index = next_index, next_index + 1

    outro_index = None
    if has_outro:
        inputs += ["-loop", "1", "-t", f"{outro_seconds:.3f}", "-i", str(outro_png)]
        outro_index, next_index = next_index, next_index + 1

    caption_base = next_index
    for caption in captions:
        inputs += ["-i", str(caption["file"])]
        next_index += 1

    audio_index = next_index
    bgm = Path(shorts["bgm"]).resolve() if shorts.get("bgm") else None
    has_bgm = bool(bgm and bgm.exists())
    if has_bgm:
        inputs += ["-stream_loop", "-1", "-i", str(bgm)]
    else:
        inputs += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    chain = [
        f"[0:v]trim=0:{raw_limit:.3f},setpts=(PTS-STARTPTS)/{factor:.3f},"
        f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
        f"fps={fps},format=rgba[b0]"
    ]
    last = "b0"
    for index, caption in enumerate(captions):
        nxt = f"b{index + 1}"
        chain.append(
            f"[{last}][{caption_base + index}:v]overlay=0:0:"
            f"enable='between(t,{caption['start']},{caption['end']})'[{nxt}]"
        )
        last = nxt

    segments = []
    if has_intro:
        chain.append(f"[{intro_index}:v]scale={width}:{height},fps={fps},format=rgba,"
                     f"fade=t=out:st={max(0.0, intro_seconds - 0.3):.3f}:d=0.3[intro]")
        segments.append("[intro]")
    segments.append(f"[{last}]")
    if has_outro:
        chain.append(f"[{outro_index}:v]scale={width}:{height},fps={fps},format=rgba,"
                     f"fade=t=in:st=0:d=0.3[outro]")
        segments.append("[outro]")

    if len(segments) > 1:
        chain.append(f"{''.join(segments)}concat=n={len(segments)}:v=1:a=0,format=yuv420p[v]")
    else:
        # 카드가 하나도 없으면 본편만 그대로 씁니다 (concat=n=1 은 쓰지 않습니다).
        chain.append(f"[{last}]format=yuv420p[v]")

    chain.append(
        f"[{audio_index}:a]atrim=0:{total:.3f},asetpts=N/SR/TB,volume=0.22,"
        f"afade=t=out:st={max(0.0, total - 1.2):.3f}:d=1.2[a]"
        if has_bgm else f"[{audio_index}:a]anull[a]"
    )

    ffmpeg.run([
        *inputs,
        "-filter_complex", ";".join(chain),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1", "-r", str(fps),
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-t", f"{total:.3f}",
        str(out_mp4),
    ])

    # 표지 이미지: 인트로 카드가 있으면 그걸 쓰고, 없으면 본편 첫 장면에서 뽑습니다.
    if has_intro:
        shutil.copyfile(intro_png, out_cover)
    else:
        ffmpeg.run(["-ss", "0.5", "-i", str(out_mp4), "-frames:v", "1", str(out_cover)])

    log.ok(f"숏츠 mp4 → {relative(out_mp4)}")

    # ── 3) GIF (인트로 다음 구간만) ───────────────────────────
    gif = render_config["gif"]
    ffmpeg.run([
        "-ss", f"{intro_seconds:.3f}", "-t", f"{min(gif['maxDuration'], body_duration):.3f}",
        "-i", str(out_mp4),
        "-vf", (f"fps={gif['fps']},scale={gif['width']}:-2:flags=lanczos,split[a][b];"
                f"[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=3"),
        "-loop", "0",
        str(out_gif),
    ])
    log.ok(f"GIF → {relative(out_gif)}")

    return {"mp4": str(out_mp4), "gif": str(out_gif), "cover": str(out_cover), "duration": total}
