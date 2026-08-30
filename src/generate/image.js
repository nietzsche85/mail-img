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

/**
 * 카피의 card 필드로 SNS 규격별 홍보 이미지를 굽습니다.
 * 배경 사진은 블로그 og:image 를 그대로 씁니다 (없으면 그라디언트).
 */
export async function generateImages({ copy, brand, image: cfg, article, paths, fallbackImage }) {
  const templateFile = path.isAbsolute(cfg.template) ? cfg.template : path.join(root, cfg.template);
  if (!fs.existsSync(templateFile)) throw new Error(`이미지 템플릿이 없습니다: ${templateFile}`);
  const template = fs.readFileSync(templateFile, "utf8");

  const card = copy.card ?? {};
  const bg = article?.image || (fallbackImage ? `file://${fallbackImage}` : "");
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
