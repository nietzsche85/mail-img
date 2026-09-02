# 채널 연결 가이드

발행 대상은 `config/pipeline.yaml` 의 `publish.targets` 에 적고, 자격 증명은 `.env`(또는 GitHub Actions Secrets)에 넣습니다.
설정되지 않은 채널은 **자동으로 건너뜁니다.** `node src/cli.js doctor` 로 무엇이 연결됐는지 확인할 수 있습니다.

---

## 어떤 방식을 고를까

| | 직접 API 연결 | Postiz 경유 | 웹훅(n8n/Make) |
|---|---|---|---|
| 초기 설정 | 채널마다 개발자 앱 등록 필요 | 한 번만 연결 | 워크플로 1개 |
| 예약 발행 | 직접 구현 필요 | 기본 제공 | 도구가 처리 |
| 채널 수 | 이 저장소는 4개 지원 | 28개 이상 | 도구에 따라 다름 |
| 토큰 관리 | 만료 때마다 직접 갱신 | Postiz가 갱신 | 도구가 갱신 |
| 추천 | 한두 채널만 쓸 때 | **대부분의 경우** | 이미 쓰고 있다면 |

`targets: [file]` 로 두고 `out/<실행ID>/queue/*.txt` 를 복붙해서 수동 발행하는 것도 완전히 유효한 운영 방식입니다.
자동 발행은 처음 2주 정도 `file` 로 결과물을 눈으로 확인한 뒤 켜는 걸 권합니다.

---

## Postiz (권장)

X · 인스타그램 · 스레드 · 유튜브 · 틱톡 · 링크드인 · 레딧 등 여러 채널을 하나의 API로 처리합니다.
클라우드(postiz.com)와 셀프호스팅(도커) 둘 다 됩니다.

### 두 종류의 키를 헷갈리지 마세요

| | 무엇 | 어디에 넣나 |
|---|---|---|
| **Public API 키** | Postiz 자체를 조작하는 키 (`Authorization` 헤더) | **이 도구의 `.env`** |
| **CLIENT_ID / CLIENT_SECRET** | X·유튜브 등 각 SNS의 개발자 앱 자격증명. Postiz가 채널을 연결할 때 씁니다 | **셀프호스팅 Postiz 서버**의 환경변수 (`YOUTUBE_CLIENT_ID`, `FACEBOOK_APP_ID` 등) |

클라우드 Postiz를 쓰면 CLIENT_ID/SECRET은 아예 필요 없습니다 — 화면에서 채널을 연결하면 끝입니다.

### 설정

1. Postiz에서 채널들을 연결합니다.
2. **Settings → Public API** 에서 API 키를 발급합니다.

```bash
POSTIZ_API_URL=https://api.postiz.com     # 셀프호스팅이면 그 주소
POSTIZ_API_KEY=여기에_키
```

3. 연결된 채널을 확인합니다.

```bash
python -m sns_autopilot channels      # Node: node src/cli.js channels
```

```
✓ 연결된 채널 3개
  x            마이리얼트립 @myrealtrip
               id: cm4ean69r0003w8w1cdomox9n
  instagram    myrealtrip @myrealtrip_official
               id: cm4instagram0001
  youtube      마이리얼트립 TV
               id: cm4youtube0001

자동 매칭된 채널: x, instagram, youtube
```

**매핑은 안 넣어도 됩니다.** 채널 목록의 `identifier` 로 자동으로 찾습니다.
채널이 여러 개라 고정하고 싶을 때만 위 명령이 만들어주는 `POSTIZ_INTEGRATIONS=...` 줄을 `.env` 에 넣으세요.

`config/pipeline.yaml` 의 `publish.scheduleAt` 에 ISO 시각을 넣으면 예약 발행됩니다.

### 알아둘 것

- **시간당 30요청 제한**입니다. 발행 1건당 미디어 업로드 포함 2요청이 나가므로, 한 번에 올릴 수 있는 건 대략 14건입니다.
- 요청 본문의 `settings.__type` 에는 채널의 provider 이름(`instagram`, `x`, `youtube` …)이 들어가야 합니다.
  이 값은 채널 목록에서 받은 `identifier` 를 그대로 씁니다. 빠지면 일부 채널에서 400 이 납니다.
- UI의 "채널"이 API에서는 "integration" 입니다.
- 첨부 파일은 먼저 `/public/v1/upload` 로 올린 뒤, 받은 `{id, path}` 를 본문의 `image` 배열에 넣습니다.

---

## X (트위터)

1. [developer.x.com](https://developer.x.com) 에서 앱 생성
2. **User authentication settings** → 권한을 `Read and Write` 로 변경
3. Keys and tokens 에서 API Key/Secret 과 Access Token/Secret 발급 (권한 변경 **후** 재발급해야 합니다)

```bash
X_API_KEY=...
X_API_SECRET=...
X_ACCESS_TOKEN=...
X_ACCESS_SECRET=...
```

동영상은 INIT → APPEND → FINALIZE → 처리 대기 순으로 올라갑니다.
무료 등급은 월 게시 수 제한이 있으니 시안 개수를 늘릴 때 확인하세요.

---

## Instagram (릴스)

**프로페셔널(비즈니스/크리에이터) 계정 + 페이스북 페이지 연결**이 필수입니다. 개인 계정은 API 발행이 불가합니다.

1. Meta 개발자 앱 생성 → Instagram Graph API 제품 추가
2. `instagram_content_publish`, `pages_read_engagement` 권한 승인
3. 장기 액세스 토큰 발급 (60일마다 갱신 필요)

```bash
IG_USER_ID=...
IG_ACCESS_TOKEN=...
PUBLIC_MEDIA_BASE_URL=https://cdn.mysite.com/sns
```

> **중요:** 인스타그램과 스레드는 미디어를 파일 업로드가 아니라 **공개 URL**로 받습니다.
> 렌더 결과물(`out/<실행ID>/render/shorts.mp4` 등)을 S3·Cloudflare R2·GitHub Pages 같은 곳에 올린 뒤
> 그 베이스 주소를 `PUBLIC_MEDIA_BASE_URL` 에 넣어야 합니다. 이게 없으면 발행이 실패합니다.
> (Postiz를 쓰면 이 과정이 필요 없습니다.)
>
> 주소는 `<베이스>/<실행ID>/<폴더>/<파일>` 형태로 만들어집니다.
> 예: `PUBLIC_MEDIA_BASE_URL=https://cdn.mysite.com/sns` 이고 `out/20260830-124238/render/shorts.mp4` 이면
> → `https://cdn.mysite.com/sns/20260830-124238/render/shorts.mp4`
> 즉 `out/` 아래 실행 폴더를 통째로 올리면 경로가 맞습니다.

릴스 사양: 세로 9:16, 3초~15분, mp4(H.264/AAC). 이 저장소의 렌더 설정은 이 사양에 맞춰져 있습니다.

---

## Threads

Meta 개발자 앱에서 Threads API 를 활성화하고 `threads_basic`, `threads_content_publish` 권한을 받습니다.

```bash
THREADS_USER_ID=...
THREADS_ACCESS_TOKEN=...
```

인스타그램과 마찬가지로 미디어는 공개 URL 이 필요합니다.

---

## YouTube Shorts

1. Google Cloud 프로젝트 → **YouTube Data API v3** 사용 설정
2. OAuth 클라이언트(데스크톱 앱) 생성
3. `https://www.googleapis.com/auth/youtube.upload` 범위로 1회 인증해 refresh token 확보

```bash
YT_CLIENT_ID=...
YT_CLIENT_SECRET=...
YT_REFRESH_TOKEN=...
YT_PRIVACY=public          # 테스트 중에는 private 로 두세요
```

세로 영상 + 3분 이하 + 제목·설명에 `#Shorts` 가 있으면 쇼츠로 분류됩니다.
할당량이 하루 10,000 units 이고 업로드 1건이 약 1,600 units 이라 **하루 6건 정도**가 상한입니다.

---

## 네이버 블로그

네이버는 외부 앱이 블로그 글을 자동 발행하는 공개 API를 제공하지 않습니다.
그래서 이 저장소는 네이버용 원고를 `out/<실행ID>/queue/naver_blog-v1.txt` 로 만들어만 두고, 게시는 사람이 합니다.
`config/pipeline.yaml` 의 `copy.platforms` 에 `naver_blog` 를 넣으면 소제목까지 갖춘 본문이 생성됩니다.

---

## 웹훅 (n8n · Make · Zapier)

이미 자동화 도구를 쓰고 있다면 가장 간단합니다.

```bash
WEBHOOK_URL=https://n8n.mysite.com/webhook/sns
```

전송되는 JSON:

```json
{
  "runId": "20260830-124238",
  "platform": "instagram",
  "variant": 1,
  "title": "",
  "text": "본문 + 해시태그",
  "hashtags": ["#홍콩여행"],
  "firstComment": "",
  "assets": { "video": "/절대/경로/shorts.mp4", "image": "/절대/경로/feed.png" }
}
```

경로는 파이프라인을 실행한 머신 기준입니다. 다른 서버로 넘길 때는 미디어를 먼저 업로드하고 URL로 바꿔주세요.

---

## 운영 체크리스트

- [ ] 처음 2주는 `targets: [file]` 로 두고 결과물을 눈으로 확인
- [ ] `copy.json` 의 `risky_claims` 는 매번 확인 (과장광고 표시광고법 이슈)
- [ ] 광고성 게시물에는 `#광고` `#협찬` 등 표기 의무를 지켰는지 확인
- [ ] 녹화 시나리오에 실제 고객 정보나 결제 화면이 들어가지 않는지 확인
- [ ] 토큰 만료일 캘린더에 등록 (인스타·스레드 60일)
- [ ] 같은 문구를 여러 채널에 그대로 뿌리지 말 것 — `copy.platforms` 로 채널별 문구가 따로 나옵니다
