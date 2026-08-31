import { BASE_CSS } from "./html2png.js";

const esc = (s) => String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

/** **강조** 문법을 accent 색 span 으로 바꿉니다. */
const emphasize = (s, accent) =>
  esc(s).replace(/\*\*(.+?)\*\*/g, `<span style="color:${accent}">$1</span>`);

const palette = (brand) => ({
  bg: brand?.colors?.bg ?? "#0B3D91",
  accent: brand?.colors?.accent ?? "#4FC3F7",
  text: brand?.colors?.text ?? "#FFFFFF",
  highlight: brand?.colors?.highlight ?? "#FFD54F",
});

/** 영상 위에 얹을 자막 (투명 배경). 하단 UI 를 피해 안전 영역에 배치합니다. */
export function captionHtml(text, { width, height, brand }) {
  const c = palette(brand);
  return `<!doctype html><meta charset="utf-8"><style>${BASE_CSS}
  body{background:transparent;display:flex;align-items:flex-end;justify-content:center;padding:0 64px ${Math.round(height * 0.19)}px}
  .box{max-width:100%;background:rgba(10,14,24,.82);backdrop-filter:blur(2px);
    border-radius:28px;padding:30px 40px;box-shadow:0 18px 50px rgba(0,0,0,.45)}
  .t{font-size:${Math.round(width * 0.062)}px;font-weight:800;color:${c.text};text-align:center;
    letter-spacing:-.02em;text-shadow:0 3px 12px rgba(0,0,0,.5)}
  </style><div class="box"><div class="t">${emphasize(text, c.highlight)}</div></div>`;
}

/**
 * 첫 1.5초를 잡는 훅 카드.
 * 위쪽 배지는 기본으로 넣지 않습니다. 브랜드 이름이 첫 화면에 박히면
 * 광고처럼 보여서 이탈이 늘어납니다. 넣고 싶으면 설정에 brand.badge 를 적으세요.
 */
export function introHtml({ hook, sub, brand, width, height }) {
  const c = palette(brand);
  const badge = brand?.badge ?? "";
  return `<!doctype html><meta charset="utf-8"><style>${BASE_CSS}
  body{background:linear-gradient(160deg,${c.bg} 0%,#04122f 100%);color:${c.text};
    display:flex;flex-direction:column;align-items:center;justify-content:center;padding:0 80px;text-align:center}
  .badge{border:2px solid ${c.accent};color:${c.accent};border-radius:999px;
    padding:12px 28px;font-size:${Math.round(width * 0.031)}px;font-weight:700;margin-bottom:48px}
  .hook{font-size:${Math.round(width * 0.098)}px;font-weight:900;letter-spacing:-.035em;line-height:1.22}
  .sub{margin-top:36px;font-size:${Math.round(width * 0.041)}px;font-weight:500;opacity:.82}
  .bar{margin-top:64px;width:120px;height:8px;border-radius:8px;background:${c.accent}}
  </style>
  ${badge ? `<div class="badge">${esc(badge)}</div>` : ""}
  <div class="hook">${emphasize(hook, c.highlight)}</div>
  ${sub ? `<div class="sub">${esc(sub)}</div>` : ""}
  <div class="bar"></div>`;
}

/** 마지막 CTA 카드. */
export function outroHtml({ cta, brand, width, height }) {
  const c = palette(brand);
  return `<!doctype html><meta charset="utf-8"><style>${BASE_CSS}
  body{background:linear-gradient(200deg,#04122f 0%,${c.bg} 100%);color:${c.text};
    display:flex;flex-direction:column;align-items:center;justify-content:center;padding:0 80px;text-align:center}
  .cta{font-size:${Math.round(width * 0.078)}px;font-weight:900;letter-spacing:-.03em;line-height:1.25}
  .arrow{margin-top:44px;font-size:${Math.round(width * 0.1)}px;color:${c.accent};animation:none}
  .name{margin-top:56px;font-size:${Math.round(width * 0.036)}px;font-weight:700;opacity:.75;letter-spacing:.08em}
  </style>
  <div class="cta">${emphasize(cta, c.highlight)}</div>
  <div class="arrow">↓</div>
  <div class="name">${esc(brand?.name ?? "")}</div>`;
}
