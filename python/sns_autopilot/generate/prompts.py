"""플랫폼별 작성 규칙과 브랜드 시스템 프롬프트."""
from __future__ import annotations

PLATFORM_SPECS: dict[str, dict[str, str]] = {
    "instagram": {
        "label": "인스타그램 릴스 캡션",
        "rules": "첫 줄 40자 안에 후킹. 전체 300~600자. 줄바꿈으로 호흡 나누기. "
                 "해시태그 8~12개는 hashtags 로 분리. 링크는 본문에 못 넣으니 '프로필 링크' 로 유도.",
    },
    "threads": {"label": "스레드", "rules": "500자 이내. 대화체로 질문 던지며 시작. 해시태그는 1~2개만."},
    "x": {"label": "X(트위터)", "rules": "한글 220자 이내로 완결. 줄바꿈 2회 이내. 해시태그 2개 이내."},
    "youtube": {
        "label": "유튜브 쇼츠",
        "rules": "title 은 45자 이내 + 검색어 포함. text 는 설명란 3~5줄. hashtags 에 #Shorts 를 반드시 포함.",
    },
    "tiktok": {"label": "틱톡", "rules": "150자 이내. 해시태그 4~6개. 트렌디한 말투."},
    "naver_blog": {
        "label": "네이버 블로그",
        "rules": "title 은 30자 내외 검색형 제목. text 는 소제목(##) 3개로 나눈 800~1200자 본문. 표현은 담백하게.",
    },
    "linkedin": {"label": "링크드인", "rules": "인사이트 중심 600자 이내. 해시태그 3개."},
    "facebook": {"label": "페이스북", "rules": "300자 이내. 링크 클릭 유도."},
}


def system_prompt(brand: dict) -> str:
    banned = ", ".join(brand.get("banned") or [])
    lines = [
        "당신은 한국 SNS 그로스 마케터입니다. 실제로 성과가 나는 카피를 씁니다.",
        "",
        "# 브랜드",
        f"- 이름: {brand.get('name', '')}",
        f"- 톤앤매너: {brand.get('voice', '')}",
    ]
    if brand.get("cta"):
        lines.append(f"- 기본 CTA: {brand['cta']}")
    lines += [
        "",
        "# 반드시 지킬 것",
        "1. 원문(블로그/화면)에 없는 사실, 숫자, 할인율을 지어내지 않습니다. 근거가 없으면 그 표현을 뺍니다.",
        f"2. 다음 표현은 절대 쓰지 않습니다: {banned}" if banned else "2. 근거 없는 최상급 표현을 쓰지 않습니다.",
        "3. 과장광고로 읽힐 소지가 있는 문장은 risky_claims 에 그대로 적어 둡니다.",
        "4. 이모지는 문장당 1개 이하. 남발하지 않습니다.",
        "5. 플랫폼별 글자 수 제한을 지킵니다. 넘치면 문장을 줄입니다.",
        "6. 훅(hook)은 18자 이내, 읽자마자 무슨 얘긴지 알 수 있게 씁니다.",
    ]
    return "\n".join(lines)


def user_prompt(article: dict | None, screen_text: str, platforms: list[str],
                variants: int, language: str) -> str:
    specs = "\n".join(
        f"- {p} ({PLATFORM_SPECS.get(p, {}).get('label', p)}): "
        f"{PLATFORM_SPECS.get(p, {}).get('rules', '간결하게')}"
        for p in platforms
    )

    if article:
        source_lines = [f"제목: {article.get('title', '')}"]
        if article.get("publishedAt"):
            source_lines.append(f"작성일: {article['publishedAt']}")
        source_lines += [f"URL: {article.get('url', '')}", "", "본문:", (article.get("text") or "")[:8000]]
        source = "\n".join(source_lines)
    else:
        source = "(블로그 글 없음)"

    blocks = ["# 소재", source, ""]
    if screen_text:
        blocks += [f"# 함께 붙일 영상에 담긴 화면 흐름\n{screen_text}", ""]
    blocks += [
        "# 만들어야 할 것",
        f"언어: {'한국어' if language == 'ko' else language}",
        f"플랫폼별로 서로 다른 시안 {variants}개씩:",
        specs,
        "",
        "posts 배열에는 위 플랫폼 × 시안 수 만큼 항목을 넣습니다. variant 는 1부터 시작합니다.",
        "card 필드들은 정사각/세로 홍보 이미지에 그대로 얹을 짧은 문구입니다. bullets 는 각 14자 이내로 3개.",
    ]
    return "\n".join(blocks)
