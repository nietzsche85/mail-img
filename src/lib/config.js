import fs from "node:fs";
import path from "node:path";
import YAML from "yaml";
import { root } from "./paths.js";

/** .env 를 아주 단순하게 읽어 process.env 에 채웁니다 (이미 있는 값은 덮어쓰지 않음). */
export function loadEnv(file = path.join(root, ".env")) {
  if (!fs.existsSync(file)) return;
  for (const raw of fs.readFileSync(file, "utf8").split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    if (process.env[key] === undefined) process.env[key] = value;
  }
}

/** 문자열 안의 ${VAR} 을 환경변수로 치환합니다. 없으면 빈 문자열. */
export function expandEnv(value) {
  if (typeof value === "string") {
    return value.replace(/\$\{([A-Z0-9_]+)\}/gi, (_, name) => process.env[name] ?? "");
  }
  if (Array.isArray(value)) return value.map(expandEnv);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, expandEnv(v)]));
  }
  return value;
}

export function loadYaml(file) {
  const abs = path.isAbsolute(file) ? file : path.join(root, file);
  if (!fs.existsSync(abs)) throw new Error(`설정 파일을 찾을 수 없습니다: ${abs}`);
  return expandEnv(YAML.parse(fs.readFileSync(abs, "utf8")) ?? {});
}

const DEFAULTS = {
  brand: { name: "브랜드", voice: "친근하고 구체적으로", banned: [], cta: "", colors: {} },
  capture: { flow: "config/flows/example-homepage.yaml" },
  render: {
    shorts: { width: 1080, height: 1920, fps: 30, maxDuration: 28, speed: "auto", introSeconds: 1.6, outroSeconds: 0, bgm: "" },
    gif: { width: 640, fps: 12, maxDuration: 8 },
  },
  blog: { feed: "", urls: [], limit: 3, stateFile: ".state/seen.json" },
  copy: { model: "claude-opus-5", effort: "high", platforms: ["instagram", "threads", "x"], variants: 2, language: "ko" },
  image: { template: "templates/card.html", sizes: [{ name: "feed", width: 1080, height: 1350 }] },
  publish: { targets: ["file"], scheduleAt: "" },
};

function deepMerge(base, override) {
  if (Array.isArray(override)) return override;
  if (override === null || override === undefined) return base;
  if (typeof override !== "object" || typeof base !== "object" || base === null) return override;
  const out = { ...base };
  for (const [k, v] of Object.entries(override)) out[k] = deepMerge(base[k], v);
  return out;
}

export function loadConfig(file = "config/pipeline.yaml") {
  loadEnv();
  return deepMerge(DEFAULTS, loadYaml(file));
}
