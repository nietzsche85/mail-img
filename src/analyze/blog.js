import * as cheerio from "cheerio";
import { log } from "../lib/log.js";
import { readJson, writeJson } from "../lib/paths.js";

const UA = "Mozilla/5.0 (compatible; SNS-Autopilot/0.1; +https://github.com/)";

async function get(url) {
  const res = await fetch(url, { headers: { "user-agent": UA, accept: "*/*" }, redirect: "follow" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${url}`);

  // res.text() 는 무조건 UTF-8 로 읽습니다. 국내 구형 블로그는 EUC-KR 이 많아서
  // 그대로 두면 한글이 전부 깨진 채로 모델에 들어갑니다.
  // 헤더 charset → <meta charset> → utf-8 순으로 정합니다.
  const buffer = Buffer.from(await res.arrayBuffer());
  const fromHeader = /charset=["']?([\w-]+)/i.exec(res.headers.get("content-type") ?? "")?.[1];
  const fromMeta = /charset=["']?\s*([\w-]+)/i.exec(buffer.subarray(0, 4096).toString("latin1"))?.[1];
  const charset = (fromHeader || fromMeta || "utf-8").toLowerCase();
  try {
    return new TextDecoder(charset).decode(buffer);
  } catch {
    return buffer.toString("utf8");
  }
}

/** 사이트 주소만 줘도 흔한 위치에서 RSS/Atom 을 찾아봅니다. */
export async function discoverFeed(siteUrl) {
  try {
    const html = await get(siteUrl);
    const $ = cheerio.load(html);
    const href = $('link[type="application/rss+xml"], link[type="application/atom+xml"]').first().attr("href");
    if (href) return new URL(href, siteUrl).href;
  } catch { /* 아래 후보들로 계속 */ }
  for (const p of ["/rss", "/rss.xml", "/feed", "/feed.xml", "/atom.xml", "/index.xml"]) {
    const candidate = new URL(p, siteUrl).href;
    try {
      const body = await get(candidate);
      if (/<(rss|feed)[\s>]/i.test(body)) return candidate;
    } catch { /* 다음 후보 */ }
  }
  return null;
}

export async function fetchFeed(feedUrl, limit = 5) {
  const xml = await get(feedUrl);
  const $ = cheerio.load(xml, { xmlMode: true });
  const items = [];
  $("item, entry").each((_, el) => {
    const node = $(el);
    const link = node.find("link").attr("href") || node.find("link").first().text().trim();
    const title = node.find("title").first().text().trim();
    const date = node.find("pubDate, published, updated").first().text().trim();
    if (link) items.push({ url: link, title, publishedAt: date });
  });
  return items.slice(0, limit);
}

const DROP = "script,style,noscript,nav,header,footer,aside,form,iframe,svg,.comment,.comments,#comments";

/** 글 본문을 최대한 얌전하게 뽑아냅니다. */
export async function fetchArticle(url) {
  const html = await get(url);
  const $ = cheerio.load(html);
  $(DROP).remove();

  const meta = (sel, attr = "content") => $(sel).first().attr(attr)?.trim() || "";
  const title =
    meta('meta[property="og:title"]') || $("h1").first().text().trim() || $("title").first().text().trim();
  const description = meta('meta[property="og:description"]') || meta('meta[name="description"]');
  const image = meta('meta[property="og:image"]');
  const publishedAt =
    meta('meta[property="article:published_time"]') || $("time").first().attr("datetime") || "";

  let body = "";
  for (const sel of ["article", "main", '[itemprop="articleBody"]', ".post-content", ".entry-content", ".se-main-container", "#content", "body"]) {
    const t = $(sel).first().text().replace(/\s+\n/g, "\n").replace(/[ \t]{2,}/g, " ").trim();
    if (t.length > body.length) body = t;
    if (body.length > 1200) break;
  }
  const text = body.replace(/\n{3,}/g, "\n\n").slice(0, 12000);

  const images = [];
  $("img").each((_, el) => {
    const src = $(el).attr("src") || $(el).attr("data-src");
    if (src && !src.startsWith("data:")) {
      try { images.push(new URL(src, url).href); } catch { /* 잘못된 주소는 무시 */ }
    }
  });

  return { url, title, description, image, publishedAt, text, images: images.slice(0, 12), wordCount: text.length };
}

/**
 * 설정에 따라 분석 대상 글 목록을 만들고 본문까지 받아옵니다.
 * 이미 처리한 글은 stateFile 로 걸러 중복 발행을 막습니다.
 */
export async function collectArticles(blogConfig) {
  const { feed, urls = [], limit = 3, stateFile } = blogConfig;
  const seen = new Set(readJson(stateFile, { seen: [] })?.seen ?? []);

  let targets = [...urls];
  if (!targets.length && feed) {
    const feedUrl = /\.(xml|rss)$|\/(rss|feed|atom)/i.test(feed) ? feed : (await discoverFeed(feed)) ?? feed;
    log.info(`피드: ${feedUrl}`);
    targets = (await fetchFeed(feedUrl, limit * 3)).map((i) => i.url);
  }
  const fresh = targets.filter((u) => !seen.has(u)).slice(0, limit);
  if (!fresh.length) {
    log.warn("새로 분석할 글이 없습니다 (모두 처리 완료 또는 대상 미지정).");
    return { articles: [], commit: () => {} };
  }

  const articles = [];
  for (const url of fresh) {
    try {
      const a = await fetchArticle(url);
      log.ok(`분석: ${a.title || url} (${a.wordCount}자)`);
      articles.push(a);
    } catch (e) {
      log.warn(`가져오기 실패 ${url} — ${e.message}`);
    }
  }

  // 발행까지 성공한 뒤에 호출해서 "처리 완료" 로 기록합니다.
  const commit = () => {
    if (!stateFile) return;
    const next = [...seen, ...articles.map((a) => a.url)];
    writeJson(stateFile, { seen: next.slice(-500), updatedAt: new Date().toISOString() });
  };
  return { articles, commit };
}
