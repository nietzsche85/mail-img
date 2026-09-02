import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
export const outDir = path.join(root, "out");

/** out/<runId>/ 아래에 이번 실행의 모든 산출물이 모입니다. */
export function runPaths(runId) {
  const base = path.join(outDir, runId);
  const p = {
    runId,
    base,
    capture: path.join(base, "capture"),
    render: path.join(base, "render"),
    images: path.join(base, "images"),
    copy: path.join(base, "copy"),
    queue: path.join(base, "queue"),
  };
  for (const dir of Object.values(p)) {
    if (typeof dir === "string" && dir.startsWith(outDir)) fs.mkdirSync(dir, { recursive: true });
  }
  return p;
}

export function newRunId() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

export function readJson(file, fallback = null) {
  try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch { return fallback; }
}

export function writeJson(file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(data, null, 2));
  return file;
}
