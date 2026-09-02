"""녹화본 + 자막 타임라인 → 세로 숏츠 mp4 와 GIF."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import ffmpeg, log
from ..paths import RunPaths, relative
from .cards import caption_html, intro_html, outro_html
from .html2png import RenderJob, render_all

#: 앞뒤 카드에 쓸 수 있는 이미지 형식
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

#: 채우기로 잘라냈을 때 이만큼도 안 남으면 잘라내지 않고 여백을 둡니다.
FILL_COVERAGE_LIMIT = 0.9


def _fill(width: int, height: int) -> str:
    """짧은 쪽을 맞춰 꽉 채우고 넘치는 부분은 잘라냅니다."""
    return (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}")


def _contain(label_in: str, label_out: str, width: int, height: int) -> list[str]:
    """화면 전체를 넣고 남는 자리는 같은 화면을 흐리게 깔아 채웁니다.

    가로가 긴 화면(데스크톱 등)을 세로 영상에 담을 때 잘라내면 내용이 대부분
    날아갑니다. 검은 띠 대신 흐린 배경을 깔면 덜 허전합니다.
    """
    return [
        f"[{label_in}]split=2[{label_out}_fg][{label_out}_bgsrc]",
        f"[{label_out}_bgsrc]{_fill(width, height)},gblur=sigma=28,"
        f"eq=brightness=-0.18[{label_out}_bg]",
        f"[{label_out}_fg]scale={width}:{height}:force_original_aspect_ratio=decrease[{label_out}_fit]",
        f"[{label_out}_bg][{label_out}_fit]overlay=(W-w)/2:(H-h)/2[{label_out}]",
    ]


def _should_contain(mode: str, source_width: int, source_height: int,
                    width: int, height: int) -> bool:
    """auto 일 때, 잘라내면 너무 많이 날아가는지 보고 정합니다."""
    if mode == "fill":
        return False
    if mode == "contain":
        return True
    if not source_width or not source_height:
        return False
    source_ratio = source_width / source_height
    target_ratio = width / height
    coverage = min(source_ratio / target_ratio, target_ratio / source_ratio)
    return coverage < FILL_COVERAGE_LIMIT


def _card_spec(spec: dict | None) -> dict:
    """설정에서 온 앞/뒤 카드 값을 다루기 쉬운 모양으로 정리합니다."""
    spec = spec or {}
    return {
        "text": (spec.get("text") or "").strip(),
        "image": (spec.get("image") or "").strip(),
        "seconds": float(spec.get("seconds") or 0),
    }


def _prepare_card(spec: dict, kind: str, brand: dict, width: int, height: int,
                  out_png: Path, jobs: list) -> dict | None:
    """카드 하나를 준비합니다.

    - 이미지가 지정돼 있으면 그 파일을 그대로 씁니다 (직접 만든 카드).
    - 아니면 문구로 카드를 그립니다.
    - 문구도 이미지도 없으면 그 카드는 붙이지 않습니다.
    """
    if spec["seconds"] <= 0 or not (spec["text"] or spec["image"]):
        out_png.unlink(missing_ok=True)      # 껐는데 예전 실행의 카드가 남으면 헷갈립니다
        return None

    if spec["image"]:
        source = Path(spec["image"]).expanduser()
        if not source.exists():
            log.warn(f"{kind} 카드 이미지를 찾을 수 없습니다: {source}")
            if not spec["text"]:
                return None
            log.info("  문구로 카드를 만듭니다.")
        elif source.suffix.lower() not in IMAGE_SUFFIXES:
            log.warn(f"{kind} 카드 이미지 형식을 알 수 없습니다: {source.suffix}")
            return None
        else:
            out_png.unlink(missing_ok=True)
            return {"path": source, "seconds": spec["seconds"], "from_image": True}

    html = (
        intro_html(spec["text"], "", brand, width, height) if kind == "앞"
        else outro_html(spec["text"], brand, width, height)
    )
    jobs.append(RenderJob(html, width, height, out_png))
    return {"path": out_png, "seconds": spec["seconds"], "from_image": False}


def render_shorts(
    video: str | Path,
    timeline: dict,
    brand: dict,
    render_config: dict,
    paths: RunPaths,
    intro: dict | None = None,
    outro: dict | None = None,
) -> dict[str, Any]:
    shorts = render_config["shorts"]
    width, height, fps = shorts["width"], shorts["height"], shorts["fps"]
    max_duration = shorts["maxDuration"]

    out_mp4 = paths.render / "shorts.mp4"
    out_gif = paths.render / "preview.gif"
    out_cover = paths.render / "cover.png"

    # 녹화 화면이 세로 규격과 많이 다르면 잘라내지 않고 여백을 둡니다.
    fit_mode = (shorts.get("fit") or "auto").lower()
    source_width, source_height = ffmpeg.dimensions(video)
    body_contain = _should_contain(fit_mode, source_width, source_height, width, height)
    if body_contain and fit_mode == "auto":
        log.info(f"녹화 화면 {source_width}x{source_height} 이 세로 규격과 달라 "
                 "잘라내지 않고 흐린 여백을 둡니다 (설정 render.shorts.fit).")

    raw_duration = ffmpeg.duration(video) or timeline.get("duration") or 10.0
    if shorts["speed"] == "auto":
        factor = min(2.5, raw_duration / max_duration) if raw_duration > max_duration else 1.0
    else:
        factor = float(shorts["speed"] or 1)
    raw_limit = min(raw_duration, max_duration * factor)
    body_duration = raw_limit / factor

    # ── 1) 자막과 앞뒤 카드 준비 ──────────────────────────────
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

    jobs: list[RenderJob] = []
    intro_card = _prepare_card(_card_spec(intro), "앞", brand, width, height,
                               paths.render / "intro.png", jobs)
    outro_card = _prepare_card(_card_spec(outro), "뒤", brand, width, height,
                               paths.render / "outro.png", jobs)
    jobs += [
        RenderJob(caption_html(c["text"], width, height, brand), width, height, c["file"], transparent=True)
        for c in captions
    ]
    render_all(jobs)

    intro_seconds = intro_card["seconds"] if intro_card else 0.0
    outro_seconds = outro_card["seconds"] if outro_card else 0.0
    total = intro_seconds + body_duration + outro_seconds
    cards = " + ".join(
        part for part in (
            f"앞 {intro_seconds:.1f}초" if intro_card else "",
            f"본편 {body_duration:.1f}초",
            f"뒤 {outro_seconds:.1f}초" if outro_card else "",
        ) if part
    )
    log.info(f"원본 {raw_duration:.1f}초 → 배속 {factor:.2f}x → {cards} (총 {total:.1f}초)")

    # ── 2) ffmpeg 그래프 조립 ─────────────────────────────────
    # 카드를 빼면 입력 번호가 밀리므로 번호를 만들면서 기억해 둡니다.
    inputs = ["-i", str(video)]
    next_index = 1

    intro_index = outro_index = None
    for card, setter in ((intro_card, "intro"), (outro_card, "outro")):
        if not card:
            continue
        inputs += ["-loop", "1", "-t", f"{card['seconds']:.3f}", "-i", str(card["path"])]
        if setter == "intro":
            intro_index = next_index
        else:
            outro_index = next_index
        next_index += 1

    caption_base = next_index
    for caption in captions:
        inputs += ["-i", str(caption["file"])]
        next_index += 1

    audio_index = next_index
    bgm = Path(shorts["bgm"]).expanduser() if shorts.get("bgm") else None
    has_bgm = bool(bgm and bgm.exists())
    if has_bgm:
        inputs += ["-stream_loop", "-1", "-i", str(bgm)]
    else:
        inputs += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    chain = []
    if body_contain:
        chain.append(f"[0:v]trim=0:{raw_limit:.3f},setpts=(PTS-STARTPTS)/{factor:.3f},fps={fps}[body_src]")
        chain += _contain("body_src", "body_fit", width, height)
        chain.append("[body_fit]format=rgba[b0]")
    else:
        chain.append(
            f"[0:v]trim=0:{raw_limit:.3f},setpts=(PTS-STARTPTS)/{factor:.3f},"
            f"{_fill(width, height)},fps={fps},format=rgba[b0]"
        )
    last = "b0"
    for index, caption in enumerate(captions):
        nxt = f"b{index + 1}"
        chain.append(
            f"[{last}][{caption_base + index}:v]overlay=0:0:"
            f"enable='between(t,{caption['start']},{caption['end']})'[{nxt}]"
        )
        last = nxt

    # 직접 넣은 이미지는 비율이 제각각입니다. fill 로 못박지 않은 이상,
    # 디자인이 잘리지 않게 전체를 넣고 남는 자리는 흐린 배경으로 채웁니다.
    card_fill = fit_mode == "fill"

    def card_chain(index: int, name: str, fade: str) -> None:
        if card_fill:
            chain.append(f"[{index}:v]{_fill(width, height)},fps={fps},format=rgba,{fade}[{name}]")
            return
        chain.append(f"[{index}:v]fps={fps}[{name}_src]")
        chain.extend(_contain(f"{name}_src", f"{name}_fit", width, height))
        chain.append(f"[{name}_fit]format=rgba,{fade}[{name}]")

    segments = []
    if intro_card:
        card_chain(intro_index, "intro",
                   f"fade=t=out:st={max(0.0, intro_seconds - 0.3):.3f}:d=0.3")
        segments.append("[intro]")
    segments.append(f"[{last}]")
    if outro_card:
        card_chain(outro_index, "outro", "fade=t=in:st=0:d=0.3")
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
    log.ok(f"숏츠 mp4 → {relative(out_mp4)}")

    # 표지 이미지는 완성된 영상에서 뽑습니다 (카드가 있든 없든 항상 맞습니다).
    ffmpeg.run(["-ss", "0.5", "-i", str(out_mp4), "-frames:v", "1", str(out_cover)])

    # ── 3) GIF (앞 카드 다음 구간만) ──────────────────────────
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
