import fs from "node:fs";
import { composeText, LIMITS } from "../compose.js";

/**
 * YouTube Shorts — refresh token 으로 access token 을 받아 resumable 업로드.
 * 필요한 값: YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN
 * (세로 영상 + 3분 이하 + 제목이나 설명에 #Shorts 가 있으면 쇼츠로 잡힙니다.)
 */
async function accessToken() {
  const res = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: process.env.YT_CLIENT_ID,
      client_secret: process.env.YT_CLIENT_SECRET,
      refresh_token: process.env.YT_REFRESH_TOKEN,
      grant_type: "refresh_token",
    }),
  });
  const json = await res.json();
  if (!res.ok) throw new Error(`YouTube 토큰 발급 실패: ${JSON.stringify(json).slice(0, 200)}`);
  return json.access_token;
}

export const youtube = {
  name: "youtube",
  configured: () => ["YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"].every((k) => process.env[k]),
  async send({ post, assets }) {
    if (!assets.video || !fs.existsSync(assets.video)) throw new Error("유튜브에 올릴 동영상이 없습니다.");
    const token = await accessToken();

    const tags = (post.hashtags ?? []).map((t) => t.replace(/^#/, ""));
    const description = composeText(post, { limit: LIMITS.youtube });
    const metadata = {
      snippet: {
        title: (post.title || post.text.split("\n")[0]).slice(0, 95),
        description: description.includes("#Shorts") ? description : `${description}\n\n#Shorts`,
        tags: tags.slice(0, 15),
        categoryId: "19",             // Travel & Events
      },
      status: { privacyStatus: process.env.YT_PRIVACY || "public", selfDeclaredMadeForKids: false },
    };

    const body = fs.readFileSync(assets.video);
    const start = await fetch(
      "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "content-type": "application/json",
          "X-Upload-Content-Length": String(body.length),
          "X-Upload-Content-Type": "video/mp4",
        },
        body: JSON.stringify(metadata),
      }
    );
    if (!start.ok) throw new Error(`YouTube 업로드 세션 실패 ${start.status}: ${(await start.text()).slice(0, 300)}`);
    const uploadUrl = start.headers.get("location");

    const done = await fetch(uploadUrl, {
      method: "PUT",
      headers: { "content-type": "video/mp4", "content-length": String(body.length) },
      body,
    });
    const json = await done.json();
    if (!done.ok) throw new Error(`YouTube 업로드 실패 ${done.status}: ${JSON.stringify(json).slice(0, 300)}`);
    return { ok: true, target: "youtube", id: json.id, url: `https://youtube.com/shorts/${json.id}` };
  },
};
