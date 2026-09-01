"""단계 조립. 실행 폴더의 manifest.json 으로 단계 사이를 이어붙입니다."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import log
from .analyze import collect_articles
from .capture import capture, record_manually, simple_flow
from .config import load_config, load_yaml, resolve
from .generate import generate_copy, generate_images
from .paths import RunPaths, latest_run, new_run_id, read_json, write_json
from .publish import publish
from .render import render_shorts


@dataclass
class Context:
    config: dict
    paths: RunPaths

    @property
    def run_id(self) -> str:
        return self.paths.run_id

    def manifest(self) -> dict:
        return read_json(self.paths.manifest, {}) or {}

    def save(self, **patch: Any) -> None:
        write_json(self.paths.manifest, {**self.manifest(), **patch})


def open_run(options: dict) -> Context:
    config = load_config(options.get("config") or "config/pipeline.yaml")
    run_id = options.get("run")
    if not run_id and options.get("latest"):
        # 이어받을 실행이 없으면 새로 만듭니다 (처음 쓰는 사람이 막히지 않게).
        run_id = latest_run()
    return Context(config=config, paths=RunPaths.create(run_id or new_run_id()))


# ── 개별 단계 ──────────────────────────────────────────────

def step_capture(ctx: Context, options: dict) -> dict:
    # 주소만 주고 시나리오 파일이 없으면 "들어가서 훑어보는" 기본 시나리오를 만듭니다.
    if options.get("simple_capture") and options.get("url"):
        flow = simple_flow(
            options["url"],
            caption=options.get("caption") or "",
            scroll_seconds=float(options.get("scroll_seconds") or 6.0),
            viewport=options.get("viewport"),
        )
        flow_file = "(주소로 만든 기본 시나리오)"
    else:
        flow_file = options.get("flow") or ctx.config["capture"]["flow"]
        flow = load_yaml(flow_file)
        if options.get("url"):
            flow["url"] = options["url"]

    result = capture(flow, ctx.paths, headless=not options.get("headed"))
    ctx.save(flow=str(flow_file), video=result["video"],
             timeline=result["timeline"], shots=result["shots"])
    return result


def step_manual_capture(ctx: Context, options: dict) -> dict:
    """브라우저를 띄워 두고 사람이 시작·종료를 누르는 녹화."""
    result = record_manually(
        url=options.get("url") or "",
        paths=ctx.paths,
        viewport=options.get("viewport"),
        caption=options.get("caption") or "",
        commands=options.get("commands"),
        on_state=options.get("on_state"),
    )
    ctx.save(flow="(수동 녹화)", video=result["video"],
             timeline=result["timeline"], shots=result["shots"])
    return result


def step_analyze(ctx: Context, options: dict) -> tuple[list[dict], Callable[[], None]]:
    blog = dict(ctx.config["blog"])
    if options.get("url"):
        blog["urls"], blog["feed"] = [options["url"]], ""
    if options.get("feed"):
        blog["feed"] = options["feed"]
    articles, commit = collect_articles(blog)
    ctx.save(articles=articles)
    return articles, commit


def step_copy(ctx: Context, options: dict) -> dict:
    manifest = ctx.manifest()
    articles = manifest.get("articles") or []
    index = options.get("article_index", 0)
    article = articles[index] if index < len(articles) else None
    if not article and not manifest.get("timeline"):
        raise RuntimeError("분석한 블로그 글도, 녹화본도 없습니다. analyze 또는 capture 를 먼저 실행하세요.")

    copy = generate_copy(
        article=article, timeline=manifest.get("timeline"),
        brand=ctx.config["brand"], copy_config=ctx.config["copy"], paths=ctx.paths,
    )
    ctx.save(copy=copy)
    return copy


def _card_options(options: dict, config_block: dict | None, prefix: str) -> dict:
    """설정의 앞/뒤 카드 값에 창(GUI)에서 넣은 값을 덮어씁니다."""
    block = dict(config_block or {})
    for key in ("text", "image", "seconds"):
        value = options.get(f"{prefix}_{key}")
        if value not in (None, ""):
            block[key] = value
    return block


def step_render(ctx: Context, options: dict | None = None) -> dict:
    options = options or {}
    manifest = ctx.manifest()
    video = manifest.get("video")
    if not video or not Path(video).exists():
        raise RuntimeError("녹화본이 없습니다. 먼저 capture 를 실행하세요.")

    shorts = ctx.config["render"]["shorts"]
    media = render_shorts(
        video=video,
        timeline=manifest.get("timeline") or {"captions": [], "duration": 0},
        brand=ctx.config["brand"],
        render_config=ctx.config["render"],
        paths=ctx.paths,
        # 앞뒤 카드는 직접 넣은 문구나 이미지가 있을 때만 붙습니다.
        intro=_card_options(options, shorts.get("intro"), "intro"),
        outro=_card_options(options, shorts.get("outro"), "outro"),
    )
    ctx.save(media={**(manifest.get("media") or {}), **media})
    return media


def step_image(ctx: Context) -> dict[str, str]:
    manifest = ctx.manifest()
    if not manifest.get("copy"):
        raise RuntimeError("카피가 없습니다. 먼저 copy 를 실행하세요.")
    shots = manifest.get("shots") or []

    files = generate_images(
        copy=manifest["copy"], brand=ctx.config["brand"], image_config=ctx.config["image"],
        paths=ctx.paths, article=(manifest.get("articles") or [None])[0],
        fallback_image=shots[0] if shots else None,
    )
    images = {size["name"]: str(file) for size, file in zip(ctx.config["image"]["sizes"], files)}
    ctx.save(media={**(manifest.get("media") or {}), "images": images})
    return images


def step_publish(ctx: Context, options: dict) -> list[dict]:
    manifest = ctx.manifest()
    if not manifest.get("copy"):
        raise RuntimeError("카피가 없습니다. 먼저 copy 를 실행하세요.")
    if options.get("targets"):
        ctx.config["publish"]["targets"] = options["targets"]

    return publish(
        copy=manifest["copy"], media=manifest.get("media") or {}, config=ctx.config,
        paths=ctx.paths, run_id=ctx.run_id,
        dry_run=not options.get("publish"), variant=options.get("variant") or 1,
    )


# ── 전체 파이프라인 ────────────────────────────────────────

def run_all(options: dict) -> dict:
    ctx = open_run(options)
    log.step(f"실행 {ctx.run_id} 시작 · 결과는 out/{ctx.run_id}/ 에 쌓입니다")

    commit: Callable[[], None] = lambda: None
    blog = ctx.config["blog"]
    wants_blog = blog.get("feed") or blog.get("urls") or options.get("url") or options.get("feed")
    if not options.get("skip_analyze") and wants_blog:
        _, commit = step_analyze(ctx, options)

    if not options.get("skip_capture") and resolve(ctx.config["capture"]["flow"]).exists():
        try:
            step_capture(ctx, options)
        except Exception as exc:  # noqa: BLE001 - 영상이 없어도 이미지/카피는 낼 수 있습니다
            log.error(f"녹화 실패 — 영상 없이 이미지/카피만 진행합니다.\n  {exc}")

    step_copy(ctx, options)

    if ctx.manifest().get("video"):
        try:
            step_render(ctx)
        except Exception as exc:  # noqa: BLE001
            log.error(f"렌더 실패 — 이미지로만 진행합니다.\n  {exc}")

    step_image(ctx)
    results = step_publish(ctx, options)

    if options.get("publish") and any(r.get("ok") for r in results):
        commit()

    log.ok(f"완료 · out/{ctx.run_id}/")
    return {"runId": ctx.run_id, "results": results}
