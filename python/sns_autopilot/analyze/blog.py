"""블로그 글 수집·본문 추출."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Callable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .. import log
from ..paths import read_json, write_json

UA = "Mozilla/5.0 (compatible; SNS-Autopilot/0.1)"
TIMEOUT = 20

DROP_SELECTORS = [
    "script", "style", "noscript", "nav", "header", "footer", "aside",
    "form", "iframe", "svg", ".comment", ".comments", "#comments",
]
BODY_SELECTORS = [
    "article", "main", '[itemprop="articleBody"]', ".post-content",
    ".entry-content", ".se-main-container", "#content", "body",
]
FEED_CANDIDATES = ["/rss", "/rss.xml", "/feed", "/feed.xml", "/atom.xml", "/index.xml"]
_FEEDISH = re.compile(r"\.(xml|rss)$|/(rss|feed|atom)", re.IGNORECASE)
_META_CHARSET = re.compile(rb"""charset=["']?\s*([\w-]+)""", re.IGNORECASE)


@dataclass
class Article:
    url: str
    title: str = ""
    description: str = ""
    image: str = ""
    publishedAt: str = ""  # noqa: N815 - JSON 키를 노드 버전과 맞춥니다
    text: str = ""
    images: list[str] = field(default_factory=list)
    wordCount: int = 0  # noqa: N815

    def to_dict(self) -> dict:
        return asdict(self)


def _get(url: str) -> str:
    response = requests.get(url, headers={"user-agent": UA, "accept": "*/*"}, timeout=TIMEOUT)
    response.raise_for_status()

    # Content-Type 에 charset 이 없으면 requests 는 ISO-8859-1 로 가정합니다.
    # 그대로 두면 한글이 전부 깨져서 모델에 쓰레기 텍스트가 들어갑니다.
    # 헤더에 없을 때는 <meta charset> → 바이트 추정 순으로 직접 정합니다.
    if "charset" not in (response.headers.get("content-type") or "").lower():
        found = _META_CHARSET.search(response.content[:4096])
        detected = found.group(1).decode("ascii", "ignore") if found else ""
        response.encoding = detected or response.apparent_encoding or "utf-8"
    return response.text


def discover_feed(site_url: str) -> str | None:
    """사이트 주소만 줘도 흔한 위치에서 RSS/Atom 을 찾아봅니다."""
    try:
        soup = BeautifulSoup(_get(site_url), "html.parser")
        link = soup.find("link", type=re.compile(r"application/(rss|atom)\+xml"))
        if link and link.get("href"):
            return urljoin(site_url, link["href"])
    except requests.RequestException:
        pass

    for path in FEED_CANDIDATES:
        candidate = urljoin(site_url, path)
        try:
            body = _get(candidate)
            if re.search(r"<(rss|feed)[\s>]", body, re.IGNORECASE):
                return candidate
        except requests.RequestException:
            continue
    return None


def fetch_feed(feed_url: str, limit: int = 5) -> list[dict]:
    soup = BeautifulSoup(_get(feed_url), "xml")
    items = []
    for node in soup.find_all(["item", "entry"]):
        link_node = node.find("link")
        url = ""
        if link_node is not None:
            url = link_node.get("href") or (link_node.text or "").strip()
        if not url:
            continue
        title_node = node.find("title")
        date_node = node.find(["pubDate", "published", "updated"])
        items.append({
            "url": url,
            "title": (title_node.text or "").strip() if title_node else "",
            "publishedAt": (date_node.text or "").strip() if date_node else "",
        })
    return items[:limit]


def fetch_article(url: str) -> Article:
    """글 본문을 최대한 얌전하게 뽑아냅니다."""
    soup = BeautifulSoup(_get(url), "html.parser")
    for selector in DROP_SELECTORS:
        for node in soup.select(selector):
            node.decompose()

    def meta(name: str, attr: str = "property") -> str:
        node = soup.find("meta", attrs={attr: name})
        return (node.get("content") or "").strip() if node else ""

    h1 = soup.find("h1")
    title_tag = soup.find("title")
    title = meta("og:title") or (h1.get_text(strip=True) if h1 else "") or (
        title_tag.get_text(strip=True) if title_tag else ""
    )
    description = meta("og:description") or meta("description", "name")
    time_node = soup.find("time")
    published = meta("article:published_time") or (time_node.get("datetime", "") if time_node else "")

    body = ""
    for selector in BODY_SELECTORS:
        node = soup.select_one(selector)
        if not node:
            continue
        text = re.sub(r"[ \t]{2,}", " ", node.get_text("\n", strip=True))
        if len(text) > len(body):
            body = text
        if len(body) > 1200:
            break
    text = re.sub(r"\n{3,}", "\n\n", body)[:12000]

    images = []
    for node in soup.find_all("img"):
        src = node.get("src") or node.get("data-src")
        if src and not src.startswith("data:"):
            images.append(urljoin(url, src))

    return Article(
        url=url, title=title, description=description, image=meta("og:image"),
        publishedAt=published, text=text, images=images[:12], wordCount=len(text),
    )


def collect_articles(blog_config: dict) -> tuple[list[dict], Callable[[], None]]:
    """분석 대상 글을 모으고 본문까지 받아옵니다.

    이미 처리한 글은 stateFile 로 걸러 중복 발행을 막습니다.
    반환된 commit() 은 **발행에 성공한 뒤** 호출해야 합니다.
    """
    state_file = blog_config.get("stateFile")
    seen = set((read_json(state_file, {}) or {}).get("seen", [])) if state_file else set()

    targets: list[str] = list(blog_config.get("urls") or [])
    feed = blog_config.get("feed")
    if not targets and feed:
        feed_url = feed if _FEEDISH.search(feed) else (discover_feed(feed) or feed)
        log.info(f"피드: {feed_url}")
        targets = [item["url"] for item in fetch_feed(feed_url, (blog_config.get("limit") or 3) * 3)]

    fresh = [url for url in targets if url not in seen][: blog_config.get("limit") or 3]
    if not fresh:
        log.warn("새로 분석할 글이 없습니다 (모두 처리 완료 또는 대상 미지정).")
        return [], lambda: None

    articles: list[dict] = []
    for url in fresh:
        try:
            article = fetch_article(url)
            log.ok(f"분석: {article.title or url} ({article.wordCount}자)")
            articles.append(article.to_dict())
        except Exception as exc:  # noqa: BLE001 - 한 글이 실패해도 나머지는 계속
            log.warn(f"가져오기 실패 {url} — {exc}")

    def commit() -> None:
        if not state_file:
            return
        merged = list(seen) + [a["url"] for a in articles]
        write_json(state_file, {"seen": merged[-500:], "updatedAt": datetime.now().isoformat(timespec="seconds")})

    return articles, commit
