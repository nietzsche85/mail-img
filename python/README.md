# SNS 오토파일럿 (Python)

홈페이지를 **자동으로 조작·녹화**해서 숏츠와 GIF를 만들고, **블로그를 분석**해 바이럴 문구와 홍보 이미지를 뽑은 뒤, **SNS에 자동 발행**하는 파이프라인입니다.

```
블로그 분석 ──┐
              ├─→ Claude 카피 생성 ─→ 숏츠 mp4 · GIF · 홍보 이미지 ─→ 자동 발행
홈페이지 녹화 ─┘
```

한글 폰트를 동봉해서 **인터넷 없이도 자막·이미지가 깨지지 않습니다.**

---

## 1. 설치

압축을 푼 폴더에서 한 줄이면 됩니다.

```bash
bash setup.sh          # macOS / Linux
setup.bat              # Windows (더블클릭해도 됩니다)
```

가상환경(.venv) 생성 → 라이브러리 설치 → Chromium 내려받기 → `.env` 생성 → 환경 점검까지 알아서 합니다.
회사망 등에서 Chromium 다운로드가 막혀도 나머지 설치는 끝내고, 무엇을 다시 하면 되는지 알려줍니다.

설치가 끝나면 **`.env` 파일을 열어 `ANTHROPIC_API_KEY` 에 실제 키를 넣어주세요.**
`.env` 는 `.gitignore` 에 들어 있어서 GitHub 에 올라가지 않습니다.

```
ANTHROPIC_API_KEY=sk-ant-...
```

<details><summary>직접 설치하고 싶다면</summary>

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
python -m sns_autopilot doctor
```
</details>

<details><summary>인터넷이 막힌 환경이라면</summary>

`vendor/wheels/` 폴더가 함께 들어 있으면 `setup.sh` / `setup.bat` 이 자동으로 그걸 씁니다
(`pip install --no-index --find-links vendor/wheels`). 이 폴더는 **운영체제와 파이썬 버전이 맞아야** 합니다.
직접 만들려면 인터넷 되는 같은 사양의 PC에서:

```bash
pip download -d vendor/wheels -r requirements.txt
```

Chromium 은 wheel 에 들어 있지 않아 `playwright install chromium` 이 따로 필요합니다.
이미 크롬이 있다면 `CHROMIUM_PATH` 환경변수로 실행 파일 경로를 지정해도 됩니다.
</details>

`doctor` 가 Python 버전, ffmpeg, Chromium, 한글 폰트, API 키, 연결된 발행 채널을 한 번에 점검합니다.

> ffmpeg 는 `imageio-ffmpeg` 가 받아둔 정적 바이너리를 씁니다. 따로 설치할 필요가 없습니다.
> 시스템 ffmpeg 를 쓰고 싶으면 `FFMPEG_PATH` 환경변수로 지정하세요.

### 새 버전으로 업데이트

압축본을 **기존 폴더에 그대로 덮어쓰면** 됩니다. 압축본에는 `.env` 와 `.venv` 가 들어 있지 않아
설정과 가상환경은 그대로 유지됩니다.

```bash
python -m sns_autopilot --version    # 지금 버전 확인
```

명령이 없다는 오류(`invalid choice`)가 나면 폴더가 옛 버전입니다.

## 2. 창으로 쓰기 (제일 쉬운 방법)

주소만 넣고 버튼을 누르면 홈페이지를 녹화해서 세로 숏츠와 GIF까지 만들어 줍니다.
시나리오 yaml 도, 명령줄도 필요 없습니다.

```
Windows          gui.bat 더블클릭
macOS / Linux    bash gui.sh
명령으로도       python -m sns_autopilot gui
```

| 입력칸 | 설명 |
|---|---|
| 홈페이지 주소 | `https://` 는 빼고 넣어도 붙여줍니다 |
| 영상 자막 | 녹화 화면 위에 깔리는 문구. `**강조**` 는 포인트 색으로 나옵니다. 비워도 됩니다 |
| 화면 크기 | 모바일(540×960) · 태블릿 · 데스크톱 |
| 스크롤 시간 | 위에서 아래까지 훑는 데 걸리는 초 |
| 브라우저 창 보기 | 진행되는 모습을 눈으로 보고 싶을 때 |

버튼은 **캡쳐 + 인코딩**(한 번에), **캡쳐만**, **인코딩만**(최근 캡쳐 다시 인코딩) 세 가지입니다.
진행 상황은 창 안에 그대로 찍히고, 끝나면 **결과 폴더 열기** 로 바로 확인할 수 있습니다.

### 앞뒤 카드 — 기본은 없음

영상 앞뒤에 붙는 카드는 **기본으로 붙지 않습니다.** 녹화한 화면만 그대로 나갑니다.
넣고 싶을 때만 창의 **앞뒤 카드** 칸에 채우세요.

| 넣은 것 | 결과 |
|---|---|
| 아무것도 안 넣음 | 카드 없음 (기본) |
| 문구만 | 그 문구로 카드를 그립니다 |
| 이미지만 | **직접 만든 그 이미지**가 카드가 됩니다 |
| 문구 + 이미지 | 이미지가 이깁니다 |

이미지는 비율이 달라도 됩니다. 늘리지 않고 **채운 뒤 잘라내서** 9:16 에 맞춥니다.
지정한 이미지 파일이 없으면 경고하고, 문구가 있으면 문구로 대신 만듭니다.

설정 파일로도 같은 값을 정할 수 있습니다. 창에 넣은 값이 설정보다 우선합니다.

```yaml
render:
  shorts:
    intro: { text: "", image: "", seconds: 1.6 }
    outro: { text: "", image: "", seconds: 2.0 }
```

### 수동 녹화 — 브라우저를 직접 조작하며 담기

로그인이 필요하거나, 그때그때 다르게 보여주고 싶은 흐름은 시나리오로 적기 어렵습니다.
그럴 땐 브라우저를 띄워 두고 **손으로 조작하면서 원하는 구간만** 담으면 됩니다.

```
브라우저 열기  →  (화면을 원하는 상태로 맞춤)  →  ● 녹화 시작
             →  (보여주고 싶은 동작을 함)     →  ■ 녹화 종료 + 인코딩
```

- **브라우저 열기** — 주소를 열고 대기합니다. 로그인이든 검색이든 자유롭게 하세요.
- **● 녹화 시작** — 이 순간부터 화면이 담깁니다. 준비를 다 마친 뒤 누르세요.
- **■ 녹화 종료 + 인코딩** — 녹화를 멈추고 바로 숏츠와 GIF 로 만듭니다.
- **취소** — 담은 것을 버리고 브라우저를 닫습니다.

클릭한 자리에는 자동 녹화와 똑같이 커서와 물결 표시가 찍힙니다.
같은 탭 안에서 페이지를 옮겨 다니는 것은 그대로 담기지만, **새 탭을 열면 그쪽은 담기지 않습니다.**

> 카피 생성·이미지 카드·SNS 발행은 아직 창에 없습니다. 명령줄(`copy`, `image`, `publish`)로 이어서 하시면 됩니다.

**tkinter 는 파이썬에 기본 포함**이라 따로 설치할 게 없습니다.
리눅스 일부 배포판만 `sudo apt install python3-tk` 가 필요합니다.

## 3. 5분 만에 돌려보기

포함된 데모 사이트로 전체 흐름을 확인합니다. **인터넷 연결도, SNS 계정도 필요 없습니다.**

```bash
python -m sns_autopilot capture --flow config/flows/demo.yaml   # 자동 조작 + 녹화
python -m sns_autopilot copy   --latest                         # 카피 생성 (Claude)
python -m sns_autopilot render --latest                         # 숏츠 mp4 + GIF
python -m sns_autopilot image  --latest                         # 홍보 이미지 카드
python -m sns_autopilot publish --latest                        # 미리보기 (실제 발행 X)
```

결과는 전부 `out/<실행ID>/` 에 쌓입니다.

```
out/20260830-225901/
├── capture/   recording.mp4, step-01.png…, timeline.json, frames/
├── render/    shorts.mp4, preview.gif, cover.png, intro.png, caption-*.png
├── images/    feed.png (1080×1350), story.png (1080×1920), og.png (1200×630)
├── copy/      copy.json  ← 플랫폼별 문구 전문
├── queue/     instagram-v1.txt, x-v1.txt … ← 손으로 올릴 때 복붙용
└── publish-report.json
```

`pip install -e .` 로 설치하면 `sns-autopilot <명령>` 으로도 쓸 수 있습니다.

---

## 4. 내 사이트로 바꾸기

### 녹화 시나리오

`config/pipeline.yaml` 의 `capture.flow` 는 처음엔 데모를 가리킵니다.
내 사이트로 바꾸려면 `config/flows/example-homepage.yaml` 을 복사해 고친 뒤 그 경로를 적어주세요.

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

## 5. 발행

### 채널 API 가 없어도 됩니다

`ANTHROPIC_API_KEY` 하나만 있으면 분석 → 카피 → 영상 → 이미지까지 전 과정이 돌아갑니다.
기본 설정(`targets: [file]`)이 발행 직전 상태를 `out/<실행ID>/queue/` 에 파일로 떨궈주니,
그걸 그대로 각 SNS 에 붙여넣으면 됩니다. 채널별 토큰은 **나중에 자동화하고 싶어질 때** 붙이면 됩니다.

```
── 인스타그램 · 시안 1 ────────────────────────────────────
글자수 65 / 2200

홍콩 왕복, 검색 한 번이면 끝나요.

출발지랑 도착지만 넣으면 직항부터 순서대로 보여줘요.

#홍콩여행 #항공권특가

[첫 댓글] 자세한 조건은 링크에서 확인하세요.

[첨부]
  동영상  .../render/shorts.mp4
  이미지  .../images/feed.png
```

`doctor` 에 뜨는 `· 발행 채널: x — 미설정` 같은 줄은 **오류가 아니라 안내**입니다.
✗ 로 표시되는 항목만 고치면 됩니다.

### 자동 발행

기본은 **미리보기(dry-run)** 입니다. `--publish` 를 붙여야 실제로 올라갑니다.

```bash
python -m sns_autopilot run --publish                      # 전체 자동
python -m sns_autopilot publish --latest --target postiz --publish
python -m sns_autopilot publish --latest --variant 2 --publish   # B안으로 발행
```

채널별 토큰 발급 방법과 정책 주의사항은 **[docs/PLATFORM-GUIDE.md](docs/PLATFORM-GUIDE.md)** 에 정리해 두었습니다.
가장 손이 덜 가는 방법은 **Postiz** 하나만 연결하는 것입니다 (X·인스타·스레드·유튜브·틱톡·링크드인 등 28개 채널을 한 API로 처리).

매일 자동으로 돌리려면 `deploy/github-actions.yml` 을 `.github/workflows/` 에 복사하고,
저장소 Secrets 에 `.env.example` 의 키들을 등록하면 됩니다.

---

## 6. 명령어

```
run          전체 파이프라인
capture      홈페이지 자동 조작 + 녹화 (새 실행 생성)
analyze      블로그 글 수집·분석
copy         카피 생성 (Claude)
render       녹화본 → 숏츠 mp4 + GIF
image        홍보 이미지 카드 생성
publish      발행 (기본 미리보기, --publish 로 실제 발행)
gui          주소 넣고 캡쳐·인코딩하는 창 띄우기
channels     Postiz 에 연결된 채널 목록 보기
doctor       실행 환경 점검
```

옵션: `--config` `--flow` `--url` `--feed` `--run <ID>` `--latest` `--variant <n>` `--target <이름>` `--publish` `--headed`

---

## 7. 만들면서 걸렸던 것 (읽어두면 고칠 때 편합니다)

**Playwright 내장 녹화는 세로 영상에 못 씁니다.** CSS 픽셀 크기로만 저장돼서 1080×1920으로 키우면 뿌옇습니다.
그래서 CDP `Page.startScreencast` 로 실제 디바이스 픽셀 프레임을 직접 받습니다.

**동기 API에서는 `time.sleep()` 동안 프레임이 하나도 안 옵니다.**
Playwright 동기 API는 자기 호출 안에서만 이벤트를 펌프하기 때문에, `time.sleep(2)` 하면 그 2초 동안 화면 캐스트 프레임이
전혀 전달되지 않고 나중에 몰려서 도착합니다. 그래서 대기는 전부 `page.wait_for_timeout()` 을 씁니다.
(같은 시나리오에서 프레임 수가 179장 → 350장으로 늘었습니다.)

**자막 시각은 프레임 메타데이터의 epoch 시각으로 계산합니다.**
핸들러가 실행된 시각을 쓰면 이벤트 전달이 밀릴 때 자막이 어긋납니다.
화면이 안 바뀌면 프레임이 오지 않아 영상 길이가 실제 조작 시간보다 짧으므로,
"실제 시각 → 영상 시각" 대응표를 만들어 자막 위치를 다시 계산합니다.

**프레임을 이어붙일 때 `fps` 필터를 쓰면 안 됩니다.**
화면이 멈춰 있던 긴 구간을 만나면 앞부분을 통째로 버리고 시작 시각을 밀어버립니다
(실측: 11.7초 영상이 9.6초로 잘리고 뒷부분이 날아감). VFR로 두고 30fps 변환은 렌더 단계에서 합니다.

**영상 길이는 컨테이너 헤더의 `Duration` 으로 읽습니다.**
진행 로그(`time=`)의 마지막 줄은 실제 끝보다 앞설 수 있어서, 그 값으로 자르면 뒷부분이 잘립니다.

**앞뒤 카드를 빼면 ffmpeg 입력 번호가 밀립니다.**
자막 오버레이와 오디오가 몇 번째 입력인지 코드에 박아두면, 카드를 하나 뺐을 때 엉뚱한 입력을 가리킵니다.
번호를 만들면서 기억해 두고, 카드가 하나도 없으면 `concat` 을 아예 쓰지 않습니다.

**화면에 그리는 커서는 transform 으로 숨기면 안 됩니다.**
첫 움직임 전까지 점을 화면 밖에 두려고 `translate3d(-100px,-100px,0)` 을 걸어뒀는데, 이 값이 지워지지 않아
점이 계속 실제 포인터보다 100px 왼쪽 위에 그려졌습니다. 위치는 `left`/`top` 으로만 잡고,
`transform` 은 누를 때 크기 줄이는 데만 씁니다. (화면 캐스트에는 운영체제 커서가 안 찍혀서,
이 점이 영상 속 유일한 포인터입니다.)

**한글 페이지는 인코딩을 직접 정해야 합니다.**
`requests` 는 Content-Type 에 charset 이 없으면 ISO-8859-1 로 가정합니다. 그대로 두면 한글이 전부 깨진 채
모델에 들어갑니다. 헤더에 charset 이 없으면 `<meta charset>` → 바이트 추정 순으로 직접 정합니다.
(국내 구형 블로그에 흔한 EUC-KR 도 이 경로로 처리됩니다.)

**카드 배경 사진은 data: URI 로 심습니다.**
`set_content` 로 띄운 페이지는 about:blank 출신이라 `file://` 이미지를 못 불러옵니다. 원격 og:image 도
렌더 시점에 죽어 있을 수 있어서, 둘 다 미리 바이트로 받아 인라인합니다. 실패하면 사진 없는 레이아웃으로 자동 전환됩니다.

**한글은 ffmpeg 로 그리지 않습니다.** `drawtext` 는 폰트 문제가 잦고 정적 빌드엔 아예 없는 경우도 있습니다.
자막·인트로·아웃트로·이미지 카드는 전부 크롬에서 CSS로 그린 뒤 PNG로 얹습니다.
디자인을 바꾸려면 `templates/card.html` 과 `sns_autopilot/render/cards.py` 만 고치면 됩니다.

**과장광고 방지** — 원문에 없는 숫자·할인율을 만들지 않도록 지시하고, `banned` 목록은 코드로 한 번 더 걸러
`copy.json` 의 `risky_claims` 에 남깁니다. **발행 전에 이 항목은 사람이 확인하세요.**

**계정 정책** — SNS 발행은 각 플랫폼의 **공식 API**로만 합니다.
브라우저 자동 조작으로 SNS에 로그인해 글을 올리는 방식은 대부분 약관 위반이고 계정 정지 사유라서 넣지 않았습니다.
브라우저 자동화는 "내 홈페이지를 녹화하는 용도"로만 씁니다.

---

## 8. 구조

```
sns_autopilot/
├── cli.py                 명령줄 진입점 (argparse)
├── gui.py                 tkinter 창 (주소 → 캡쳐 → 인코딩)
├── pipeline.py            단계 조립 (manifest.json 으로 이어붙임)
├── config.py              YAML 로딩 · .env · ${ENV} 치환
├── paths.py               실행 폴더 구조
├── ffmpeg.py              ffmpeg 실행 래퍼
├── capture/
│   ├── recorder.py        시나리오 실행 + 녹화
│   ├── manual.py          사람이 시작·종료를 누르는 수동 녹화
│   ├── flows.py           주소만 있을 때 쓰는 기본 시나리오
│   ├── screencast.py      CDP 프레임 캡처 + 시간축 대응표
│   └── cursor.py          마우스 커서·클릭 파장 오버레이
├── render/
│   ├── shorts.py          숏츠 mp4 + GIF
│   ├── cards.py           인트로·아웃트로·자막 HTML
│   └── html2png.py        HTML → PNG (동봉 한글 폰트 인라인)
├── analyze/blog.py        RSS 탐색 · 본문 추출 · 중복 방지
├── generate/
│   ├── copy.py            Claude 구조화 출력(pydantic)으로 플랫폼별 카피
│   ├── prompts.py         플랫폼별 규칙·브랜드 프롬프트
│   └── image.py           홍보 이미지 카드
└── publish/
    ├── __init__.py        발행 라우팅 (dry-run 기본)
    ├── compose.py         본문·해시태그 조합, 글자 수 제한
    └── adapters/          file · webhook · postiz · x · threads · instagram · youtube
```
