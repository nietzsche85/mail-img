import fs from "node:fs";
import path from "node:path";
import { log } from "../lib/log.js";
import * as ff from "../lib/ffmpeg.js";
import { renderAll } from "./html2png.js";
import { captionHtml, introHtml, outroHtml } from "./cards.js";

const q = (n) => Number(n.toFixed(3));

/**
 * 녹화본(webm) + 자막 타임라인 → 세로 숏츠 mp4 와 GIF.
 * 글자는 전부 크롬에서 PNG 로 구워 얹기 때문에 한글이 깨지지 않습니다.
 */
export async function renderShorts({ video, timeline, brand, render, paths, hook, sub, cta }) {
  const { width: W, height: H, fps: FPS, maxDuration, introSeconds, outroSeconds, bgm } = render.shorts;
  const outMp4 = path.join(paths.render, "shorts.mp4");
  const outGif = path.join(paths.render, "preview.gif");
  const outCover = path.join(paths.render, "cover.png");

  const rawDuration = (await ff.duration(video)) || timeline.duration || 10;
  let factor = 1;
  if (render.shorts.speed === "auto") {
    factor = rawDuration > maxDuration ? Math.min(2.5, rawDuration / maxDuration) : 1;
  } else {
    factor = Number(render.shorts.speed) || 1;
  }
  const rawLimit = Math.min(rawDuration, maxDuration * factor);
  const bodyDuration = rawLimit / factor;
  const total = introSeconds + bodyDuration + outroSeconds;
  log.info(`원본 ${rawDuration.toFixed(1)}초 → 배속 ${factor.toFixed(2)}x → 본편 ${bodyDuration.toFixed(1)}초 (총 ${total.toFixed(1)}초)`);

  // ── 1) 오버레이용 PNG 굽기 ────────────────────────────────
  const captions = (timeline.captions ?? [])
    .filter((c) => c.text && (c.end ?? rawDuration) > c.start)
    .map((c, i) => ({
      ...c,
      // 배속을 걸었으면 자막 시간도 같이 당겨야 합니다.
      start: q(Math.min(bodyDuration, c.start / factor)),
      end: q(Math.min(bodyDuration, (c.end ?? rawDuration) / factor)),
      file: path.join(paths.render, `caption-${String(i + 1).padStart(2, "0")}.png`),
    }))
    .filter((c) => c.end - c.start > 0.25);

  // 인트로·아웃트로는 초를 0 으로 두면 카드 자체가 빠집니다.
  const hasIntro = introSeconds > 0;
  const hasOutro = outroSeconds > 0;
  const introPng = path.join(paths.render, "intro.png");
  const outroPng = path.join(paths.render, "outro.png");

  const jobs = [];
  if (hasIntro) jobs.push({ html: introHtml({ hook, sub, brand, width: W, height: H }), width: W, height: H, out: introPng });
  // 비워두면 그 줄이 안 나오도록, 여기서 기본 문구를 끼워넣지 않습니다.
  if (hasOutro) jobs.push({ html: outroHtml({ cta: cta || brand.cta || "", brand, width: W, height: H }), width: W, height: H, out: outroPng });
  jobs.push(...captions.map((c) => ({
    html: captionHtml(c.text, { width: W, height: H, brand }),
    width: W, height: H, out: c.file, transparent: true,
  })));
  await renderAll(jobs);

  // 껐는데 예전 실행의 카드가 남아 있으면 헷갈립니다.
  if (!hasIntro) fs.rmSync(introPng, { force: true });
  if (!hasOutro) fs.rmSync(outroPng, { force: true });

  // ── 2) ffmpeg 그래프 조립 ─────────────────────────────────
  // 카드를 빼면 입력 번호가 밀리므로 번호를 만들면서 기억해 둡니다.
  const inputs = ["-i", video];
  let nextIndex = 1;

  let introIndex = null;
  if (hasIntro) {
    inputs.push("-loop", "1", "-t", String(q(introSeconds)), "-i", introPng);
    introIndex = nextIndex++;
  }
  let outroIndex = null;
  if (hasOutro) {
    inputs.push("-loop", "1", "-t", String(q(outroSeconds)), "-i", outroPng);
    outroIndex = nextIndex++;
  }

  const captionBase = nextIndex;
  captions.forEach((c) => { inputs.push("-i", c.file); nextIndex++; });

  const audioIndex = nextIndex;
  const bgmFile = bgm ? path.resolve(bgm) : "";
  const hasBgm = Boolean(bgmFile && fs.existsSync(bgmFile));
  if (hasBgm) inputs.push("-stream_loop", "-1", "-i", bgmFile);
  else inputs.push("-f", "lavfi", "-t", String(q(total)), "-i", "anullsrc=channel_layout=stereo:sample_rate=44100");

  const chain = [];
  chain.push(
    `[0:v]trim=0:${q(rawLimit)},setpts=(PTS-STARTPTS)/${q(factor)},` +
    `scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H},fps=${FPS},format=rgba[b0]`
  );
  let last = "b0";
  captions.forEach((c, i) => {
    const next = `b${i + 1}`;
    chain.push(`[${last}][${captionBase + i}:v]overlay=0:0:enable='between(t,${c.start},${c.end})'[${next}]`);
    last = next;
  });

  const segments = [];
  if (hasIntro) {
    chain.push(`[${introIndex}:v]scale=${W}:${H},fps=${FPS},format=rgba,fade=t=out:st=${q(Math.max(0, introSeconds - 0.3))}:d=0.3[intro]`);
    segments.push("[intro]");
  }
  segments.push(`[${last}]`);
  if (hasOutro) {
    chain.push(`[${outroIndex}:v]scale=${W}:${H},fps=${FPS},format=rgba,fade=t=in:st=0:d=0.3[outro]`);
    segments.push("[outro]");
  }

  if (segments.length > 1) {
    chain.push(`${segments.join("")}concat=n=${segments.length}:v=1:a=0,format=yuv420p[v]`);
  } else {
    // 카드가 하나도 없으면 본편만 그대로 씁니다 (concat=n=1 은 쓰지 않습니다).
    chain.push(`[${last}]format=yuv420p[v]`);
  }

  chain.push(
    hasBgm
      ? `[${audioIndex}:a]atrim=0:${q(total)},asetpts=N/SR/TB,volume=0.22,afade=t=out:st=${q(Math.max(0, total - 1.2))}:d=1.2[a]`
      : `[${audioIndex}:a]anull[a]`
  );

  await ff.run([
    ...inputs,
    "-filter_complex", chain.join(";"),
    "-map", "[v]", "-map", "[a]",
    "-c:v", "libx264", "-preset", "medium", "-crf", "20",
    "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1", "-r", String(FPS),
    "-c:a", "aac", "-b:a", "128k",
    "-movflags", "+faststart",
    "-t", String(q(total)),
    outMp4,
  ]);

  // 표지 이미지: 인트로 카드가 있으면 그걸 쓰고, 없으면 본편 첫 장면에서 뽑습니다.
  if (hasIntro) fs.copyFileSync(introPng, outCover);
  else await ff.run(["-ss", "0.5", "-i", outMp4, "-frames:v", "1", outCover]);

  log.ok(`숏츠 mp4 → ${path.relative(process.cwd(), outMp4)}`);

  // ── 3) GIF (인트로 다음 구간만) ───────────────────────────
  const gif = render.gif;
  await ff.run([
    "-ss", String(q(introSeconds)), "-t", String(q(Math.min(gif.maxDuration, bodyDuration))),
    "-i", outMp4,
    "-vf", `fps=${gif.fps},scale=${gif.width}:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=3`,
    "-loop", "0",
    outGif,
  ]);
  log.ok(`GIF → ${path.relative(process.cwd(), outGif)}`);

  return { mp4: outMp4, gif: outGif, cover: outCover, duration: total };
}
