from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "biznews-jayant" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from lib import biznews_core as core


def test_html_to_text_removes_scripts_and_tags():
    text = core.html_to_text("<article><h1>Title</h1><p>Hello <b>world</b></p><script>bad()</script><p>Subscribe</p></article>")
    assert "Title" in text
    assert "Hello world" in text
    assert "bad()" not in text
    assert "Subscribe" not in text
    assert "<p>" not in text


def test_parse_feed_reads_content_encoded():
    feed = (ROOT / "tests" / "fixtures" / "feed.xml").read_text(encoding="utf-8")
    articles = core.parse_feed(feed, "bharatnama", "https://bharatnama.substack.com", 10)
    assert len(articles) == 2
    assert articles[0].title == "India AI policy shifts"
    assert "changing AI policy" in articles[0].text


def test_scoring_and_excerpt_reduce_token_noise():
    article = core.Article(
        source="bharatnama",
        source_url="https://bharatnama.substack.com",
        title="India AI policy shifts",
        url="https://example.com",
        text="Navigation Subscribe Share\n\nIndia AI policy matters for startups.\n\nFooter garbage",
    )
    scored = core.score_article("India AI policy", article)
    excerpt = core.compact_excerpt(scored.text, scored.matched_terms, 60)
    assert scored.score > 0
    assert "India AI policy" in excerpt
    assert len(excerpt) <= 63


def test_run_report_uses_cached_retrieval(monkeypatch, tmp_path: Path):
    feed = (ROOT / "tests" / "fixtures" / "feed.xml").read_text(encoding="utf-8")

    def fake_fetch_url(url: str, timeout: float = 15.0) -> str:
        if url.endswith("/p/cricket"):
            return "<article><p>Sports notes only.</p></article>"
        return feed

    monkeypatch.setattr(core, "fetch_url", fake_fetch_url)
    report = core.run_report("India AI policy", max_posts=5, cache_dir=tmp_path, excerpt_chars=120)
    assert report.topic == "India AI policy"
    assert len(report.sources) == 3
    assert all(source.checked == 2 for source in report.sources)
    assert sum(len(source.articles) for source in report.sources) == 3


def test_json_output_is_serializable(monkeypatch, tmp_path: Path, capsys):
    feed = (ROOT / "tests" / "fixtures" / "feed.xml").read_text(encoding="utf-8")
    monkeypatch.setattr(core, "fetch_url", lambda url, timeout=15.0: feed)
    code = core.main(["India", "AI", "policy", "--emit", "json", "--cache-dir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["topic"] == "India AI policy"


def test_compact_output_uses_biznews_scaffold(monkeypatch, tmp_path: Path, capsys):
    feed = (ROOT / "tests" / "fixtures" / "feed.xml").read_text(encoding="utf-8")

    def fake_fetch_url(url: str, timeout: float = 15.0) -> str:
        if url.endswith("/p/cricket"):
            return "<article><p>Sports notes only.</p></article>"
        return feed

    monkeypatch.setattr(core, "fetch_url", fake_fetch_url)
    code = core.main(["India", "AI", "policy", "--cache-dir", str(tmp_path)])
    text = capsys.readouterr().out
    assert code == 0
    assert text.startswith("biznews-jayant v")
    assert "What I found:" in text
    assert "KEY PATTERNS from the research:" in text
    assert "PASS-THROUGH FOOTER" in text
    assert "Useful source links:" in text
    assert "Sources:" not in text
