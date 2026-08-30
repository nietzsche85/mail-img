import fs from "node:fs";
import path from "node:path";
import * as ff from "../lib/ffmpeg.js";
import { log } from "../lib/log.js";

/**
 * CDP 화면 캐스트로 실제 디바이스 픽셀(예: 1080x1920) 프레임을 그대로 받아옵니다.
 * Playwright 내장 녹화는 CSS 픽셀 크기로만 찍혀서 세로 영상으로 확대하면 뿌옇게 나옵니다.
 */
export class Screencast {
  constructor(page, dir) {
    this.page = page;
    this.dir = path.join(dir, "frames");
    this.frames = [];
    this.client = null;
  }

  async start({ maxWidth, maxHeight, quality = 92 } = {}) {
    fs.mkdirSync(this.dir, { recursive: true });
    this.client = await this.page.context().newCDPSession(this.page);
    this.client.on("Page.screencastFrame", async (frame) => {
      const file = path.join(this.dir, `f_${String(this.frames.length).padStart(6, "0")}.jpg`);
      fs.writeFileSync(file, Buffer.from(frame.data, "base64"));
      this.frames.push({ file, ts: frame.metadata.timestamp ?? Date.now() / 1000, wall: Date.now() / 1000 });
      try { await this.client.send("Page.screencastFrameAck", { sessionId: frame.sessionId }); }
      catch { /* 페이지가 이미 닫혔으면 무시 */ }
    });
    await this.client.send("Page.startScreencast", {
      format: "jpeg", quality, maxWidth, maxHeight, everyNthFrame: 1,
    });
  }

  async stop() {
    try { await this.client?.send("Page.stopScreencast"); } catch { /* 이미 정리됨 */ }
  }

  /**
   * 프레임마다 실제 간격을 살려서 mp4 로 묶습니다.
   * 화면이 안 바뀌면 프레임이 안 오기 때문에 영상 길이는 실제 조작 시간보다 짧습니다.
   * 자막을 제자리에 붙이려면 "실제 시각 → 영상 시각" 대응표가 필요해서 같이 만들어 둡니다.
   */
  async assemble(outFile, { width, height, fps = 30, t0 = 0 }) {
    if (this.frames.length < 5) return null;
    const listFile = path.join(this.dir, "frames.txt");
    const lines = ["ffconcat version 1.0"];
    this.timeMap = [];
    let cursor = 0;
    for (let i = 0; i < this.frames.length; i++) {
      const next = this.frames[i + 1];
      const d = next ? Math.min(2, Math.max(1 / 60, next.ts - this.frames[i].ts)) : 1 / fps;
      this.timeMap.push({ wall: this.frames[i].wall - t0, video: cursor });
      cursor += d;
      lines.push(`file '${path.basename(this.frames[i].file)}'`, `duration ${d.toFixed(4)}`);
    }
    this.videoDuration = cursor;
    lines.push(`file '${path.basename(this.frames.at(-1).file)}'`);
    fs.writeFileSync(listFile, lines.join("\n"));

    await ff.run([
      "-f", "concat", "-safe", "0", "-i", listFile,
      "-vf", `fps=${fps},scale=${width}:${height}:force_original_aspect_ratio=decrease,pad=${width}:${height}:(ow-iw)/2:(oh-ih)/2:color=black`,
      "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
      outFile,
    ]);
    log.info(`화면 캐스트 ${this.frames.length}프레임 → ${path.basename(outFile)} (${cursor.toFixed(1)}초)`);
    return outFile;
  }

  /** 녹화 시작 후 n초(실제 시각)가 영상에서는 몇 초인지 환산합니다. */
  mapTime(wallSeconds) {
    const map = this.timeMap;
    if (!map?.length) return wallSeconds;
    if (wallSeconds <= map[0].wall) return 0;
    if (wallSeconds >= map.at(-1).wall) return this.videoDuration;
    let lo = 0, hi = map.length - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (map[mid].wall <= wallSeconds) lo = mid; else hi = mid;
    }
    const span = map[hi].wall - map[lo].wall;
    const ratio = span > 0 ? (wallSeconds - map[lo].wall) / span : 0;
    return map[lo].video + (map[hi].video - map[lo].video) * ratio;
  }
}
