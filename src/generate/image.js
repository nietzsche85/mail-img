import fs from "node:fs";
import path from "node:path";
import { log } from "../lib/log.js";
import { root } from "../lib/paths.js";
import { koreanFontFace, renderAll } from "../render/html2png.js";

const esc = (s) => String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
const emphasize = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<em>$1</em>");

function fill(template, vars) {
  return template.replace(/\{\{(\w+)\}\}/g, (_, key) => (vars[key] !== undefined ? String(vars[key]) : ""));
}

const MIME = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif" };

/**
 * 배경 사진을 data: URI 로 바꿔 페이지에 심습니다.
 * setContent 로 띄운 페이지는 about:blank 출신이라 file:// 이미지를 못 불러오고,
 * 원격 URL 은 렌더 시점에 죽어 있을 수 있습니다. 둘 다 미리 바이트로 받아 넣습니다.
 * 실패하면 빈 문자열 — 사진 없는 레이아웃으로 자동 전환됩니다.
 */
async function asDataUri(source) {
  if (!source) return "";
  if (String(source).startsWith("data:")) return String(source);
  try {
    if (/^https?:\/\//.test(source)) {
      const res = await fetch(source);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const mime = (res.headers.get("content-type") ?? "image/jpeg").split(";")[0];
      const buffer = Buffer.from(await res.arrayBuffer());
      return `data:${mime};base64,${buffer.toString("base64")}`;
    }
    const mime = MIME[path.extname(source).toLowerCase()] ?? "image/png";
    return `data:${mime};base64,${fs.readFileSync(source).toString("base64")}`;
  } catch (e) {
    log.warn(`배경 사진을 못 불러왔습니다 — 사진 없는 레이아웃으로 갑니다 (${e.message})`);
    return "";
  }
}

/**
 * 카피의 card 필드로 SNS 규격별 홍보 이미지를 굽습니다.
 * 배경 사진은 블로그 og:image 를 그대로 씁니다 (없으면 그라디언트).
 */
export async function generateImages({ copy, brand, image: cfg, article, paths, fallbackImage }) {
  const templateFile = path.isAbsolute(cfg.template) ? cfg.template : path.join(root, cfg.template);
  if (!fs.existsSync(templateFile)) throw new Error(`이미지 템플릿이 없습니다: ${templateFile}`);
  const template = fs.readFileSync(templateFile, "utf8");

  const card = copy.card ?? {};
  const bg = await asDataUri(article?.image || fallbackImage);
  const colors = brand.colors ?? {};

  const jobs = cfg.sizes.map((size) => {
    const vars = {
      FONT_CSS: koreanFontFace(),
      bodyClass: bg ? "withphoto" : "nophoto",
      width: size.width,
      height: size.height,
      bg: colors.bg ?? "#0B3D91",
      accent: colors.accent ?? "#4FC3F7",
      text: colors.text ?? "#FFFFFF",
      highlight: colors.highlight ?? "#FFD54F",
      image: bg,
      badge: esc(card.badge || brand.name),
      title: emphasize(card.title || copy.hook || ""),
      subtitle: esc(card.subtitle || copy.hookSub || ""),
      bullets: (card.bullets ?? []).map((b) => `<li>${esc(b)}</li>`).join(""),
      brand: esc(brand.name),
      cta: esc(copy.cta || brand.cta || ""),
    };
    return {
      html: fill(template, vars),
      width: size.width,
      height: size.height,
      out: path.join(paths.images, `${size.name}.png`),
    };
  });

  const files = await renderAll(jobs);
  log.ok(`홍보 이미지 ${files.length}장 → ${path.relative(process.cwd(), paths.images)}/`);
  return files;
}
