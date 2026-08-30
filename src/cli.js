#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { log } from "./lib/log.js";
import { loadEnv } from "./lib/config.js";
import { root } from "./lib/paths.js";
import { ffmpegPath } from "./lib/ffmpeg.js";
import { koreanFontFace } from "./render/html2png.js";
import { ADAPTERS } from "./publish/index.js";
import * as pipeline from "./pipeline.js";

const HELP = `
SNS 오토파일럿 — 홈페이지 녹화 → 숏츠/GIF → 블로그 분석 → 카피·이미지 → 자동 발행

사용법
  node src/cli.js <명령> [옵션]

명령
  run          전체 파이프라인 (분석 → 녹화 → 카피 → 렌더 → 이미지 → 발행)
  capture      홈페이지를 자동 조작하며 화면 녹화 (새 실행 생성)
  analyze      블로그 글 수집·분석
  copy         카피 생성 (Claude)
  render       녹화본 → 숏츠 mp4 + GIF
  image        홍보 이미지 카드 생성
  publish      발행 (기본은 미리보기, --publish 를 붙여야 실제 발행)
  doctor       실행 환경 점검

옵션
  --config <경로>    설정 파일 (기본 config/pipeline.yaml)
  --flow <경로>      녹화 시나리오 yaml
  --url <주소>       분석할 블로그 글 주소 / capture 시 시작 주소
  --feed <주소>      RSS 주소
  --run <실행ID>     특정 실행 폴더에 이어서 작업
  --latest           가장 최근 실행에 이어서 작업 (capture 외 기본값)
  --variant <n>      발행할 시안 번호 (기본 1)
  --target <이름>    발행 대상 지정 (여러 번 사용 가능)
  --publish          실제로 발행합니다 (없으면 미리보기만)
  --headed           브라우저 창을 띄워서 녹화 (디버깅용)

예시
  node src/cli.js doctor
  node src/cli.js capture --flow config/flows/example-homepage.yaml --headed
  node src/cli.js run --url https://blog.example.com/post/123
  node src/cli.js publish --latest --target postiz --publish
`;

function parseArgs(argv) {
  const opts = { targets: [] };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    switch (a) {
      case "--config": opts.config = next(); break;
      case "--flow": opts.flow = next(); break;
      case "--url": opts.url = next(); break;
      case "--feed": opts.feed = next(); break;
      case "--run": opts.run = next(); break;
      case "--latest": opts.latest = true; break;
      case "--variant": opts.variant = Number(next()); break;
      case "--target": opts.targets.push(next()); break;
      case "--publish": opts.publish = true; break;
      case "--headed": opts.headed = true; break;
      case "--skip-capture": opts.skipCapture = true; break;
      case "--skip-analyze": opts.skipAnalyze = true; break;
      case "-h": case "--help": opts.help = true; break;
      default: rest.push(a);
    }
  }
  return { opts, rest };
}

async function doctor() {
  const checks = [];
  const push = (ok, label, hint = "") => checks.push({ ok, label, hint });

  push(Number(process.versions.node.split(".")[0]) >= 20, `Node ${process.versions.node}`, "Node 20 이상이 필요합니다.");

  const ff = ffmpegPath();
  push(ff !== "ffmpeg" || fs.existsSync("/usr/bin/ffmpeg"), `ffmpeg: ${ff}`, "npm install 로 ffmpeg-static 을 받아주세요.");

  let chromiumOk = false;
  try { const { chromium } = await import("playwright"); chromiumOk = Boolean(chromium.executablePath()); } catch { /* 미설치 */ }
  push(chromiumOk, "Chromium (playwright)", "npx playwright install chromium 을 실행하세요.");

  push(koreanFontFace().includes("@font-face"), "한글 폰트 (Noto Sans KR)", "npm install 로 @fontsource/noto-sans-kr 를 받아주세요.");

  push(Boolean(process.env.ANTHROPIC_API_KEY || process.env.ANTHROPIC_AUTH_TOKEN), "ANTHROPIC_API_KEY", ".env 에 API 키를 넣어주세요.");

  for (const [name, adapter] of Object.entries(ADAPTERS)) {
    if (name === "file") continue;
    const ok = adapter.configured();
    checks.push({ ok, label: `발행 채널: ${name}`, hint: "미설정 — 쓰려면 .env 를 채우세요", soft: true });
  }

  for (const c of checks) {
    if (c.ok) log.ok(c.label);
    else if (c.soft) log.info(`· ${c.label} — ${c.hint}`);
    else log.error(`${c.label} — ${c.hint}`);
  }
  const hardFail = checks.some((c) => !c.ok && !c.soft);
  if (hardFail) process.exitCode = 1;
  else log.ok("필수 항목 모두 통과");
}

async function main() {
  loadEnv(path.join(root, ".env"));
  const [command, ...argv] = process.argv.slice(2);
  const { opts } = parseArgs(argv);

  if (!command || opts.help || command === "help") { console.log(HELP); return; }
  if (command === "doctor") return doctor();

  // capture / run 은 새 실행을 만들고, 나머지는 기본적으로 최근 실행을 이어받습니다.
  if (!["capture", "run"].includes(command) && !opts.run) opts.latest = true;

  if (command === "run") { await pipeline.runAll(opts); return; }

  const ctx = pipeline.openRun(opts);
  switch (command) {
    case "capture": await pipeline.stepCapture(ctx, opts); break;
    case "analyze": await pipeline.stepAnalyze(ctx, opts); break;
    case "copy": await pipeline.stepCopy(ctx, opts); break;
    case "render": await pipeline.stepRender(ctx); break;
    case "image": await pipeline.stepImage(ctx); break;
    case "publish": await pipeline.stepPublish(ctx, opts); break;
    default:
      log.error(`알 수 없는 명령: ${command}`);
      console.log(HELP);
      process.exitCode = 1;
  }
}

main().catch((e) => {
  log.error(e.message);
  if (process.env.DEBUG) console.error(e);
  process.exitCode = 1;
});
