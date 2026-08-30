import path from "node:path";
import Anthropic from "@anthropic-ai/sdk";
import { zodOutputFormat } from "@anthropic-ai/sdk/helpers/zod";
import { z } from "zod";
import { log } from "../lib/log.js";
import { writeJson } from "../lib/paths.js";
import { systemPrompt, userPrompt } from "./prompts.js";

const PostSchema = z.object({
  platform: z.string(),
  variant: z.number(),
  title: z.string().describe("유튜브/블로그처럼 제목이 따로 있는 플랫폼만. 없으면 빈 문자열."),
  text: z.string(),
  hashtags: z.array(z.string()),
  firstComment: z.string().describe("첫 댓글에 넣을 링크/부연. 없으면 빈 문자열."),
});

const CopySchema = z.object({
  angle: z.string().describe("이번 콘텐츠를 관통하는 한 줄 각도"),
  hook: z.string().describe("영상 첫 화면에 띄울 훅. 18자 이내"),
  hookSub: z.string().describe("훅 아래 보조 문구. 24자 이내"),
  cta: z.string().describe("영상 마지막 화면 CTA. 16자 이내"),
  captions: z.array(z.string()).describe("영상 자막으로 쓸 짧은 문장들. 각 20자 이내"),
  card: z.object({
    badge: z.string(),
    title: z.string(),
    subtitle: z.string(),
    bullets: z.array(z.string()),
  }),
  hashtags: z.array(z.string()).describe("공통 해시태그 풀. # 포함"),
  posts: z.array(PostSchema),
  risky_claims: z.array(z.string()).describe("과장광고로 읽힐 수 있어 사람이 확인해야 하는 문장"),
});

/** 녹화 타임라인을 카피 생성용 텍스트로 요약합니다. */
export function screenSummary(timeline) {
  if (!timeline?.events?.length) return "";
  const lines = timeline.events.map((e) => {
    const s = e.step ?? {};
    if (s.caption) return `- ${s.caption}`;
    if (s.click) return `- 클릭: ${JSON.stringify(s.click)}`;
    if (s.fill) return `- 입력: ${s.fill.value}`;
    if (s.scroll) return "- 결과 목록 스크롤";
    return null;
  }).filter(Boolean);
  return [`화면 시나리오: ${timeline.name}`, ...lines].join("\n");
}

export async function generateCopy({ article, timeline, brand, copy: cfg, paths }) {
  if (!process.env.ANTHROPIC_API_KEY && !process.env.ANTHROPIC_AUTH_TOKEN) {
    throw new Error("ANTHROPIC_API_KEY 가 없습니다. .env 에 넣어주세요.");
  }
  const client = new Anthropic();

  log.step(`카피 생성 (${cfg.model}, ${cfg.platforms.join(", ")})`);

  // messages.parse() 를 쓰면 응답 검증에 실패했을 때 SDK 가 먼저 예외를 던져서
  // 아래 거절/파싱 검사까지 오지 못합니다. 그래서 create() 로 원본 응답을 받고
  // 스키마 검증은 직접 합니다 (zodOutputFormat 은 공개 헬퍼라 그대로 씁니다).
  const response = await client.messages.create({
    model: cfg.model,
    max_tokens: 16000,
    thinking: { type: "adaptive" },
    system: systemPrompt(brand),
    messages: [{
      role: "user",
      content: userPrompt({
        article,
        screenText: screenSummary(timeline),
        platforms: cfg.platforms,
        variants: cfg.variants,
        language: cfg.language,
      }),
    }],
    output_config: {
      effort: cfg.effort ?? "high",
      format: zodOutputFormat(CopySchema),
    },
  });

  if (response.stop_reason === "refusal") {
    throw new Error(`모델이 요청을 거절했습니다 (${response.stop_details?.category ?? "unknown"}). 소재를 확인해주세요.`);
  }

  const raw = response.content.find((block) => block.type === "text")?.text ?? "";
  let result;
  try {
    result = CopySchema.parse(JSON.parse(raw));
  } catch (e) {
    const reason = raw.trim()
      ? `모델이 형식에 맞지 않는 응답을 돌려줬습니다: ${raw.slice(0, 120)}…`
      : "모델이 빈 응답을 돌려줬습니다. 요청을 거절했거나 응답이 잘렸을 수 있습니다.";
    throw new Error(`카피 생성 실패 — ${reason}\n  소재를 바꾸거나 copy.platforms / copy.variants 를 줄여서 다시 시도해보세요.`);
  }

  // 브랜드 금칙어는 코드로 한 번 더 거릅니다 (모델 실수 방지).
  const banned = brand.banned ?? [];
  const flagged = [];
  for (const post of result.posts) {
    for (const word of banned) {
      if (post.text.includes(word) || (post.title ?? "").includes(word)) {
        flagged.push(`${post.platform} #${post.variant}: "${word}"`);
      }
    }
  }
  if (flagged.length) {
    log.warn(`금칙어 발견 — 발행 전 확인 필요:\n  ${flagged.join("\n  ")}`);
    result.risky_claims = [...(result.risky_claims ?? []), ...flagged];
  }
  if (result.risky_claims?.length) {
    log.warn(`사람 확인 권장 문구 ${result.risky_claims.length}건 (copy/copy.json 의 risky_claims 참고)`);
  }

  const file = writeJson(path.join(paths.copy, "copy.json"), {
    source: article ? { url: article.url, title: article.title } : null,
    model: cfg.model,
    generatedAt: new Date().toISOString(),
    usage: response.usage,
    ...result,
  });
  log.ok(`카피 ${result.posts.length}개 → ${path.relative(process.cwd(), file)}`);
  return result;
}
