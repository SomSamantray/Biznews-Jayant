from __future__ import annotations

import argparse
import email.utils
import hashlib
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
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
    relevance_score: float = 0.0
    recency_weight: float = 1.0
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


def fetch_cached(url: str, cache_dir: Path, timeout: float, max_age_seconds: int, *, retries: int = 2) -> str:
    key = cache_key(url)
    cached = read_cache(cache_dir, key, max_age_seconds)
    if cached is not None:
        return cached
    for attempt in range(retries + 1):
        try:
            body = fetch_url(url, timeout=timeout)
            break
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt >= retries:
                raise
            time.sleep(1.5 * (attempt + 1))
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


def parse_archive_items(items: list[dict[str, Any]], source: str, source_url: str) -> list[Article]:
    articles: list[Article] = []
    for item in items:
        title = str(item.get("title") or "").strip()
        url = str(item.get("canonical_url") or "").strip()
        slug = str(item.get("slug") or "").strip()
        if not url and slug:
            url = source_url.rstrip("/") + "/p/" + slug
        if not title or not url:
            continue
        subtitle = str(item.get("subtitle") or item.get("description") or "").strip()
        articles.append(
            Article(
                source=source,
                source_url=source_url,
                title=html.unescape(title),
                url=url,
                published_at=str(item.get("post_date") or "").strip() or None,
                text=html_to_text(subtitle),
            )
        )
    return articles


def fetch_archive_articles(
    source: str,
    source_url: str,
    *,
    cache_dir: Path,
    timeout: float,
    cache_ttl: int,
    archive_limit: int,
    search: str | None = None,
    page_size: int = 12,
) -> list[Article]:
    articles: list[Article] = []
    seen: set[str] = set()
    offset = 0
    while len(articles) < archive_limit:
        params: dict[str, str | int] = {"sort": "new", "offset": offset, "limit": page_size}
        if search:
            params["search"] = search
        query = urllib.parse.urlencode(params)
        url = source_url.rstrip("/") + "/api/v1/archive?" + query
        try:
            body = fetch_cached(url, cache_dir / "archives", timeout, cache_ttl, retries=4)
        except Exception:
            if articles:
                break
            raise
        payload = json.loads(body)
        if not isinstance(payload, list) or not payload:
            break
        for article in parse_archive_items(payload, source, source_url):
            if article.url in seen:
                continue
            seen.add(article.url)
            articles.append(article)
            if len(articles) >= archive_limit:
                break
        if len(payload) < page_size:
            break
        offset += len(payload)
        time.sleep(0.15)
    return articles


def discover_articles(
    source: str,
    source_url: str,
    *,
    cache_dir: Path,
    timeout: float,
    cache_ttl: int,
    archive_limit: int,
    topic: str | None = None,
) -> list[Article]:
    try:
        if topic:
            search_articles = fetch_archive_articles(
                source,
                source_url,
                cache_dir=cache_dir,
                timeout=timeout,
                cache_ttl=cache_ttl,
                archive_limit=archive_limit,
                search=topic,
            )
            if search_articles:
                return search_articles
        archive_articles = fetch_archive_articles(
            source,
            source_url,
            cache_dir=cache_dir,
            timeout=timeout,
            cache_ttl=cache_ttl,
            archive_limit=archive_limit,
        )
        if archive_articles:
            return archive_articles
    except Exception:
        pass
    feed_url = source_url.rstrip("/") + "/feed"
    feed_xml = fetch_cached(feed_url, cache_dir / "feeds", timeout, cache_ttl)
    return parse_feed(feed_xml, source, source_url, limit=archive_limit)


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


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None


def recency_weight(published_at: str | None, as_of: datetime | None = None) -> float:
    published = parse_datetime(published_at)
    if not published:
        return 0.85
    as_of = as_of or datetime.now(timezone.utc)
    days = max(0, (as_of - published).days)
    if days <= 30:
        return 1.60
    if days <= 90:
        return 1.35
    if days <= 180:
        return 1.15
    if days <= 365:
        return 1.00
    if days <= 730:
        return 0.80
    return 0.65


def score_article(topic: str, article: Article, *, as_of: datetime | None = None) -> Article:
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
    weight = recency_weight(article.published_at, as_of=as_of)
    final_score = score * weight
    return Article(
        source=article.source,
        source_url=article.source_url,
        title=article.title,
        url=article.url,
        published_at=article.published_at,
        text=article.text,
        score=final_score,
        relevance_score=score,
        recency_weight=weight,
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
    archive_limit: int,
    full_text_limit: int,
    fetch_workers: int,
    as_of: datetime | None,
) -> SourceResult:
    try:
        candidates = discover_articles(
            source,
            source_url,
            cache_dir=cache_dir,
            timeout=timeout,
            cache_ttl=cache_ttl,
            archive_limit=archive_limit,
            topic=topic,
        )
        checked = len(candidates)
        scored: list[Article] = []
        def enrich(article: Article) -> Article:
            try:
                raw_page = fetch_cached(article.url, cache_dir / "articles", timeout, cache_ttl)
                return Article(
                    source=article.source,
                    source_url=article.source_url,
                    title=article.title,
                    url=article.url,
                    published_at=article.published_at,
                    text=html_to_text(raw_page) or article.text,
                )
            except Exception:
                return article

        metadata_ranked = sorted(
            (score_article(topic, article, as_of=as_of) for article in candidates),
            key=lambda item: item.score,
            reverse=True,
        )
        fetch_candidates = metadata_ranked[:max(max_posts, full_text_limit)]

        with ThreadPoolExecutor(max_workers=max(1, fetch_workers)) as pool:
            futures = [pool.submit(enrich, article) for article in fetch_candidates]
            for future in as_completed(futures):
                scored_article = score_article(topic, future.result(), as_of=as_of)
                if scored_article.relevance_score >= min_score:
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
                relevance_score=item.relevance_score,
                recency_weight=item.recency_weight,
                matched_terms=item.matched_terms,
            )
            for item in ranked[:max_posts]
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
    archive_limit: int = 500,
    full_text_limit: int = 60,
    fetch_workers: int = 8,
    as_of: datetime | None = None,
) -> Report:
    notes = [
        "Python searched each full public Substack archive via paginated archive API search, fetched the strongest matching article pages, cleaned HTML, scored topic relevance, applied recency weighting, and emitted compact excerpts before model synthesis.",
        "Recency weighting: newest 30 days get the highest boost; older posts remain searchable with progressively lower weight.",
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
                archive_limit=archive_limit,
                full_text_limit=full_text_limit,
                fetch_workers=fetch_workers,
                as_of=as_of,
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
            "**Nothing strong came back on this topic.** All three sources were checked and not enough relevant content was found to give a solid answer.",
            "",
            "KEY PATTERNS from the research:",
            "1. No strong matches found across all three sources for this topic.",
            f"2. Coverage is {confidence}.",
            "",
        ])
    else:
        leads = diverse_articles(report, limit=3)
        strongest = leads[0]
        lines.extend([
            f"**{source_label(strongest.source)} has the most on this.** [{strongest.title}]({strongest.url}) covers {', '.join(strongest.matched_terms) or 'the topic'}. {_lead_sentence(strongest)}",
            "",
        ])
        lead_labels = ["adds a contrasting angle", "rounds out the picture"]
        for article, label in zip(leads[1:], lead_labels):
            lines.extend([
                f"**{source_label(article.source)} {label}.** [{article.title}]({article.url}) {_lead_sentence(article)}",
                "",
            ])
        lines.append("KEY PATTERNS from the research:")
        for index, article in enumerate(top[:5], start=1):
            terms = ", ".join(article.matched_terms) if article.matched_terms else "the topic"
            lines.append(
                f"{index}. **{source_label(article.source)}:** [{article.title}]({article.url}) — covers: {terms}."
            )
        lines.append("")

    lines.append("---")
    for source in report.sources:
        count = len(source.articles)
        status = f"{count} article{'s' if count != 1 else ''} found"
        if source.error:
            status += f" (note: {source.error})"
        lines.append(f"- {source_label(source.source)}: {status}")
    lines.extend([
        f"- Coverage confidence: {confidence}",
        "---",
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
        archive_url = source_url.rstrip("/") + "/api/v1/archive?sort=new&offset=0&limit=12"
        try:
            payload = json.loads(fetch_url(archive_url, timeout=timeout))
            checks["sources"][source] = {"archive": archive_url, "ok": isinstance(payload, list), "sample_count": len(payload) if isinstance(payload, list) else 0}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            checks["sources"][source] = {"archive": archive_url, "ok": False, "error": str(exc)}
        except json.JSONDecodeError as exc:
            checks["sources"][source] = {"archive": archive_url, "ok": False, "error": str(exc)}
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
    parser.add_argument("--archive-limit", type=int, default=int(os.environ.get("BIZNEWS_JAYANT_ARCHIVE_LIMIT", "500")))
    parser.add_argument("--full-text-limit", type=int, default=int(os.environ.get("BIZNEWS_JAYANT_FULL_TEXT_LIMIT", "60")))
    parser.add_argument("--fetch-workers", type=int, default=int(os.environ.get("BIZNEWS_JAYANT_FETCH_WORKERS", "8")))
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
        archive_limit=args.archive_limit,
        full_text_limit=args.full_text_limit,
        fetch_workers=args.fetch_workers,
    )
    if args.emit == "json":
        print(json.dumps(report_to_dict(report), indent=2, sort_keys=True))
    else:
        print(render_compact(report), end="")
    return 0
