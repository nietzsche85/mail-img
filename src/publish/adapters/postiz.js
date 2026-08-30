import fs from "node:fs";
import path from "node:path";
import { composeText, LIMITS } from "../compose.js";

/**
 * Postiz — 한 번 연결해두면 X/스레드/인스타/유튜브/틱톡/링크드인 등 28개 채널에
 * 같은 API 로 예약·발행할 수 있습니다. 채널별 토큰을 직접 관리하지 않아도 되는 게 장점.
 *
 * 필요한 값
 *   POSTIZ_API_URL       기본 https://api.postiz.com (셀프호스팅이면 그 주소)
 *   POSTIZ_API_KEY       설정 > Public API 에서 발급
 *   POSTIZ_INTEGRATIONS  {"instagram":"<integration id>","x":"<id>"} 형태의 JSON
 */
const api = () => (process.env.POSTIZ_API_URL || "https://api.postiz.com").replace(/\/$/, "");
const headers = () => ({ Authorization: process.env.POSTIZ_API_KEY });

async function uploadMedia(filePath) {
  const form = new FormData();
  const buf = fs.readFileSync(filePath);
  form.append("file", new Blob([buf]), path.basename(filePath));
  const res = await fetch(`${api()}/public/v1/upload`, { method: "POST", headers: headers(), body: form });
  if (!res.ok) throw new Error(`postiz upload ${res.status}: ${(await res.text()).slice(0, 200)}`);
  return res.json();
}

export const postiz = {
  name: "postiz",
  configured: () => Boolean(process.env.POSTIZ_API_KEY),
  async send({ post, assets, scheduleAt }) {
    const map = JSON.parse(process.env.POSTIZ_INTEGRATIONS || "{}");
    const integrationId = map[post.platform];
    if (!integrationId) {
      throw new Error(`POSTIZ_INTEGRATIONS 에 "${post.platform}" 채널 id 가 없습니다.`);
    }

    const mediaFile = assets.video ?? assets.image;
    const uploaded = mediaFile && fs.existsSync(mediaFile) ? await uploadMedia(mediaFile) : null;

    const body = {
      type: scheduleAt ? "schedule" : "now",
      date: scheduleAt || new Date().toISOString(),
      shortLink: false,
      posts: [{
        integration: { id: integrationId },
        value: [{
          content: composeText(post, { limit: LIMITS[post.platform] ?? 0 }),
          ...(uploaded ? { image: [{ id: uploaded.id, path: uploaded.path }] } : {}),
        }],
        settings: post.title ? { title: post.title } : {},
      }],
    };

    const res = await fetch(`${api()}/public/v1/posts`, {
      method: "POST",
      headers: { ...headers(), "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`postiz posts ${res.status}: ${(await res.text()).slice(0, 300)}`);
    return { ok: true, target: "postiz", response: await res.json().catch(() => ({})) };
  },
};
