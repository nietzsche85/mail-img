import fs from "node:fs";
import crypto from "node:crypto";
import { composeText, LIMITS } from "../compose.js";

/**
 * X(트위터) — OAuth 1.0a User Context.
 * 필요한 값: X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_SECRET
 * (개발자 포털에서 앱 권한을 Read and Write 로 올려두어야 합니다.)
 */
const UPLOAD_HOST = process.env.X_UPLOAD_HOST || "https://upload.twitter.com/1.1/media/upload.json";
const API_HOST = process.env.X_API_HOST || "https://api.x.com";

const enc = (s) => encodeURIComponent(String(s)).replace(/[!*'()]/g, (c) => "%" + c.charCodeAt(0).toString(16).toUpperCase());

/** 쿼리스트링 파라미터까지 포함해 OAuth 1.0a 서명을 만듭니다. multipart/JSON 바디는 서명 대상이 아닙니다. */
function authHeader(method, urlString) {
  const url = new URL(urlString);
  const oauth = {
    oauth_consumer_key: process.env.X_API_KEY,
    oauth_nonce: crypto.randomBytes(16).toString("hex"),
    oauth_signature_method: "HMAC-SHA1",
    oauth_timestamp: Math.floor(Date.now() / 1000).toString(),
    oauth_token: process.env.X_ACCESS_TOKEN,
    oauth_version: "1.0",
  };
  const all = { ...oauth };
  for (const [k, v] of url.searchParams) all[k] = v;

  const paramString = Object.keys(all).sort().map((k) => `${enc(k)}=${enc(all[k])}`).join("&");
  const baseUrl = `${url.origin}${url.pathname}`;
  const base = `${method.toUpperCase()}&${enc(baseUrl)}&${enc(paramString)}`;
  const key = `${enc(process.env.X_API_SECRET)}&${enc(process.env.X_ACCESS_SECRET)}`;
  oauth.oauth_signature = crypto.createHmac("sha1", key).update(base).digest("base64");

  return "OAuth " + Object.keys(oauth).sort().map((k) => `${enc(k)}="${enc(oauth[k])}"`).join(", ");
}

async function call(method, url, { body, json } = {}) {
  const headers = { Authorization: authHeader(method, url) };
  if (json) headers["content-type"] = "application/json";
  const res = await fetch(url, { method, headers, body: json ? JSON.stringify(json) : body });
  const text = await res.text();
  if (!res.ok) throw new Error(`X ${method} ${new URL(url).pathname} ${res.status}: ${text.slice(0, 300)}`);
  return text ? JSON.parse(text) : {};
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** 동영상은 INIT → APPEND(5MB 청크) → FINALIZE → STATUS 폴링 순서입니다. */
async function uploadVideo(filePath) {
  const buf = fs.readFileSync(filePath);
  const init = await call("POST", `${UPLOAD_HOST}?command=INIT&total_bytes=${buf.length}&media_type=video%2Fmp4&media_category=tweet_video`);
  const mediaId = init.media_id_string;

  const CHUNK = 5 * 1024 * 1024;
  for (let i = 0, offset = 0; offset < buf.length; i++, offset += CHUNK) {
    const form = new FormData();
    form.append("media", new Blob([buf.subarray(offset, Math.min(buf.length, offset + CHUNK))]), "chunk");
    await call("POST", `${UPLOAD_HOST}?command=APPEND&media_id=${mediaId}&segment_index=${i}`, { body: form });
  }
  await call("POST", `${UPLOAD_HOST}?command=FINALIZE&media_id=${mediaId}`);

  for (let i = 0; i < 40; i++) {
    const status = await call("GET", `${UPLOAD_HOST}?command=STATUS&media_id=${mediaId}`);
    const info = status.processing_info;
    if (!info || info.state === "succeeded") return mediaId;
    if (info.state === "failed") throw new Error(`X 동영상 처리 실패: ${JSON.stringify(info.error ?? {})}`);
    await sleep((info.check_after_secs ?? 3) * 1000);
  }
  throw new Error("X 동영상 처리 시간 초과");
}

async function uploadImage(filePath) {
  const form = new FormData();
  form.append("media", new Blob([fs.readFileSync(filePath)]), "image.png");
  const res = await call("POST", UPLOAD_HOST, { body: form });
  return res.media_id_string;
}

export const x = {
  name: "x",
  configured: () => ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"].every((k) => process.env[k]),
  async send({ post, assets }) {
    let mediaId = null;
    if (assets.video && fs.existsSync(assets.video)) mediaId = await uploadVideo(assets.video);
    else if (assets.image && fs.existsSync(assets.image)) mediaId = await uploadImage(assets.image);

    const payload = { text: composeText(post, { limit: LIMITS.x }) };
    if (mediaId) payload.media = { media_ids: [mediaId] };
    const tweet = await call("POST", `${API_HOST}/2/tweets`, { json: payload });

    if (post.firstComment) {
      await call("POST", `${API_HOST}/2/tweets`, {
        json: { text: post.firstComment.slice(0, LIMITS.x), reply: { in_reply_to_tweet_id: tweet.data.id } },
      });
    }
    return { ok: true, target: "x", id: tweet.data?.id, url: `https://x.com/i/status/${tweet.data?.id}` };
  },
};
