import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { chromium } from "playwright";

const require = createRequire(import.meta.url);

/**
 * 한글 웹폰트를 file:// 로 인라인합니다.
 * ffmpeg 의 drawtext 는 한글 폰트 문제가 잦아서, 글자는 전부 크롬에서 그린 뒤 PNG 로 얹습니다.
 */
export function koreanFontFace() {
  let dir;
  try {
    dir = path.join(path.dirname(require.resolve("@fontsource/noto-sans-kr/package.json")), "files");
  } catch {
    return `/* @fontsource/noto-sans-kr 미설치 — 시스템 폰트로 대체 */`;
  }
  const weights = [300, 400, 500, 700, 800, 900];
  return weights
    .map((w) => {
      const file = path.join(dir, `noto-sans-kr-korean-${w}-normal.woff2`);
      if (!fs.existsSync(file)) return "";
      return `@font-face{font-family:'AP Sans';font-style:normal;font-weight:${w};font-display:block;src:url('file://${file}') format('woff2');}`;
    })
    .join("\n");
}

export const BASE_CSS = `
${koreanFontFace()}
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%}
body{font-family:'AP Sans','Noto Sans KR',system-ui,sans-serif;-webkit-font-smoothing:antialiased;
  word-break:keep-all;line-height:1.35}
`;

/**
 * HTML 문자열 여러 개를 한 번에 PNG 로 굽습니다.
 * @param {Array<{html:string,width:number,height:number,out:string,transparent?:boolean}>} jobs
 */
export async function renderAll(jobs) {
  if (!jobs.length) return [];
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: ["--force-color-profile=srgb"],
  });
  const results = [];
  try {
    for (const job of jobs) {
      const page = await browser.newPage({
        viewport: { width: job.width, height: job.height },
        deviceScaleFactor: 1,
      });
      await page.setContent(job.html, { waitUntil: "load" });
      await page.evaluate(() => document.fonts.ready);
      fs.mkdirSync(path.dirname(job.out), { recursive: true });
      await page.screenshot({ path: job.out, omitBackground: Boolean(job.transparent) });
      await page.close();
      results.push(job.out);
    }
  } finally {
    await browser.close();
  }
  return results;
}
