/** 본문 + 해시태그를 플랫폼에 맞게 한 덩어리로 합칩니다. */
export function composeText(post, { withHashtags = true, limit = 0 } = {}) {
  const tags = (post.hashtags ?? []).map((t) => (t.startsWith("#") ? t : `#${t}`));
  let text = (post.text ?? "").trim();
  if (withHashtags && tags.length) text += `\n\n${tags.join(" ")}`;
  if (limit && text.length > limit) {
    // 해시태그부터 줄이고, 그래도 넘치면 본문을 자릅니다.
    let kept = [...tags];
    while (kept.length && ((post.text ?? "").trim() + "\n\n" + kept.join(" ")).length > limit) kept.pop();
    text = ((post.text ?? "").trim() + (kept.length ? `\n\n${kept.join(" ")}` : "")).slice(0, limit);
  }
  return text;
}

export const LIMITS = {
  x: 280,
  threads: 500,
  instagram: 2200,
  tiktok: 2200,
  facebook: 5000,
  linkedin: 3000,
  youtube: 5000,
  naver_blog: 0,
};

/** 공개 URL 이 필요한 플랫폼(인스타·스레드)을 위해 로컬 파일 경로를 URL 로 바꿉니다. */
export function publicUrl(localPath) {
  const base = process.env.PUBLIC_MEDIA_BASE_URL;
  if (!base) return null;
  const name = localPath.split("/").slice(-3).join("/");
  return `${base.replace(/\/$/, "")}/${name}`;
}
