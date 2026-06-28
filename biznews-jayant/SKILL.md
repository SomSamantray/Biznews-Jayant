---
name: biznews-jayant
description: Use this skill to research any topic across the full public Bharatnama, BizNews by Jay, and Decoding the Dragon Substack archives. It runs Python archive API retrieval, article cleanup, caching, topic filtering, and recency weighting first so the agent synthesizes from compact evidence instead of raw web pages.
---

# biznews-jayant

Research a user topic across these fixed author sources:

- Bharatnama: `https://bharatnama.substack.com`
- BizNews by Jay: `https://biznewsbyjay.substack.com`
- Decoding the Dragon: `https://decodingthedragon.substack.com`

## Workflow

1. If the user gave no topic, ask for one short topic.
2. Run the Python engine before synthesis:

```bash
python3 "$SKILL_DIR/scripts/biznews_jayant.py" "$TOPIC" --emit compact
```

If `$SKILL_DIR` is not set by the host, use the directory that contains this `SKILL.md`.

3. Read the engine output. It contains full-archive matches, cleaned article text, filtered excerpts, recency weighting, and a consistent synthesis scaffold.
4. Use six analysis roles overall:
   - Source collector: Bharatnama
   - Source collector: BizNews by Jay
   - Source collector: Decoding the Dragon
   - Cross-source synthesizer
   - Evidence skeptic
   - Final editor
5. Emit the final answer in the same engaging shape as the engine scaffold:

```markdown
biznews-jayant v{version} - Jayant Substack scan

What I found:

**Bold lead-in.** Evidence-backed synthesis paragraph with inline article links.

**Bold lead-in.** Second synthesis paragraph if there is enough evidence.

KEY PATTERNS from the research:
1. **Source:** [Article](url) - why it matters.
2. **Source:** [Article](url) - why it matters.

<!-- PASS-THROUGH FOOTER: keep this source-coverage block visible in the final response. -->
---
All source collectors reported back.
- Bharatnama: ...
- BizNews by Jay: ...
- Decoding the Dragon: ...
- Coverage confidence: strong|mixed|thin|absent
- Retrieval path: Python archive API search -> article fetch -> HTML cleanup -> topic scoring -> recency weighting -> compact excerpts
---
<!-- END PASS-THROUGH FOOTER -->

Useful source links:
- [Article title](url) - source, date
```

## Engine Rules

- Do not fetch or paste raw Substack HTML into the final answer.
- Prefer the engine's compact output over manual web reading.
- Search scope is the full public archive for each source through Substack archive API search. The engine then fetches only the strongest matching article pages for full-text cleanup and final ranking. Archive browsing and RSS are fallbacks if searched archive retrieval fails.
- Recency is a ranking input, not a hard filter: articles from the latest 30 days get the strongest boost, then older articles receive progressively lower weights while remaining searchable.
- Preserve the badge, `What I found:`, bold lead-in paragraphs, `KEY PATTERNS from the research:`, source-coverage footer, and useful links list.
- If the engine returns no matches, say that the three-source archive did not show enough evidence and list what was checked.
- If one source fails, continue with the other sources and mention the failure briefly under confidence.
- Keep citations inline or in the final useful links list. Do not invent article titles or dates.
- Do not add a trailing `Sources:` block. The `Useful source links:` section is the citation surface.

## Useful Commands

Run a normal compact research bundle:

```bash
python3 "$SKILL_DIR/scripts/biznews_jayant.py" "India AI policy" --emit compact
```

Return machine-readable evidence:

```bash
python3 "$SKILL_DIR/scripts/biznews_jayant.py" "China EVs" --emit json
```

Check local setup and source reachability:

```bash
python3 "$SKILL_DIR/scripts/biznews_jayant.py" --diagnose
```
