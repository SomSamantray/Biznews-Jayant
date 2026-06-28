from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


SOURCES: dict[str, str] = {
    "bharatnama": "https://bharatnama.substack.com",
    "biznewsbyjay": "https://biznewsbyjay.substack.com",
    "decodingthedragon": "https://decodingthedragon.substack.com",
}

DEFAULT_CACHE_DIR = Path(os.environ.get("BIZNEWS_JAYANT_CACHE_DIR", Path.home() / ".cache" / "biznews-jayant"))
USER_AGENT = "biznews-jayant/0.1 (+https://agentskills.io)"
VERSION = "0.1.0"


@dataclass(frozen=True)
class Article:
    source: str
    source_url: str
    title: str
    url: str
    published_at: str | None = None
    text: str = ""
    score: float = 0.0
    matched_terms: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SourceResult:
    source: str
    source_url: str
    articles: list[Article]
    checked: int
    error: str | None = None


@dataclass(frozen=True)
class Report:
    topic: str
    generated_at: str
    sources: list[SourceResult]
    notes: list[str]


class TextExtractor(HTMLParser):
    """Small HTML-to-text extractor for Substack pages and feed content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if tag in {"p", "br", "div", "li", "h1", "h2", "h3", "blockquote"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag in {"p", "li", "h1", "h2", "h3", "blockquote"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        raw = html.unescape(" ".join(self._parts))
        raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
        raw = re.sub(r"\n\s+", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        return "\n".join(_dedupe_adjacent(lines))


def html_to_text(page: str) -> str:
    extractor = TextExtractor()
    extractor.feed(page)
    extractor.close()
    return drop_boilerplate(extractor.text())


def drop_boilerplate(text: str) -> str:
    noisy_patterns = [
        re.compile(r"^https?://\S+$", re.IGNORECASE),
        re.compile(r"^join\s+\d+k\+?\s+others\b", re.IGNORECASE),
        re.compile(r"^(subscribe|share|like|comment|best,?)$", re.IGNORECASE),
        re.compile(r"^thanks\s+for\s+reading\b", re.IGNORECASE),
        re.compile(r"^this\s+post\s+is\s+public\b", re.IGNORECASE),
        re.compile(r"^copy\s+link$", re.IGNORECASE),
    ]
    cleaned: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(pattern.search(line) for pattern in noisy_patterns):
            continue
        line = re.sub(r"https?://\S+", "", line).strip()
        if line:
            cleaned.append(line)
    return "\n".join(_dedupe_adjacent(cleaned))


def _dedupe_adjacent(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if not out or out[-1] != line:
            out.append(line)
    return out


def fetch_url(url: str, timeout: float = 15.0) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def cache_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def read_cache(cache_dir: Path, key: str, max_age_seconds: int) -> str | None:
    path = cache_dir / f"{key}.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if time.time() - float(payload.get("created_at", 0)) > max_age_seconds:
        return None
    body = payload.get("body")
    return body if isinstance(body, str) else None


def write_cache(cache_dir: Path, key: str, body: str) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {"created_at": time.time(), "body": body}
    (cache_dir / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")


def fetch_cached(url: str, cache_dir: Path, timeout: float, max_age_seconds: int) -> str:
    key = cache_key(url)
    cached = read_cache(cache_dir, key, max_age_seconds)
    if cached is not None:
        return cached
    body = fetch_url(url, timeout=timeout)
    write_cache(cache_dir, key, body)
    return body


def parse_feed(feed_xml: str, source: str, source_url: str, limit: int) -> list[Article]:
    root = ET.fromstring(feed_xml)
    articles: list[Article] = []
    for item in root.findall(".//item")[:limit]:
        title = _first_text(item, ["title"])
        url = _first_text(item, ["link"])
        published_at = _first_text(item, ["pubDate", "published", "updated"]) or None
        body_html = _namespaced_text(item, "encoded") or _first_text(item, ["description", "summary"]) or ""
        if not title or not url:
            continue
        articles.append(
            Article(
                source=source,
                source_url=source_url,
                title=html.unescape(title.strip()),
                url=url.strip(),
                published_at=published_at.strip() if published_at else None,
                text=html_to_text(body_html),
            )
        )
    return articles


def _first_text(item: ET.Element, names: list[str]) -> str:
    for name in names:
        value = item.findtext(name)
        if value:
            return value
    return ""


def _namespaced_text(item: ET.Element, local_name: str) -> str:
    for child in item:
        if child.tag.rsplit("}", 1)[-1] == local_name and child.text:
            return child.text
    return ""


def topic_terms(topic: str) -> list[str]:
    stop = {"the", "and", "for", "with", "about", "from", "this", "that", "into", "what", "why", "how"}
    terms = []
    for token in re.findall(r"[a-zA-Z0-9]+", topic.lower()):
        if len(token) >= 3 and token not in stop and token not in terms:
            terms.append(token)
    return terms


def score_article(topic: str, article: Article) -> Article:
    terms = topic_terms(topic)
    title = article.title.lower()
    body = article.text.lower()
    matched: list[str] = []
    score = 0.0
    for term in terms:
        title_hits = title.count(term)
        body_hits = body.count(term)
        if title_hits or body_hits:
            matched.append(term)
            score += title_hits * 4.0 + min(body_hits, 8) * 1.0
    phrase = topic.lower().strip()
    if phrase and phrase in title:
        score += 8.0
    if phrase and phrase in body:
        score += 4.0
    return Article(
        source=article.source,
        source_url=article.source_url,
        title=article.title,
        url=article.url,
        published_at=article.published_at,
        text=article.text,
        score=score,
        matched_terms=matched,
    )


def compact_excerpt(text: str, terms: list[str], max_chars: int) -> str:
    if not text:
        return ""
    paragraphs = [p.strip() for p in re.split(r"\n{1,2}", text) if p.strip()]
    ranked = sorted(
        paragraphs,
        key=lambda p: sum(p.lower().count(term) for term in terms),
        reverse=True,
    )
    chosen: list[str] = []
    total = 0
    for paragraph in ranked or paragraphs:
        if paragraph in chosen:
            continue
        if total + len(paragraph) > max_chars and chosen:
            continue
        chosen.append(paragraph)
        total += len(paragraph)
        if total >= max_chars:
            break
    excerpt = "\n\n".join(chosen)[:max_chars].strip()
    return excerpt + ("..." if len(excerpt) == max_chars else "")


def collect_source(
    source: str,
    source_url: str,
    topic: str,
    *,
    max_posts: int,
    timeout: float,
    cache_dir: Path,
    cache_ttl: int,
    min_score: float,
    excerpt_chars: int,
) -> SourceResult:
    try:
        feed_url = source_url.rstrip("/") + "/feed"
        feed_xml = fetch_cached(feed_url, cache_dir / "feeds", timeout, cache_ttl)
        candidates = parse_feed(feed_xml, source, source_url, limit=max_posts)
        checked = len(candidates)
        scored: list[Article] = []
        for article in candidates:
            enriched = article
            if len(enriched.text) < 400:
                try:
                    raw_page = fetch_cached(article.url, cache_dir / "articles", timeout, cache_ttl)
                    enriched = Article(
                        source=article.source,
                        source_url=article.source_url,
                        title=article.title,
                        url=article.url,
                        published_at=article.published_at,
                        text=html_to_text(raw_page),
                    )
                except Exception:
                    enriched = article
            scored_article = score_article(topic, enriched)
            if scored_article.score >= min_score:
                scored.append(scored_article)
        ranked = sorted(scored, key=lambda item: item.score, reverse=True)
        clipped = [
            Article(
                source=item.source,
                source_url=item.source_url,
                title=item.title,
                url=item.url,
                published_at=item.published_at,
                text=compact_excerpt(item.text, item.matched_terms, excerpt_chars),
                score=item.score,
                matched_terms=item.matched_terms,
            )
            for item in ranked
        ]
        return SourceResult(source=source, source_url=source_url, articles=clipped, checked=checked)
    except Exception as exc:
        return SourceResult(source=source, source_url=source_url, articles=[], checked=0, error=str(exc))


def run_report(
    topic: str,
    *,
    max_posts: int = 20,
    timeout: float = 15.0,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    cache_ttl: int = 60 * 60 * 24,
    min_score: float = 2.0,
    excerpt_chars: int = 900,
) -> Report:
    notes = [
        "Python retrieved feeds, cleaned HTML, scored topic relevance, and emitted compact excerpts before model synthesis.",
        "Six-role synthesis plan: 3 source collectors, 2 cross-checkers, 1 final editor.",
    ]
    results: list[SourceResult] = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(
                collect_source,
                source,
                source_url,
                topic,
                max_posts=max_posts,
                timeout=timeout,
                cache_dir=cache_dir,
                cache_ttl=cache_ttl,
                min_score=min_score,
                excerpt_chars=excerpt_chars,
            ): source
            for source, source_url in SOURCES.items()
        }
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda result: list(SOURCES).index(result.source))
    return Report(
        topic=topic,
        generated_at=datetime.now(timezone.utc).isoformat(),
        sources=results,
        notes=notes,
    )


def top_articles(report: Report, limit: int = 5) -> list[Article]:
    articles = [article for source in report.sources for article in source.articles]
    return sorted(articles, key=lambda item: item.score, reverse=True)[:limit]


def diverse_articles(report: Report, limit: int = 3) -> list[Article]:
    ranked = top_articles(report, limit=50)
    selected: list[Article] = []
    used_sources: set[str] = set()
    for article in ranked:
        if article.source in used_sources:
            continue
        selected.append(article)
        used_sources.add(article.source)
        if len(selected) >= limit:
            return selected
    for article in ranked:
        if article not in selected:
            selected.append(article)
        if len(selected) >= limit:
            break
    return selected


def confidence_label(report: Report) -> str:
    source_hits = sum(1 for source in report.sources if source.articles)
    total_hits = sum(len(source.articles) for source in report.sources)
    if total_hits == 0:
        return "absent"
    if source_hits >= 3 and total_hits >= 6:
        return "strong"
    if source_hits >= 2:
        return "mixed"
    return "thin"


def source_label(source: str) -> str:
    return {
        "bharatnama": "Bharatnama",
        "biznewsbyjay": "BizNews by Jay",
        "decodingthedragon": "Decoding the Dragon",
    }.get(source, source)


def _lead_sentence(article: Article) -> str:
    text = article.text.strip().replace("\n", " ")
    if not text:
        return "No excerpt was available after cleanup."
    parts = re.split(r"(?<=[.!?])\s+", text)
    sentence = parts[0].strip() if parts else text[:220].strip()
    return sentence[:260].rstrip() + ("..." if len(sentence) > 260 else "")


def render_compact(report: Report) -> str:
    top = top_articles(report, limit=5)
    confidence = confidence_label(report)
    source_hits = sum(1 for source in report.sources if source.articles)
    total_checked = sum(source.checked for source in report.sources)
    total_matches = sum(len(source.articles) for source in report.sources)
    lines = [
        f"biznews-jayant v{VERSION} - Jayant Substack scan",
        "",
        "What I found:",
        "",
    ]
    if total_matches == 0:
        lines.extend([
            "**The three-source archive scan came up thin.** The Python engine checked the latest RSS entries from Bharatnama, BizNews by Jay, and Decoding the Dragon, cleaned the HTML, and did not find enough topic-matched evidence to support a strong synthesis.",
            "",
            "KEY PATTERNS from the research:",
            "1. No source crossed the relevance threshold for this topic.",
            f"2. Coverage confidence is {confidence} across {total_checked} checked posts.",
            "",
        ])
    else:
        leads = diverse_articles(report, limit=3)
        strongest = leads[0]
        lines.extend([
            f"**{source_label(strongest.source)} is the strongest signal for this topic.** [{strongest.title}]({strongest.url}) is the top-ranked match, with the engine matching {', '.join(strongest.matched_terms) or 'the topic terms'} after stripping Substack markup and boilerplate. {_lead_sentence(strongest)}",
            "",
        ])
        lead_labels = ["adds a contrasting angle", "rounds out the picture"]
        for article, label in zip(leads[1:], lead_labels):
            lines.extend([
                f"**{source_label(article.source)} {label}.** [{article.title}]({article.url}) scored {article.score:.1f} on the cleaned text. {_lead_sentence(article)}",
                "",
            ])
        lines.append("KEY PATTERNS from the research:")
        for index, article in enumerate(top[:5], start=1):
            terms = ", ".join(article.matched_terms) if article.matched_terms else "topic match"
            lines.append(f"{index}. **{source_label(article.source)}:** [{article.title}]({article.url}) - matched {terms}; score {article.score:.1f}.")
        lines.append("")

    lines.extend([
        "<!-- PASS-THROUGH FOOTER: keep this source-coverage block visible in the final response. -->",
        "---",
        "All source collectors reported back.",
    ])
    for source in report.sources:
        status = f"{len(source.articles)} match{'es' if len(source.articles) != 1 else ''} from {source.checked} checked"
        if source.error:
            status += f"; error: {source.error}"
        lines.append(f"- {source_label(source.source)}: {status}")
    lines.extend([
        f"- Coverage confidence: {confidence}",
        f"- Retrieval path: Python RSS fetch -> HTML cleanup -> topic scoring -> compact excerpts",
        "---",
        "<!-- END PASS-THROUGH FOOTER -->",
        "",
        "Useful source links:",
    ])
    for article in top[:8]:
        date = article.published_at or "date unavailable"
        lines.append(f"- [{article.title}]({article.url}) - {source_label(article.source)}, {date}")
    return "\n".join(lines).strip() + "\n"


def report_to_dict(report: Report) -> dict[str, Any]:
    return asdict(report)


def diagnose(timeout: float = 10.0) -> dict[str, Any]:
    checks: dict[str, Any] = {"python": True, "sources": {}}
    for source, source_url in SOURCES.items():
        feed_url = source_url.rstrip("/") + "/feed"
        try:
            body = fetch_url(feed_url, timeout=timeout)
            checks["sources"][source] = {"feed": feed_url, "ok": "<rss" in body[:500].lower() or "<feed" in body[:500].lower()}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            checks["sources"][source] = {"feed": feed_url, "ok": False, "error": str(exc)}
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Research topics across Jayant Substack sources.")
    parser.add_argument("topic", nargs="*", help="Topic to research")
    parser.add_argument("--emit", choices=["compact", "json"], default="compact")
    parser.add_argument("--max-posts", type=int, default=int(os.environ.get("BIZNEWS_JAYANT_MAX_POSTS", "20")))
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("BIZNEWS_JAYANT_TIMEOUT", "15")))
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--cache-ttl", type=int, default=int(os.environ.get("BIZNEWS_JAYANT_CACHE_TTL", str(60 * 60 * 24))))
    parser.add_argument("--min-score", type=float, default=float(os.environ.get("BIZNEWS_JAYANT_MIN_SCORE", "2")))
    parser.add_argument("--excerpt-chars", type=int, default=int(os.environ.get("BIZNEWS_JAYANT_EXCERPT_CHARS", "900")))
    parser.add_argument("--diagnose", action="store_true", help="Check Python and Substack feed reachability")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.diagnose:
        print(json.dumps(diagnose(timeout=args.timeout), indent=2, sort_keys=True))
        return 0
    topic = " ".join(args.topic).strip()
    if not topic:
        parser.error("topic is required unless --diagnose is used")
    report = run_report(
        topic,
        max_posts=args.max_posts,
        timeout=args.timeout,
        cache_dir=args.cache_dir,
        cache_ttl=args.cache_ttl,
        min_score=args.min_score,
        excerpt_chars=args.excerpt_chars,
    )
    if args.emit == "json":
        print(json.dumps(report_to_dict(report), indent=2, sort_keys=True))
    else:
        print(render_compact(report), end="")
    return 0
