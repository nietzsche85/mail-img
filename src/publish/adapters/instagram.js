import { composeText, LIMITS, publicUrl } from "../compose.js";

/**
 * Instagram — 릴스(동영상) 또는 피드 이미지.
 * 필요한 값: IG_USER_ID / IG_ACCESS_TOKEN (프로페셔널 계정 + 페이지 연결 필요)
 * 미디어는 공개 URL 이어야 하므로 PUBLIC_MEDIA_BASE_URL 을 반드시 설정하세요.
 */
const BASE = "https://graph.facebook.com/v21.0";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function call(method, url, params) {
  const res = await fetch(url, {
    method,
    headers: method === "POST" ? { "content-type": "application/x-www-form-urlencoded" } : undefined,
    body: method === "POST" ? new URLSearchParams(params) : undefined,
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`Instagram ${res.status}: ${text.slice(0, 300)}`);
  return JSON.parse(text);
}

export const instagram = {
  name: "instagram",
  configured: () => Boolean(process.env.IG_USER_ID && process.env.IG_ACCESS_TOKEN),
  async send({ post, assets }) {
    const uid = process.env.IG_USER_ID;
    const token = process.env.IG_ACCESS_TOKEN;
    const caption = composeText(post, { limit: LIMITS.instagram });

    const videoUrl = assets.video ? publicUrl(assets.video) : null;
    const imageUrl = assets.image ? publicUrl(assets.image) : null;
    if (!videoUrl && !imageUrl) {
      throw new Error("인스타그램은 공개 URL 이 필요합니다. PUBLIC_MEDIA_BASE_URL 을 설정하세요.");
    }

    const params = { access_token: token, caption };
    if (videoUrl) { params.media_type = "REELS"; params.video_url = videoUrl; params.share_to_feed = "true"; }
    else params.image_url = imageUrl;

    const container = await call("POST", `${BASE}/${uid}/media`, params);

    // 동영상은 서버에서 인코딩이 끝나야 발행할 수 있습니다.
    for (let i = 0; videoUrl && i < 30; i++) {
      const st = await call("GET", `${BASE}/${container.id}?fields=status_code&access_token=${token}`);
      if (st.status_code === "FINISHED") break;
      if (st.status_code === "ERROR") throw new Error("인스타그램 동영상 처리 실패");
      await sleep(10_000);
    }

    const published = await call("POST", `${BASE}/${uid}/media_publish`, {
      access_token: token,
      creation_id: container.id,
    });
    return { ok: true, target: "instagram", id: published.id };
  },
};
