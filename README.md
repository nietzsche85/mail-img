# SNS 오토파일럿

홈페이지를 **자동으로 조작·녹화**해서 숏츠와 GIF를 만들고, **블로그를 분석**해 바이럴 문구와 홍보 이미지를 뽑은 뒤, **SNS에 자동 발행**하는 파이프라인입니다.

```
블로그 분석 ──┐
              ├─→ Claude 카피 생성 ─→ 숏츠 mp4 · GIF · 홍보 이미지 ─→ 자동 발행
홈페이지 녹화 ─┘
```

한 번 설정해두면 `node src/cli.js run --publish` 한 줄, 또는 GitHub Actions 스케줄로 매일 돌아갑니다.

---

## 1. 5분 만에 돌려보기

```bash
npm install
npx playwright install chromium

cp .env.example .env      # ANTHROPIC_API_KEY 만 채우면 시작 가능
node src/cli.js doctor    # 환경 점검
```

포함된 데모 사이트로 전체 흐름을 확인해봅니다. **인터넷 연결도, SNS 계정도 필요 없습니다.**

```bash
node src/cli.js capture --flow config/flows/demo.yaml   # 자동 조작 + 녹화
node src/cli.js copy --latest                           # 카피 생성 (Claude)
node src/cli.js render --latest                         # 숏츠 mp4 + GIF
node src/cli.js image  --latest                         # 홍보 이미지 카드
node src/cli.js publish --latest                        # 미리보기 (실제 발행 X)
```

결과는 전부 `out/<실행ID>/` 에 쌓입니다.

```
out/20260830-124238/
├── capture/   recording.mp4, step-01.png…, timeline.json
├── render/    shorts.mp4, preview.gif, cover.png, intro.png, caption-*.png
├── images/    feed.png (1080×1350), story.png (1080×1920), og.png (1200×630)
├── copy/      copy.json  ← 플랫폼별 문구 전문
├── queue/     instagram-v1.txt, x-v1.txt … ← 손으로 올릴 때 복붙용
└── publish-report.json
```

---

## 2. 내 사이트로 바꾸기

### 녹화 시나리오

`config/pipeline.yaml` 의 `capture.flow` 는 처음엔 데모(`config/flows/demo.yaml`)를 가리킵니다.
내 사이트로 바꾸려면 `config/flows/example-homepage.yaml` 을 복사해서 고친 뒤 그 경로를 적어주세요.
위에서부터 순서대로 실행되고 전 과정이 녹화됩니다.

```yaml
name: "서울 → 홍콩 항공권 검색"
url: "https://mysite.com"
viewport: { width: 540, height: 960, deviceScaleFactor: 2 }
showCursor: true          # 마우스 커서와 클릭 파장을 화면에 그려줍니다

dismiss:                  # 쿠키 배너처럼 매번 뜨는 건 여기 적으면 자동으로 닫습니다
  - "button:has-text('동의')"

steps:
  - caption: "항공권, 아직도 **손으로** 비교하세요?"   # **강조** 는 포인트 색으로 표시
    pause: 1.4
  - fill: { selector: "#origin", value: "서울", typeDelay: 110 }
    caption: "출발지만 넣으면"
  - click: { text: "검색" }
  - wait: { selector: "[data-testid='result-list']", timeout: 15 }
  - scroll: { to: "bottom", duration: 2.2 }
  - highlight: "#result-list .row:first-child"
    caption: "**28만원대** 특가까지"
    pause: 2.0
```

쓸 수 있는 동작:

| 동작 | 예시 | 설명 |
|---|---|---|
| `goto` | `goto: https://...` | 페이지 이동 |
| `click` | `click: { text: "검색" }` / `{ selector: "#btn" }` / `{ role: button, name: 로그인 }` | 마우스가 부드럽게 이동한 뒤 클릭합니다 |
| `fill` | `fill: { selector: "#id", value: "서울", typeDelay: 90 }` | 한 글자씩 타이핑 |
| `press` | `press: Enter` | 키 입력 |
| `hover` | `hover: ".card"` | 마우스 올리기 |
| `select` | `select: { selector: "#sort", value: "price" }` | 드롭다운 선택 |
| `scroll` | `scroll: { to: bottom, duration: 2.5 }` | 사람처럼 부드럽게 스크롤 |
| `highlight` | `highlight: ".row:first-child"` | 강조 테두리 + 펄스 |
| `wait` | `wait: 2` / `wait: { selector: "...", timeout: 15 }` | 대기 |
| `screenshot` | `screenshot: result` | 스크린샷 저장 |

모든 스텝에 `caption:`(자막), `pause:`(끝난 뒤 대기 초), `optional: true`(실패해도 계속)를 붙일 수 있습니다.
로그인이 필요하면 `.env` 의 값을 `${SITE_ID}` 처럼 참조하세요.

### 브랜드·발행 설정

`config/pipeline.yaml` 에서 톤앤매너, 금칙어, 색상, 플랫폼, 발행 대상을 정합니다.

```yaml
brand:
  name: "마이리얼트립"
  voice: "여행 준비하는 20~30대에게 말 걸듯, 구체적인 숫자와 혜택 중심으로. 해요체."
  banned: ["최저가 보장", "무조건", "100% 환불"]   # 이 표현이 나오면 경고하고 기록합니다
  colors: { bg: "#0B3D91", accent: "#4FC3F7", highlight: "#FFD54F" }

blog:
  feed: "https://blog.mysite.com/rss"   # 주소만 줘도 RSS 위치를 찾아냅니다
  limit: 3

publish:
  targets: [postiz]     # file | webhook | postiz | x | threads | instagram | youtube
```

---

## 3. 자동 발행

기본은 **미리보기(dry-run)** 입니다. `--publish` 를 붙여야 실제로 올라갑니다.

```bash
node src/cli.js run --publish                     # 전체 자동
node src/cli.js publish --latest --target postiz --publish
node src/cli.js publish --latest --variant 2 --publish   # B안으로 발행
```

채널별 토큰 발급 방법과 정책 주의사항은 **[docs/PLATFORM-GUIDE.md](docs/PLATFORM-GUIDE.md)** 에 정리해 두었습니다.
가장 손이 덜 가는 방법은 **Postiz** 하나만 연결하는 것입니다 (X·인스타·스레드·유튜브·틱톡·링크드인 등 28개 채널을 한 API로 처리).

### 매일 자동으로 돌리기

`.github/workflows/sns-auto.yml` 이 매일 오전 9시(KST)에 파이프라인을 실행합니다.
저장소 **Settings → Secrets and variables → Actions** 에 `.env.example` 의 키들을 등록하면 끝입니다.

---

## 4. 명령어

```
run          전체 파이프라인
capture      홈페이지 자동 조작 + 녹화 (새 실행 생성)
analyze      블로그 글 수집·분석
copy         카피 생성 (Claude)
render       녹화본 → 숏츠 mp4 + GIF
image        홍보 이미지 카드 생성
publish      발행 (기본 미리보기, --publish 로 실제 발행)
doctor       실행 환경 점검
```

주요 옵션: `--config` `--flow` `--url` `--feed` `--run <ID>` `--latest` `--variant <n>` `--target <이름>` `--publish` `--headed`

---

## 5. 알아두면 좋은 것

**영상 품질** — Playwright 내장 녹화는 CSS 픽셀 크기로만 찍혀서 세로 영상으로 키우면 뿌옇습니다.
그래서 CDP 화면 캐스트로 실제 디바이스 픽셀(1080×1920) 프레임을 직접 받아 씁니다.
화면이 안 바뀌면 프레임이 안 오기 때문에, 자막 시각은 "실제 시각 → 영상 시각" 대응표로 다시 계산해 붙입니다.

**한글 자막** — ffmpeg 의 `drawtext` 는 한글 폰트 문제가 잦아서 쓰지 않습니다.
자막·인트로·아웃트로·이미지 카드는 전부 크롬에서 CSS로 그린 뒤 PNG로 얹습니다. 디자인을 바꾸고 싶으면 `templates/card.html` 과 `src/render/cards.js` 만 고치면 됩니다.

**과장광고 방지** — 카피 생성 시 원문에 없는 숫자·할인율을 만들지 않도록 지시하고, `banned` 목록은 코드로 한 번 더 걸러 `copy.json` 의 `risky_claims` 에 남깁니다. **발행 전에 이 항목은 사람이 확인하세요.**

**중복 발행 방지** — 이미 처리한 글 주소는 `.state/seen.json` 에 남아 다음 실행에서 건너뜁니다.

**계정 정책** — SNS 자동 발행은 각 플랫폼의 **공식 API**로만 합니다. 브라우저 자동 조작으로 SNS에 로그인해 글을 올리는 방식은 대부분 약관 위반이고 계정 정지 사유라서 넣지 않았습니다. 브라우저 자동화는 "내 홈페이지를 녹화하는 용도"로만 씁니다.

---

## 6. 구조

```
src/
├── cli.js                 명령줄 진입점
├── pipeline.js            단계 조립 (실행 폴더에 manifest.json 으로 이어붙임)
├── capture/
│   ├── record.js          시나리오 실행 + 녹화
│   ├── screencast.js      CDP 프레임 캡처 + 시간축 대응표
│   └── cursor.js          마우스 커서·클릭 파장 오버레이
├── render/
│   ├── shorts.js          숏츠 mp4 + GIF (ffmpeg)
│   ├── cards.js           인트로·아웃트로·자막 HTML
│   └── html2png.js        HTML → PNG (한글 웹폰트 인라인)
├── analyze/blog.js        RSS 탐색 · 본문 추출
├── generate/
│   ├── copy.js            Claude 구조화 출력으로 플랫폼별 카피
│   ├── prompts.js         플랫폼별 규칙·브랜드 프롬프트
│   └── image.js           홍보 이미지 카드
└── publish/
    ├── index.js           발행 라우팅 (dry-run 기본)
    └── adapters/          file · webhook · postiz · x · threads · instagram · youtube
```
