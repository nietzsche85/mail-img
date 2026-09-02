# 프로젝트 메모

## 릴리스 버전
- **현재 확정 버전: 1.1** — 사용자가 로컬(데스크톱)에 받은 `sns-autopilot-python` 압축본을 최종 1.1로 저장해 둠.
- 저장소 코드의 버전 문자열(`package.json`, `python/sns_autopilot/__init__.py`)은 `0.7.1` 그대로 두기로 함.
  사용자 요청: "파일을 수정할 필요는 없음 1.1로 메모리 저장바람" — 버전 표기는 파일에 반영하지 않고 메모로만 관리.
- 즉, **사용자가 말하는 "1.1" = 아래 기능이 모두 포함된 현재 코드 상태**를 가리킴.

## 1.1에 포함된 내용 (기준선)
- Node 구현: 저장소 루트(`src/`, `config/`, `templates/`)
- Python 구현: `python/` (자체 완결형, zip으로 배포 / `.env`는 사용자가 직접 생성, 절대 커밋 금지)
- GUI(`python/sns_autopilot/gui.py`): URL 입력 → 캡쳐 + 인코딩, 수동 녹화 시작/종료 버튼
- 인트로/아웃트로 카드: 완전 선택 사항(텍스트 직접 입력 / 이미지 지정 / 아예 제거 가능)
- 커서 오버레이 좌표 오프셋 수정 (left/top 파킹, `transform` 미사용)
- 해상도 처리: `fit: auto|fill|contain` — `auto`는 커버리지 0.9 미만이면 블러 배경 contain 선택.
  화면 크기 설정은 "브라우저 크기"이며 출력물은 항상 1080x1920.
- 화면 캐스트 조립은 `fps=` 필터 대신 `-fps_mode vfr` 사용(영상 뒷부분 잘림 방지)

## 주의사항
- ANTHROPIC_API_KEY는 사용자 로컬 `.env`에만 존재. 저장소에 올리지 않음.
- Postiz는 `/public/v1/integrations`로 채널 자동 매칭, `settings.__type` 필수, 시간당 30회 제한.
