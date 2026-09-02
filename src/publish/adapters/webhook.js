import { composeText, LIMITS } from "../compose.js";

/** n8n / Make / Zapier / Slack 등으로 통째로 넘깁니다. */
export const webhook = {
  name: "webhook",
  configured: () => Boolean(process.env.WEBHOOK_URL),
  async send({ post, assets, runId }) {
    const body = {
      runId,
      platform: post.platform,
      variant: post.variant,
      title: post.title || undefined,
      text: composeText(post, { limit: LIMITS[post.platform] ?? 0 }),
      hashtags: post.hashtags,
      firstComment: post.firstComment || undefined,
      assets,
    };
    const res = await fetch(process.env.WEBHOOK_URL, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`webhook ${res.status}: ${(await res.text()).slice(0, 200)}`);
    return { ok: true, target: "webhook", status: res.status };
  },
};
