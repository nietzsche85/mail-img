import fs from "node:fs";
import path from "node:path";
import { composeText, LABELS, LIMITS } from "../compose.js";

const ASSET_LABELS = { video: "동영상", image: "이미지", gif: "GIF" };

/**
 * 어떤 자격 증명도 필요 없는 기본 대상.
 * 채널 API 없이 손으로 올릴 때는 이 .txt 가 유일한 작업 지시서라,
 * 붙여넣을 본문뿐 아니라 글자 수와 첨부할 파일 경로까지 같이 적어 둡니다.
 */
export const file = {
  name: "file",
  configured: () => true,
  async send({ post, assets, paths }) {
    const base = path.join(paths.queue, `${post.platform}-v${post.variant}`);
    const limit = LIMITS[post.platform] ?? 0;
    const text = composeText(post, { limit });

    const header = `── ${LABELS[post.platform] ?? post.platform} · 시안 ${post.variant} `;
    const lines = [
      header + "─".repeat(Math.max(0, 52 - header.length)),
      `글자수 ${text.length}${limit ? ` / ${limit}` : ""}`,
      "",
    ];
    if (post.title) lines.push(`[제목] ${post.title}`, "");
    lines.push(text);
    if (post.firstComment) lines.push("", `[첫 댓글] ${post.firstComment}`);

    const attachments = Object.entries(assets)
      .filter(([, value]) => value && fs.existsSync(value))
      .map(([kind, value]) => [ASSET_LABELS[kind] ?? kind, value]);
    if (attachments.length) {
      const width = Math.max(...attachments.map(([label]) => label.length));
      lines.push("", "[첨부]", ...attachments.map(([label, value]) => `  ${label.padEnd(width)}  ${value}`));
    }

    fs.writeFileSync(`${base}.txt`, lines.join("\n") + "\n");
    fs.writeFileSync(`${base}.json`, JSON.stringify({ post, text, assets }, null, 2));
    return { ok: true, target: "file", output: `${base}.txt` };
  },
};
