"""명령줄 진입점."""
from __future__ import annotations

import argparse
import os
import sys

from . import log, pipeline
from .config import load_env
from .paths import ROOT

EPILOG = """예시
  python -m sns_autopilot doctor
  python -m sns_autopilot capture --flow config/flows/demo.yaml --headed
  python -m sns_autopilot run --url https://blog.example.com/post/123
  python -m sns_autopilot publish --latest --target postiz --publish
"""

COMMANDS = {
    "run": "전체 파이프라인 (분석 → 녹화 → 카피 → 렌더 → 이미지 → 발행)",
    "capture": "홈페이지를 자동 조작하며 화면 녹화 (새 실행 생성)",
    "analyze": "블로그 글 수집·분석",
    "copy": "카피 생성 (Claude)",
    "render": "녹화본 → 숏츠 mp4 + GIF",
    "image": "홍보 이미지 카드 생성",
    "publish": "발행 (기본은 미리보기, --publish 를 붙여야 실제 발행)",
    "doctor": "실행 환경 점검",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sns-autopilot",
        description="홈페이지 녹화 → 숏츠/GIF → 블로그 분석 → 카피·이미지 → SNS 자동 발행",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", choices=list(COMMANDS),
                        help="\n".join(f"{k}: {v}" for k, v in COMMANDS.items()))
    parser.add_argument("--config", help="설정 파일 (기본 config/pipeline.yaml)")
    parser.add_argument("--flow", help="녹화 시나리오 yaml")
    parser.add_argument("--url", help="분석할 블로그 글 주소 / capture 시 시작 주소")
    parser.add_argument("--feed", help="RSS 주소")
    parser.add_argument("--run", help="특정 실행 폴더에 이어서 작업")
    parser.add_argument("--latest", action="store_true", help="가장 최근 실행에 이어서 작업")
    parser.add_argument("--variant", type=int, default=1, help="발행할 시안 번호 (기본 1)")
    parser.add_argument("--target", action="append", dest="targets", default=[],
                        help="발행 대상 지정 (여러 번 사용 가능)")
    parser.add_argument("--publish", action="store_true", help="실제로 발행합니다 (없으면 미리보기만)")
    parser.add_argument("--headed", action="store_true", help="브라우저 창을 띄워서 녹화 (디버깅용)")
    parser.add_argument("--skip-capture", action="store_true", dest="skip_capture")
    parser.add_argument("--skip-analyze", action="store_true", dest="skip_analyze")
    return parser


def doctor() -> int:
    checks: list[tuple[bool, str, str, bool]] = []   # (통과, 라벨, 힌트, 참고용여부)

    checks.append((sys.version_info >= (3, 10), f"Python {sys.version.split()[0]}",
                   "Python 3.10 이상이 필요합니다.", False))

    try:
        from . import ffmpeg

        checks.append((True, f"ffmpeg: {ffmpeg.binary()}", "", False))
    except Exception as exc:  # noqa: BLE001
        checks.append((False, "ffmpeg", str(exc), False))

    try:
        from playwright.sync_api import sync_playwright

        # 경로만 보지 않고 실제로 한 번 띄워봅니다 (드라이버·의존 라이브러리까지 확인).
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True, executable_path=os.environ.get("CHROMIUM_PATH") or None
            )
            browser.close()
        checks.append((True, "Chromium (playwright)", "", False))
    except Exception as exc:  # noqa: BLE001
        first_line = str(exc).splitlines()[0]
        checks.append((False, "Chromium (playwright)",
                       f"{first_line} — playwright install chromium 을 실행하세요.", False))

    from .render.html2png import FONT_DIR, korean_font_face

    checks.append(("@font-face" in korean_font_face(), "한글 폰트 (Noto Sans KR)",
                   f"{FONT_DIR} 에 woff2 파일이 있어야 합니다.", False))

    checks.append((bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")),
                   "ANTHROPIC_API_KEY", ".env 에 API 키를 넣어주세요.", False))

    from .publish.adapters import ADAPTERS

    for name, adapter in ADAPTERS.items():
        if name == "file":
            continue
        checks.append((adapter.configured(), f"발행 채널: {name}",
                       "미설정 — 쓰려면 .env 를 채우세요", True))

    for passed, label, hint, soft in checks:
        if passed:
            log.ok(label)
        elif soft:
            log.info(f"· {label} — {hint}")
        else:
            log.error(f"{label} — {hint}")

    if any(not passed and not soft for passed, _, _, soft in checks):
        return 1
    log.ok("필수 항목 모두 통과")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_env(ROOT / ".env")
    args = build_parser().parse_args(argv)
    options = vars(args)

    if args.command == "doctor":
        return doctor()

    # capture / run 은 새 실행을 만들고, 나머지는 기본적으로 최근 실행을 이어받습니다.
    if args.command not in ("capture", "run") and not args.run:
        options["latest"] = True

    try:
        if args.command == "run":
            pipeline.run_all(options)
            return 0

        ctx = pipeline.open_run(options)
        if args.command == "capture":
            pipeline.step_capture(ctx, options)
        elif args.command == "analyze":
            pipeline.step_analyze(ctx, options)
        elif args.command == "copy":
            pipeline.step_copy(ctx, options)
        elif args.command == "render":
            pipeline.step_render(ctx)
        elif args.command == "image":
            pipeline.step_image(ctx)
        elif args.command == "publish":
            pipeline.step_publish(ctx, options)
        return 0
    except KeyboardInterrupt:
        log.warn("중단했습니다.")
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI 경계에서 사람이 읽을 메시지로 바꿉니다
        log.error(str(exc))
        if os.environ.get("DEBUG"):
            raise
        return 1
