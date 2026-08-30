import fs from "node:fs";
import path from "node:path";
import { composeText, LIMITS } from "../compose.js";

/** 어떤 자격 증명도 필요 없는 기본 대상. 발행 직전 상태 그대로 파일로 떨궈줍니다. */
export const file = {
  name: "file",
  configured: () => true,
  async send({ post, assets, paths }) {
    const base = path.join(paths.queue, `${post.platform}-v${post.variant}`);
    const text = composeText(post, { limit: LIMITS[post.platform] ?? 0 });
    fs.writeFileSync(`${base}.txt`, [post.title ? `[제목] ${post.title}` : "", text, post.firstComment ? `\n[첫 댓글] ${post.firstComment}` : ""].filter(Boolean).join("\n"));
    fs.writeFileSync(`${base}.json`, JSON.stringify({ post, text, assets }, null, 2));
    return { ok: true, target: "file", output: `${base}.txt` };
  },
};
