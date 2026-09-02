import { composeText, LIMITS, publicUrl } from "../compose.js";

/**
 * Threads (Meta) — 컨테이너 생성 후 publish 하는 2단계 방식.
 * 필요한 값: THREADS_USER_ID / THREADS_ACCESS_TOKEN
 * 미디어는 "공개 URL" 이어야 해서 PUBLIC_MEDIA_BASE_URL 이 필요합니다.
 */
const BASE = "https://graph.threads.net/v1.0";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function post(url, params) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams(params),
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`Threads ${res.status}: ${text.slice(0, 300)}`);
  return JSON.parse(text);
}

export const threads = {
  name: "threads",
  configured: () => Boolean(process.env.THREADS_USER_ID && process.env.THREADS_ACCESS_TOKEN),
  async send({ post: item, assets }) {
    const uid = process.env.THREADS_USER_ID;
    const token = process.env.THREADS_ACCESS_TOKEN;
    const text = composeText(item, { limit: LIMITS.threads });

    const videoUrl = assets.video ? publicUrl(assets.video) : null;
    const imageUrl = assets.image ? publicUrl(assets.image) : null;

    const params = { access_token: token, text };
    if (videoUrl) { params.media_type = "VIDEO"; params.video_url = videoUrl; }
    else if (imageUrl) { params.media_type = "IMAGE"; params.image_url = imageUrl; }
    else params.media_type = "TEXT";

    const container = await post(`${BASE}/${uid}/threads`, params);
    if (params.media_type !== "TEXT") await sleep(20_000);   // 미디어 처리 대기

    const published = await post(`${BASE}/${uid}/threads_publish`, {
      access_token: token,
      creation_id: container.id,
    });
    return { ok: true, target: "threads", id: published.id };
  },
};
