import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { log } from "./log.js";

const require = createRequire(import.meta.url);

/** ffmpeg-static 이 받아둔 정적 바이너리를 쓰고, 없으면 시스템 ffmpeg 로 넘어갑니다. */
export function ffmpegPath() {
  if (process.env.FFMPEG_PATH) return process.env.FFMPEG_PATH;
  try {
    const p = require("ffmpeg-static");
    if (p) return p;
  } catch { /* fall through */ }
  return "ffmpeg";
}

export function run(args, { quiet = true } = {}) {
  const bin = ffmpegPath();
  return new Promise((resolve, reject) => {
    const child = spawn(bin, ["-hide_banner", "-loglevel", quiet ? "error" : "info", "-y", ...args], {
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stderr = "";
    child.stderr.on("data", (d) => { stderr += d.toString(); });
    child.on("error", (e) => reject(new Error(`ffmpeg 실행 실패 (${bin}): ${e.message}`)));
    child.on("close", (code) => {
      if (code === 0) return resolve(stderr);
      log.error(stderr.split("\n").slice(-25).join("\n"));
      reject(new Error(`ffmpeg 종료 코드 ${code}`));
    });
  });
}

/**
 * ffprobe 없이 ffmpeg 만으로 길이를 잽니다.
 * 컨테이너 헤더의 Duration 을 먼저 봅니다. 진행 로그(time=)는 마지막 줄이 실제 끝보다
 * 앞설 수 있어서, 그걸로 자르면 영상 뒷부분이 날아갑니다.
 */
export async function duration(file) {
  const stderr = String(
    await run(["-i", file, "-f", "null", "-"], { quiet: false }).catch((e) => String(e))
  );
  const header = stderr.match(/Duration:\s*(\d+):(\d+):(\d+\.\d+)/);
  if (header) {
    const [, h, m, s] = header;
    return Number(h) * 3600 + Number(m) * 60 + Number(s);
  }
  const progress = [...stderr.matchAll(/time=(\d+):(\d+):(\d+\.\d+)/g)];
  if (!progress.length) return 0;
  const [, h, m, s] = progress[progress.length - 1];
  return Number(h) * 3600 + Number(m) * 60 + Number(s);
}
