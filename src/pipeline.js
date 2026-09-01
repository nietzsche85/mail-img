import fs from "node:fs";
import path from "node:path";
import { log } from "./lib/log.js";
import { loadConfig, loadYaml } from "./lib/config.js";
import { runPaths, newRunId, readJson, writeJson, outDir } from "./lib/paths.js";
import { capture } from "./capture/record.js";
import { renderShorts } from "./render/shorts.js";
import { collectArticles } from "./analyze/blog.js";
import { generateCopy } from "./generate/copy.js";
import { generateImages } from "./generate/image.js";
import { publish } from "./publish/index.js";

/** 단계별로 따로 실행해도 이어지도록, 실행 폴더에 진행 상황을 남깁니다. */
const manifestFile = (paths) => path.join(paths.base, "manifest.json");
const readManifest = (paths) => readJson(manifestFile(paths), {});
const saveManifest = (paths, patch) => writeJson(manifestFile(paths), { ...readManifest(paths), ...patch });

export function openRun(opts = {}) {
  const config = loadConfig(opts.config ?? "config/pipeline.yaml");
  // 이어받을 실행이 없으면 새로 만듭니다 (처음 쓰는 사람이 막히지 않게).
  const runId = opts.run ?? (opts.latest ? latestRun() ?? newRunId() : newRunId());
  return { config, paths: runPaths(runId), runId };
}

export function latestRun() {
  if (!fs.existsSync(outDir)) return null;
  const runs = fs.readdirSync(outDir).filter((d) => /^\d{8}-\d{6}$/.test(d)).sort();
  return runs.at(-1) ?? null;
}

// ── 개별 단계 ──────────────────────────────────────────────

export async function stepCapture({ config, paths }, opts = {}) {
  const flowFile = opts.flow ?? config.capture.flow;
  const flow = loadYaml(flowFile);
  if (opts.url) flow.url = opts.url;
  const result = await capture(flow, paths, { headless: !opts.headed });
  saveManifest(paths, { flow: flowFile, video: result.video, timeline: result.timeline, shots: result.shots });
  return result;
}

export async function stepAnalyze({ config, paths }, opts = {}) {
  const blog = { ...config.blog };
  if (opts.url) { blog.urls = [opts.url]; blog.feed = ""; }
  if (opts.feed) blog.feed = opts.feed;
  const { articles, commit } = await collectArticles(blog);
  saveManifest(paths, { articles });
  return { articles, commit };
}

export async function stepCopy({ config, paths }, opts = {}) {
  const m = readManifest(paths);
  const article = m.articles?.[opts.articleIndex ?? 0] ?? null;
  if (!article && !m.timeline) throw new Error("분석한 블로그 글도, 녹화본도 없습니다. analyze 또는 capture 를 먼저 실행하세요.");
  const copy = await generateCopy({ article, timeline: m.timeline, brand: config.brand, copy: config.copy, paths });
  saveManifest(paths, { copy });
  return copy;
}

/** 설정의 앞/뒤 카드 값에 옵션으로 들어온 값을 덮어씁니다. */
function cardOptions(opts, configBlock, prefix) {
  const block = { ...(configBlock ?? {}) };
  for (const key of ["text", "image", "seconds"]) {
    const value = opts?.[`${prefix}_${key}`];
    if (value !== undefined && value !== "") block[key] = value;
  }
  return block;
}

export async function stepRender({ config, paths }, opts = {}) {
  const m = readManifest(paths);
  if (!m.video || !fs.existsSync(m.video)) throw new Error("녹화본이 없습니다. 먼저 capture 를 실행하세요.");
  const shorts = config.render.shorts;
  const media = await renderShorts({
    video: m.video,
    timeline: m.timeline ?? { captions: [], duration: 0 },
    brand: config.brand,
    render: config.render,
    paths,
    // 앞뒤 카드는 직접 넣은 문구나 이미지가 있을 때만 붙습니다.
    intro: cardOptions(opts, shorts.intro, "intro"),
    outro: cardOptions(opts, shorts.outro, "outro"),
  });
  saveManifest(paths, { media: { ...(m.media ?? {}), ...media } });
  return media;
}

export async function stepImage({ config, paths }) {
  const m = readManifest(paths);
  if (!m.copy) throw new Error("카피가 없습니다. 먼저 copy 를 실행하세요.");
  const files = await generateImages({
    copy: m.copy,
    brand: config.brand,
    image: config.image,
    article: m.articles?.[0] ?? null,
    fallbackImage: m.shots?.[0] ?? null,
    paths,
  });
  const images = Object.fromEntries(config.image.sizes.map((s, i) => [s.name, files[i]]));
  saveManifest(paths, { media: { ...(m.media ?? {}), images } });
  return images;
}

export async function stepPublish({ config, paths, runId }, opts = {}) {
  const m = readManifest(paths);
  if (!m.copy) throw new Error("카피가 없습니다. 먼저 copy 를 실행하세요.");
  if (opts.targets?.length) config.publish.targets = opts.targets;
  return publish({
    copy: m.copy,
    media: m.media ?? {},
    config,
    paths,
    runId,
    dryRun: !opts.publish,
    variant: opts.variant ?? 1,
  });
}

// ── 전체 파이프라인 ────────────────────────────────────────

export async function runAll(opts = {}) {
  const ctx = openRun(opts);
  log.step(`실행 ${ctx.runId} 시작 · 결과는 out/${ctx.runId}/ 에 쌓입니다`);

  let commit = () => {};
  if (!opts.skipAnalyze && (ctx.config.blog.feed || ctx.config.blog.urls?.length || opts.url || opts.feed)) {
    ({ commit } = await stepAnalyze(ctx, opts));
  }

  const hasFlow = !opts.skipCapture && fs.existsSync(path.isAbsolute(ctx.config.capture.flow)
    ? ctx.config.capture.flow
    : path.join(process.cwd(), ctx.config.capture.flow));
  if (hasFlow) {
    try {
      await stepCapture(ctx, opts);
    } catch (e) {
      log.error(`녹화 실패 — 영상 없이 이미지/카피만 진행합니다.\n  ${e.message}`);
    }
  }

  await stepCopy(ctx, opts);

  const m = readManifest(ctx.paths);
  if (m.video) {
    try { await stepRender(ctx); }
    catch (e) { log.error(`렌더 실패 — 이미지로만 진행합니다.\n  ${e.message}`); }
  }

  await stepImage(ctx);
  const results = await stepPublish(ctx, opts);

  if (opts.publish && results.some((r) => r.ok)) commit();

  log.ok(`완료 · out/${ctx.runId}/`);
  return { runId: ctx.runId, results };
}
