"""Claude 구조화 출력으로 플랫폼별 카피를 만듭니다."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import anthropic
import pydantic
from pydantic import BaseModel, Field

from .. import log
from ..paths import RunPaths, relative, write_json
from .prompts import system_prompt, user_prompt


class Post(BaseModel):
    platform: str
    variant: int
    title: str = Field(description="유튜브/블로그처럼 제목이 따로 있는 플랫폼만. 없으면 빈 문자열.")
    text: str
    hashtags: list[str]
    firstComment: str = Field(description="첫 댓글에 넣을 링크/부연. 없으면 빈 문자열.")  # noqa: N815


class Card(BaseModel):
    badge: str
    title: str
    subtitle: str
    bullets: list[str]


class CopyResult(BaseModel):
    angle: str = Field(description="이번 콘텐츠를 관통하는 한 줄 각도")
    hook: str = Field(description="영상 첫 화면에 띄울 훅. 18자 이내")
    hookSub: str = Field(description="훅 아래 보조 문구. 24자 이내")  # noqa: N815
    cta: str = Field(description="영상 마지막 화면 CTA. 16자 이내")
    captions: list[str] = Field(description="영상 자막으로 쓸 짧은 문장들. 각 20자 이내")
    card: Card
    hashtags: list[str] = Field(description="공통 해시태그 풀. # 포함")
    posts: list[Post]
    risky_claims: list[str] = Field(description="과장광고로 읽힐 수 있어 사람이 확인해야 하는 문장")


def screen_summary(timeline: dict | None) -> str:
    """녹화 타임라인을 카피 생성용 텍스트로 요약합니다."""
    if not timeline or not timeline.get("events"):
        return ""
    lines = []
    for event in timeline["events"]:
        step = event.get("step") or {}
        if step.get("caption"):
            lines.append(f"- {step['caption']}")
        elif step.get("click"):
            lines.append(f"- 클릭: {step['click']}")
        elif step.get("fill"):
            lines.append(f"- 입력: {step['fill'].get('value', '')}")
        elif step.get("scroll"):
            lines.append("- 결과 목록 스크롤")
    return "\n".join([f"화면 시나리오: {timeline.get('name', '')}", *lines])


def generate_copy(article: dict | None, timeline: dict | None, brand: dict,
                  copy_config: dict, paths: RunPaths) -> dict[str, Any]:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise RuntimeError("ANTHROPIC_API_KEY 가 없습니다. .env 에 넣어주세요.")

    client = anthropic.Anthropic()
    platforms = copy_config["platforms"]
    log.step(f"카피 생성 ({copy_config['model']}, {', '.join(platforms)})")

    try:
        response = client.messages.parse(
            model=copy_config["model"],
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=system_prompt(brand),
            messages=[{
                "role": "user",
                "content": user_prompt(
                    article=article,
                    screen_text=screen_summary(timeline),
                    platforms=platforms,
                    variants=copy_config["variants"],
                    language=copy_config["language"],
                ),
            }],
            output_format=CopyResult,
            output_config={"effort": copy_config.get("effort", "high")},
        )
    except pydantic.ValidationError as exc:
        # parse() 는 응답을 스키마로 검증하다 실패하면 여기서 바로 예외를 던집니다.
        # 아래 stop_reason 검사까지 가지 못하므로, 모델이 돌려준 원문을 보고 원인을 나눕니다.
        # (Node 판은 create() 로 원본 응답을 받아 직접 검증합니다. 파이썬 SDK 는
        #  스키마 변환 헬퍼가 비공개라 parse() 를 그대로 쓰는 편이 안전합니다.)
        errors = exc.errors()
        raw = str(errors[0].get("input", "")) if errors else ""
        if not raw.strip():
            reason = "모델이 빈 응답을 돌려줬습니다. 요청을 거절했을 수 있습니다 (민감한 소재)."
        else:
            reason = f"모델이 형식에 맞지 않는 응답을 돌려줬습니다: {raw[:120]}…"
        raise RuntimeError(
            f"카피 생성 실패 — {reason}\n"
            "  소재를 바꾸거나 copy.platforms / copy.variants 를 줄여서 다시 시도해보세요."
        ) from exc

    # 응답이 정상적으로 왔는데 내용이 비어 있는 경우까지 한 번 더 거릅니다.
    if response.stop_reason == "refusal":
        category = getattr(response.stop_details, "category", None) or "unknown"
        raise RuntimeError(f"모델이 요청을 거절했습니다 ({category}). 소재를 확인해주세요.")
    if not response.parsed_output:
        raise RuntimeError("구조화된 응답을 파싱하지 못했습니다.")

    result = response.parsed_output.model_dump()

    # 브랜드 금칙어는 코드로 한 번 더 거릅니다 (모델 실수 방지).
    flagged = [
        f'{post["platform"]} #{post["variant"]}: "{word}"'
        for post in result["posts"]
        for word in (brand.get("banned") or [])
        if word in post["text"] or word in (post.get("title") or "")
    ]
    if flagged:
        log.warn("금칙어 발견 — 발행 전 확인 필요:\n  " + "\n  ".join(flagged))
        result["risky_claims"] = [*result.get("risky_claims", []), *flagged]
    if result.get("risky_claims"):
        log.warn(f"사람 확인 권장 문구 {len(result['risky_claims'])}건 (copy/copy.json 의 risky_claims 참고)")

    file = write_json(paths.copy / "copy.json", {
        "source": {"url": article["url"], "title": article["title"]} if article else None,
        "model": copy_config["model"],
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "usage": response.usage.model_dump() if response.usage else None,
        **result,
    })
    log.ok(f"카피 {len(result['posts'])}개 → {relative(file)}")
    return result
