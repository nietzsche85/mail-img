import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";
import { log } from "../lib/log.js";
import { writeJson } from "../lib/paths.js";
import { CURSOR_INIT_SCRIPT } from "./cursor.js";
import { Screencast } from "./screencast.js";
import { root } from "../lib/paths.js";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** 로컬 HTML 경로를 적어도 열리게 해줍니다 (데모/사내 파일 테스트용). */
function normalizeUrl(url) {
  if (!url || /^[a-z]+:/i.test(url)) return url;
  return `file://${path.resolve(root, url)}`;
}

/** 문자열 하나만 온 경우도 셀렉터/텍스트 어느 쪽이든 받아줍니다. */
function resolveLocator(page, spec) {
  if (typeof spec === "string") {
    const looksLikeSelector = /[#.\[\]>:]/.test(spec) || /^[a-z]+$/i.test(spec);
    return looksLikeSelector ? page.locator(spec) : page.getByText(spec, { exact: false }).first();
  }
  let loc;
  if (spec.selector) loc = page.locator(spec.selector);
  else if (spec.role) loc = page.getByRole(spec.role, spec.name ? { name: spec.name } : undefined);
  else if (spec.label) loc = page.getByLabel(spec.label);
  else if (spec.placeholder) loc = page.getByPlaceholder(spec.placeholder);
  else if (spec.testId) loc = page.getByTestId(spec.testId);
  else if (spec.text) loc = page.getByText(spec.text, { exact: Boolean(spec.exact) });
  else throw new Error(`대상을 알 수 없는 스텝입니다: ${JSON.stringify(spec)}`);
  if (spec.nth !== undefined) loc = loc.nth(spec.nth);
  return loc.first();
}

/** 사람이 움직인 것처럼 마우스를 옮깁니다. 영상에서 클릭이 눈에 보이게 하려는 목적. */
async function glideTo(page, locator) {
  const box = await locator.boundingBox();
  if (!box) return;
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  const steps = 22;
  const from = page.__apMouse ?? { x: box.x, y: Math.max(0, box.y - 220) };
  for (let i = 1; i <= steps; i++) {
    const t = i / steps;
    const ease = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    await page.mouse.move(from.x + (x - from.x) * ease, from.y + (y - from.y) * ease);
    await sleep(10);
  }
  page.__apMouse = { x, y };
}

async function dismissAll(page, selectors) {
  for (const sel of selectors ?? []) {
    try {
      const loc = page.locator(sel).first();
      if (await loc.isVisible({ timeout: 400 })) {
        await loc.click({ timeout: 1200 });
        log.info(`방해 요소 닫음: ${sel}`);
        await sleep(250);
      }
    } catch { /* 없으면 그냥 넘어갑니다 */ }
  }
}

async function smoothScroll(page, { to = "bottom", pixels, duration = 2 }) {
  await page.evaluate(async ({ to, pixels, duration }) => {
    const start = window.scrollY;
    const max = document.documentElement.scrollHeight - window.innerHeight;
    let target = start;
    if (pixels !== undefined && pixels !== null) target = start + pixels;
    else if (to === "bottom") target = max;
    else if (to === "top") target = 0;
    else {
      const el = document.querySelector(to);
      if (el) target = window.scrollY + el.getBoundingClientRect().top - window.innerHeight / 3;
    }
    target = Math.max(0, Math.min(max, target));
    const frames = Math.max(1, Math.round(duration * 60));
    for (let i = 1; i <= frames; i++) {
      const t = i / frames;
      const ease = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      window.scrollTo(0, start + (target - start) * ease);
      await new Promise((r) => requestAnimationFrame(r));
    }
  }, { to, pixels, duration });
}

async function runStep(page, step, ctx) {
  if (step.goto) {
    await page.goto(normalizeUrl(step.goto), { waitUntil: "domcontentloaded" });
    await dismissAll(page, ctx.dismiss);
    return;
  }
  if (step.click) {
    const loc = resolveLocator(page, step.click);
    await loc.waitFor({ state: "visible", timeout: (step.timeout ?? 15) * 1000 });
    await glideTo(page, loc);
    await loc.click({ timeout: 10_000 });
    await page.waitForLoadState("domcontentloaded").catch(() => {});
    return;
  }
  if (step.fill) {
    const { value = "", typeDelay = 80 } = step.fill;
    const loc = resolveLocator(page, step.fill);
    await loc.waitFor({ state: "visible", timeout: (step.timeout ?? 15) * 1000 });
    await glideTo(page, loc);
    await loc.click({ timeout: 10_000 });
    await loc.fill("");
    await loc.pressSequentially(String(value), { delay: typeDelay });
    return;
  }
  if (step.press) {
    const { key = "Enter" } = typeof step.press === "string" ? { key: step.press } : step.press;
    if (typeof step.press === "object" && (step.press.selector || step.press.text)) {
      await resolveLocator(page, step.press).press(key);
    } else {
      await page.keyboard.press(key);
    }
    return;
  }
  if (step.hover) {
    const loc = resolveLocator(page, step.hover);
    await glideTo(page, loc);
    await loc.hover();
    return;
  }
  if (step.select) {
    await resolveLocator(page, step.select).selectOption(String(step.select.value));
    return;
  }
  if (step.scroll) {
    await smoothScroll(page, step.scroll);
    return;
  }
  if (step.highlight) {
    const sel = typeof step.highlight === "string" ? step.highlight : step.highlight.selector;
    const loc = page.locator(sel).first();
    await loc.scrollIntoViewIfNeeded().catch(() => {});
    await page.evaluate((s) => {
      const el = document.querySelector(s);
      if (el) { el.classList.add("ap-focus", "ap-pulse"); setTimeout(() => el.classList.remove("ap-pulse"), 2400); }
    }, sel);
    return;
  }
  if (step.wait !== undefined) {
    if (typeof step.wait === "number") return sleep(step.wait * 1000);
    const { selector, state = "visible", timeout = 15 } = step.wait;
    if (selector) return page.locator(selector).first().waitFor({ state, timeout: timeout * 1000 });
    return sleep((step.wait.seconds ?? 1) * 1000);
  }
  if (step.screenshot) {
    const name = typeof step.screenshot === "string" ? step.screenshot : `shot-${ctx.index}`;
    await page.screenshot({ path: path.join(ctx.dir, `${name}.png`) });
    return;
  }
  // caption / pause 만 있는 스텝은 "화면을 잠깐 보여주는" 용도입니다.
}

/**
 * 홈페이지를 자동으로 조작하면서 전 과정을 녹화합니다.
 * @returns {{video:string, timeline:object, shots:string[]}}
 */
export async function capture(flow, paths, { headless = true } = {}) {
  const dir = paths.capture;
  const viewport = {
    width: flow.viewport?.width ?? 540,
    height: flow.viewport?.height ?? 960,
  };
  const scale = flow.viewport?.deviceScaleFactor ?? 2;
  const frameSize = { width: viewport.width * scale, height: viewport.height * scale };

  log.step(`녹화 시작: ${flow.name ?? flow.url}`);
  const browser = await chromium.launch({
    headless,
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: ["--force-color-profile=srgb", "--font-render-hinting=none"],
  });
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: scale,
    locale: flow.locale ?? "ko-KR",
    timezoneId: flow.timezone ?? "Asia/Seoul",
    isMobile: viewport.width < 700,
    hasTouch: viewport.width < 700,
    // 화면 캐스트가 실패했을 때를 위한 예비 녹화 (CSS 픽셀 크기로 저장됩니다)
    recordVideo: { dir, size: viewport },
  });
  if (flow.showCursor !== false) await context.addInitScript(CURSOR_INIT_SCRIPT);

  const page = await context.newPage();
  const screencast = new Screencast(page, dir);
  await screencast.start({ maxWidth: frameSize.width, maxHeight: frameSize.height })
    .catch((e) => log.warn(`화면 캐스트를 못 켰습니다. 예비 녹화로 진행합니다 — ${e.message}`));
  const t0 = Date.now();
  const at = () => (Date.now() - t0) / 1000;

  const captions = [];
  const shots = [];
  const events = [];
  const ctx = { dismiss: flow.dismiss, dir, index: 0 };
  let videoPath = null;
  let usedScreencast = false;

  const pushCaption = (text) => {
    if (captions.length) captions[captions.length - 1].end = at();
    captions.push({ text, start: at(), end: null });
  };

  try {
    if (flow.url) {
      await page.goto(normalizeUrl(flow.url), { waitUntil: "domcontentloaded", timeout: 45_000 });
      await dismissAll(page, flow.dismiss);
      await sleep(600);
    }

    for (const [i, step] of (flow.steps ?? []).entries()) {
      ctx.index = i;
      if (step.caption) pushCaption(step.caption);
      const started = at();
      try {
        await runStep(page, step, ctx);
      } catch (e) {
        if (step.optional) { log.warn(`스텝 ${i + 1} 건너뜀 (optional): ${e.message.split("\n")[0]}`); }
        else throw new Error(`스텝 ${i + 1} 실패 — ${JSON.stringify(step).slice(0, 120)}\n  ${e.message.split("\n")[0]}`);
      }
      if (step.pause) await sleep(step.pause * 1000);
      else await sleep(400);

      const shot = path.join(dir, `step-${String(i + 1).padStart(2, "0")}.png`);
      await page.screenshot({ path: shot }).catch(() => {});
      if (fs.existsSync(shot)) shots.push(shot);
      events.push({ index: i + 1, start: started, end: at(), step });
    }

    await sleep(800);
    if (captions.length) captions[captions.length - 1].end = at();
  } finally {
    await screencast.stop();
    const video = page.video();
    await context.close();   // ← 이 시점에 예비 webm 이 디스크로 flush 됩니다
    await browser.close();

    videoPath = await screencast
      .assemble(path.join(dir, "recording.mp4"), { ...frameSize, fps: 30, t0: t0 / 1000 })
      .catch((e) => { log.warn(`프레임 합치기 실패 — 예비 녹화를 씁니다: ${e.message}`); return null; });
    if (videoPath) usedScreencast = true;
    else if (video) videoPath = await video.path();
  }

  // 영상 시간축에 맞춰 자막 시각을 다시 계산합니다 (화면 캐스트는 변화가 있을 때만 프레임을 주기 때문).
  const toVideo = (seconds) => (usedScreencast ? screencast.mapTime(seconds) : seconds);
  const timeline = {
    name: flow.name ?? "",
    url: flow.url ?? "",
    recordedAt: new Date(t0).toISOString(),
    wallDuration: (Date.now() - t0) / 1000,
    duration: usedScreencast ? screencast.videoDuration : (Date.now() - t0) / 1000,
    captions: captions.map((c) => ({ ...c, start: toVideo(c.start), end: toVideo(c.end ?? (Date.now() - t0) / 1000) })),
    events: events.map((e) => ({ ...e, start: toVideo(e.start), end: toVideo(e.end) })),
  };
  writeJson(path.join(dir, "timeline.json"), timeline);
  log.ok(`녹화 완료 · ${timeline.duration.toFixed(1)}초 · 자막 ${captions.length}개 · 스크린샷 ${shots.length}장`);
  return { video: videoPath, timeline, shots };
}
