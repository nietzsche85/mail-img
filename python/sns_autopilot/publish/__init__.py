"""발행 라우팅. 기본은 미리보기(dry-run)이며 --publish 를 붙여야 실제로 올라갑니다."""
from __future__ import annotations

from typing import Any

from .. import log
from ..paths import RunPaths, write_json
from .adapters import ADAPTERS, OWNED_PLATFORM
from .compose import LIMITS, compose_text


def assets_for(platform: str, media: dict) -> dict[str, Any]:
    """플랫폼별로 어떤 파일을 붙일지 정합니다."""
    video = media.get("mp4")
    images = media.get("images") or {}
    if platform == "youtube":
        return {"video": video}
    if platform == "instagram":
        return {"video": video, "image": images.get("feed") or media.get("cover")}
    if platform == "threads":
        return {"video": video, "image": images.get("feed")}
    if platform == "x":
        return {"video": video, "image": images.get("og") or images.get("feed")}
    if platform == "tiktok":
        return {"video": video}
    if platform == "naver_blog":
        return {"image": images.get("feed"), "gif": media.get("gif")}
    return {"video": video, "image": images.get("feed"), "gif": media.get("gif")}


def publish(copy: dict, media: dict, config: dict, paths: RunPaths, run_id: str,
            dry_run: bool = True, variant: int = 1) -> list[dict]:
    targets = config["publish"].get("targets") or ["file"]
    posts = [p for p in (copy.get("posts") or []) if p.get("variant") == variant]
    if not posts:
        log.warn(f"variant {variant} 에 해당하는 글이 없습니다.")
        return []

    ctx = {"paths": paths, "run_id": run_id, "schedule_at": config["publish"].get("scheduleAt") or ""}
    results: list[dict] = []

    for target_name in targets:
        adapter = ADAPTERS.get(target_name)
        if not adapter:
            log.warn(f"알 수 없는 발행 대상: {target_name}")
            continue
        if not adapter.configured():
            log.warn(f"{target_name}: 자격 증명이 없어 건너뜁니다 (.env 확인)")
            continue

        for post in posts:
            owned = OWNED_PLATFORM.get(target_name)
            if owned and post["platform"] != owned:
                continue

            assets = assets_for(post["platform"], media)
            label = f"{target_name} ← {post['platform']} v{post['variant']}"

            # file 대상은 dry-run 에서도 실제로 씁니다 (그게 미리보기 산출물이라서).
            if dry_run and target_name != "file":
                text = compose_text(post, limit=LIMITS.get(post["platform"], 0))
                preview = "\n".join(text.splitlines()[:3])
                log.info(f"[미리보기] {label} ({len(text)}자)\n{preview}…")
                results.append({"target": target_name, "platform": post["platform"],
                                "variant": post["variant"], "dryRun": True})
                continue

            try:
                result = adapter.send(post, assets, ctx)
                log.ok(f"{label} → {result.get('url') or result.get('output') or result.get('id') or '완료'}")
                results.append({"target": target_name, "platform": post["platform"],
                                "variant": post["variant"], **result})
            except Exception as exc:  # noqa: BLE001 - 한 채널 실패가 나머지를 막지 않게
                log.error(f"{label} 실패: {exc}")
                results.append({"target": target_name, "platform": post["platform"],
                                "variant": post["variant"], "ok": False, "error": str(exc)})

    write_json(paths.base / "publish-report.json",
               {"runId": run_id, "dryRun": dry_run, "variant": variant, "results": results})
    return results


__all__ = ["ADAPTERS", "assets_for", "publish"]
