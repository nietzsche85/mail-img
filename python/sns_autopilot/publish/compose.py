"""본문·해시태그 조합과 플랫폼별 글자 수 제한."""
from __future__ import annotations

import os
from pathlib import Path

#: 큐 파일 머리말에 쓸 사람이 읽는 채널 이름
LABELS: dict[str, str] = {
    "instagram": "인스타그램", "threads": "스레드", "x": "X(트위터)",
    "youtube": "유튜브 쇼츠", "tiktok": "틱톡", "naver_blog": "네이버 블로그",
    "linkedin": "링크드인", "facebook": "페이스북",
}

LIMITS: dict[str, int] = {
    "x": 280,
    "threads": 500,
    "instagram": 2200,
    "tiktok": 2200,
    "facebook": 5000,
    "linkedin": 3000,
    "youtube": 5000,
    "naver_blog": 0,
}


def compose_text(post: dict, with_hashtags: bool = True, limit: int = 0) -> str:
    """본문 + 해시태그를 플랫폼에 맞게 한 덩어리로 합칩니다."""
    tags = [t if t.startswith("#") else f"#{t}" for t in (post.get("hashtags") or [])]
    body = (post.get("text") or "").strip()
    text = f"{body}\n\n{' '.join(tags)}" if with_hashtags and tags else body

    if limit and len(text) > limit:
        # 해시태그부터 줄이고, 그래도 넘치면 본문을 자릅니다.
        kept = list(tags)
        while kept and len(f"{body}\n\n{' '.join(kept)}") > limit:
            kept.pop()
        text = (f"{body}\n\n{' '.join(kept)}" if kept else body)[:limit]
    return text


def public_url(local_path: str | Path) -> str | None:
    """공개 URL 이 필요한 플랫폼(인스타·스레드)을 위해 로컬 경로를 URL 로 바꿉니다.

    `<베이스>/<실행ID>/<폴더>/<파일>` 형태가 됩니다.
    """
    base = os.environ.get("PUBLIC_MEDIA_BASE_URL")
    if not base:
        return None
    tail = "/".join(Path(local_path).parts[-3:])
    return f"{base.rstrip('/')}/{tail}"
