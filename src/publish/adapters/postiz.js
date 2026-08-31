import fs from "node:fs";
import path from "node:path";
import { composeText, LIMITS } from "../compose.js";

/**
 * Postiz — 한 번 연결해두면 X/인스타/스레드/유튜브 등 여러 채널에 같은 API 로 발행합니다.
 *
 * 필요한 값 (.env)
 *   POSTIZ_API_KEY       Postiz 설정 > Public API 에서 발급한 키.
 *                        ※ 채널 연결용 CLIENT_ID / CLIENT_SECRET 과는 다른 값입니다.
 *                           그건 셀프호스팅 Postiz 서버의 환경변수로 들어갑니다.
 *   POSTIZ_API_URL       기본 https://api.postiz.com (셀프호스팅이면 그 주소)
 *   POSTIZ_INTEGRATIONS  (선택) {"instagram":"<채널 id>"} 형태의 JSON.
 *                        비워두면 연결된 채널 목록에서 자동으로 찾습니다.
 *
 * Public API 는 시간당 30요청 제한이 있습니다 (발행 1건당 업로드 포함 2요청).
 */

/** 우리 플랫폼 키 → Postiz 의 provider identifier 후보들 (자동 매칭용). */
export const PROVIDER_ALIASES = {
  x: ["x", "twitter"],
  instagram: ["instagram", "instagram-standalone"],
  threads: ["threads"],
  youtube: ["youtube"],
  tiktok: ["tiktok"],
  linkedin: ["linkedin", "linkedin-page"],
  facebook: ["facebook"],
};

const api = () => (process.env.POSTIZ_API_URL || "https://api.postiz.com").replace(/\/$/, "");
const headers = () => ({ Authorization: process.env.POSTIZ_API_KEY });

let cache = null;

/** 연결된 채널 목록. id, name, identifier(provider), disabled 등이 들어옵니다. */
export async function integrations({ refresh = false } = {}) {
  if (cache && !refresh) return cache;
  const res = await fetch(`${api()}/public/v1/integrations`, { headers: headers() });
  if (!res.ok) throw new Error(`postiz 채널 목록 조회 실패 ${res.status}: ${(await res.text()).slice(0, 200)}`);
  const payload = await res.json();
  cache = Array.isArray(payload) ? payload : payload.integrations ?? [];
  return cache;
}

/** 플랫폼 이름 → { id, provider } */
async function resolve(platform) {
  const channels = await integrations();
  const mapping = JSON.parse(process.env.POSTIZ_INTEGRATIONS || "{}");

  if (mapping[platform]) {
    const found = channels.find((c) => c.id === mapping[platform]);
    // 목록에 없어도 사용자가 지정한 id 는 존중합니다 (권한 문제로 안 보일 수 있음).
    return { id: mapping[platform], provider: found?.identifier ?? platform };
  }

  const aliases = PROVIDER_ALIASES[platform] ?? [platform];
  const found = channels.find((c) => aliases.includes(c.identifier) && !c.disabled);
  if (!found) {
    const connected = channels.map((c) => `${c.identifier}(${c.name})`).join(", ") || "없음";
    throw new Error(
      `Postiz 에 '${platform}' 채널이 연결돼 있지 않습니다.\n` +
      `  연결된 채널: ${connected}\n` +
      "  node src/cli.js channels 로 확인하거나 Postiz 에서 채널을 먼저 연결하세요."
    );
  }
  return { id: found.id, provider: found.identifier };
}

async function uploadMedia(filePath) {
  const form = new FormData();
  form.append("file", new Blob([fs.readFileSync(filePath)]), path.basename(filePath));
  const res = await fetch(`${api()}/public/v1/upload`, { method: "POST", headers: headers(), body: form });
  if (!res.ok) throw new Error(`postiz 업로드 실패 ${res.status}: ${(await res.text()).slice(0, 200)}`);
  return res.json();
}

export const postiz = {
  name: "postiz",
  configured: () => Boolean(process.env.POSTIZ_API_KEY),
  async send({ post, assets, scheduleAt }) {
    const { id: integrationId, provider } = await resolve(post.platform);

    const mediaFile = assets.video ?? assets.image;
    const uploaded = mediaFile && fs.existsSync(mediaFile) ? await uploadMedia(mediaFile) : null;

    const value = { content: composeText(post, { limit: LIMITS[post.platform] ?? 0 }) };
    if (uploaded) value.image = [{ id: uploaded.id, path: uploaded.path }];

    // __type 이 없으면 일부 채널(인스타그램 등)에서 400 이 납니다.
    const settings = { __type: provider };
    if (post.title) settings.title = post.title;

    const body = {
      type: scheduleAt ? "schedule" : "now",
      date: scheduleAt || new Date().toISOString(),
      shortLink: false,
      posts: [{ integration: { id: integrationId }, value: [value], settings }],
    };

    const res = await fetch(`${api()}/public/v1/posts`, {
      method: "POST",
      headers: { ...headers(), "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`postiz 발행 실패 ${res.status}: ${(await res.text()).slice(0, 300)}`);
    return { ok: true, target: "postiz", provider, response: await res.json().catch(() => ({})) };
  },
};
