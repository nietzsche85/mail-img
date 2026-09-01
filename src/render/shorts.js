import fs from "node:fs";
import path from "node:path";
import { log } from "../lib/log.js";
import * as ff from "../lib/ffmpeg.js";
import { renderAll } from "./html2png.js";
import { captionHtml, introHtml, outroHtml } from "./cards.js";

const q = (n) => Number(n.toFixed(3));

/** 앞뒤 카드에 쓸 수 있는 이미지 형식 */
const IMAGE_SUFFIXES = new Set([".png", ".jpg", ".jpeg", ".webp", ".bmp"]);

/** 설정에서 온 앞/뒤 카드 값을 다루기 쉬운 모양으로 정리합니다. */
function cardSpec(spec) {
  return {
    text: (spec?.text ?? "").trim(),
    image: (spec?.image ?? "").trim(),
    seconds: Number(spec?.seconds ?? 0),
  };
}

/**
 * 카드 하나를 준비합니다.
 * - 이미지가 지정돼 있으면 그 파일을 그대로 씁니다 (직접 만든 카드).
 * - 아니면 문구로 카드를 그립니다.
 * - 문구도 이미지도 없으면 그 카드는 붙이지 않습니다.
 */
function prepareCard(spec, kind, brand, W, H, outPng, jobs) {
  if (spec.seconds <= 0 || (!spec.text && !spec.image)) {
    fs.rmSync(outPng, { force: true });   // 껐는데 예전 실행의 카드가 남으면 헷갈립니다
    return null;
  }

  if (spec.image) {
    const source = path.resolve(spec.image);
    if (!fs.existsSync(source)) {
      log.warn(`${kind} 카드 이미지를 찾을 수 없습니다: ${source}`);
      if (!spec.text) return null;
      log.info("  문구로 카드를 만듭니다.");
    } else if (!IMAGE_SUFFIXES.has(path.extname(source).toLowerCase())) {
      log.warn(`${kind} 카드 이미지 형식을 알 수 없습니다: ${path.extname(source)}`);
      return null;
    } else {
      fs.rmSync(outPng, { force: true });
      return { path: source, seconds: spec.seconds, fromImage: true };
    }
  }

  const html = kind === "앞"
    ? introHtml({ hook: spec.text, sub: "", brand, width: W, height: H })
    : outroHtml({ cta: spec.text, brand, width: W, height: H });
  jobs.push({ html, width: W, height: H, out: outPng });
  return { path: outPng, seconds: spec.seconds, fromImage: false };
}

/**
 * 녹화본(webm) + 자막 타임라인 → 세로 숏츠 mp4 와 GIF.
 * 글자는 전부 크롬에서 PNG 로 구워 얹기 때문에 한글이 깨지지 않습니다.
 */
export async function renderShorts({ video, timeline, brand, render, paths, intro, outro }) {
  const { width: W, height: H, fps: FPS, maxDuration, bgm } = render.shorts;
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

  // ── 1) 자막과 앞뒤 카드 준비 ──────────────────────────────
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

  const jobs = [];
  const introCard = prepareCard(cardSpec(intro), "앞", brand, W, H, path.join(paths.render, "intro.png"), jobs);
  const outroCard = prepareCard(cardSpec(outro), "뒤", brand, W, H, path.join(paths.render, "outro.png"), jobs);
  jobs.push(...captions.map((c) => ({
    html: captionHtml(c.text, { width: W, height: H, brand }),
    width: W, height: H, out: c.file, transparent: true,
  })));
  await renderAll(jobs);

  const introSeconds = introCard ? introCard.seconds : 0;
  const outroSeconds = outroCard ? outroCard.seconds : 0;
  const total = introSeconds + bodyDuration + outroSeconds;
  const parts = [
    introCard ? `앞 ${introSeconds.toFixed(1)}초` : "",
    `본편 ${bodyDuration.toFixed(1)}초`,
    outroCard ? `뒤 ${outroSeconds.toFixed(1)}초` : "",
  ].filter(Boolean).join(" + ");
  log.info(`원본 ${rawDuration.toFixed(1)}초 → 배속 ${factor.toFixed(2)}x → ${parts} (총 ${total.toFixed(1)}초)`);

  // ── 2) ffmpeg 그래프 조립 ─────────────────────────────────
  // 카드를 빼면 입력 번호가 밀리므로 번호를 만들면서 기억해 둡니다.
  const inputs = ["-i", video];
  let nextIndex = 1;
  let introIndex = null;
  let outroIndex = null;
  if (introCard) {
    inputs.push("-loop", "1", "-t", String(q(introSeconds)), "-i", introCard.path);
    introIndex = nextIndex++;
  }
  if (outroCard) {
    inputs.push("-loop", "1", "-t", String(q(outroSeconds)), "-i", outroCard.path);
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

  // 직접 넣은 이미지는 비율이 제각각이라, 늘리지 말고 채운 뒤 잘라냅니다.
  const fit = `scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H}`;

  const segments = [];
  if (introCard) {
    chain.push(`[${introIndex}:v]${fit},fps=${FPS},format=rgba,fade=t=out:st=${q(Math.max(0, introSeconds - 0.3))}:d=0.3[intro]`);
    segments.push("[intro]");
  }
  segments.push(`[${last}]`);
  if (outroCard) {
    chain.push(`[${outroIndex}:v]${fit},fps=${FPS},format=rgba,fade=t=in:st=0:d=0.3[outro]`);
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
