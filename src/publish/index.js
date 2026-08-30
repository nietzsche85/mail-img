import path from "node:path";
import { log } from "../lib/log.js";
import { writeJson } from "../lib/paths.js";
import { composeText, LIMITS } from "./compose.js";
import { file } from "./adapters/file.js";
import { webhook } from "./adapters/webhook.js";
import { postiz } from "./adapters/postiz.js";
import { x } from "./adapters/x.js";
import { threads } from "./adapters/threads.js";
import { instagram } from "./adapters/instagram.js";
import { youtube } from "./adapters/youtube.js";

const ADAPTERS = { file, webhook, postiz, x, threads, instagram, youtube };

/** 채널 하나만 담당하는 어댑터는 자기 플랫폼 글만 처리합니다. */
const OWNED_PLATFORM = { x: "x", threads: "threads", instagram: "instagram", youtube: "youtube" };

/** 플랫폼별로 어떤 파일을 붙일지 정합니다. */
function assetsFor(platform, media) {
  const video = media.mp4 ?? null;
  const images = media.images ?? {};
  switch (platform) {
    case "youtube": return { video };
    case "instagram": return { video, image: images.feed ?? media.cover ?? null };
    case "threads": return { video, image: images.feed ?? null };
    case "x": return { video, image: images.og ?? images.feed ?? null };
    case "tiktok": return { video };
    case "naver_blog": return { image: images.feed ?? null, gif: media.gif ?? null };
    default: return { video, image: images.feed ?? null, gif: media.gif ?? null };
  }
}

export async function publish({ copy, media, config, paths, runId, dryRun = true, variant = 1 }) {
  const targets = config.publish.targets ?? ["file"];
  const scheduleAt = config.publish.scheduleAt || "";
  const posts = (copy.posts ?? []).filter((p) => p.variant === variant);
  if (!posts.length) {
    log.warn(`variant ${variant} 에 해당하는 글이 없습니다.`);
    return [];
  }

  const results = [];
  for (const targetName of targets) {
    const adapter = ADAPTERS[targetName];
    if (!adapter) { log.warn(`알 수 없는 발행 대상: ${targetName}`); continue; }
    if (!adapter.configured()) {
      log.warn(`${targetName}: 자격 증명이 없어 건너뜁니다 (.env 확인)`);
      continue;
    }
    for (const post of posts) {
      const owned = OWNED_PLATFORM[targetName];
      if (owned && post.platform !== owned) continue;

      const assets = assetsFor(post.platform, media);
      const label = `${targetName} ← ${post.platform} v${post.variant}`;
      if (dryRun && targetName !== "file") {
        const text = composeText(post, { limit: LIMITS[post.platform] ?? 0 });
        log.info(`[미리보기] ${label} (${text.length}자)\n${text.split("\n").slice(0, 3).join("\n")}…`);
        results.push({ target: targetName, platform: post.platform, variant: post.variant, dryRun: true });
        continue;
      }
      try {
        const res = await adapter.send({ post, assets, paths, runId, scheduleAt });
        log.ok(`${label} → ${res.url ?? res.output ?? res.id ?? "완료"}`);
        results.push({ target: targetName, platform: post.platform, variant: post.variant, ...res });
      } catch (e) {
        log.error(`${label} 실패: ${e.message}`);
        results.push({ target: targetName, platform: post.platform, variant: post.variant, ok: false, error: e.message });
      }
    }
  }

  writeJson(path.join(paths.base, "publish-report.json"), { runId, dryRun, variant, results });
  return results;
}

export { ADAPTERS };
