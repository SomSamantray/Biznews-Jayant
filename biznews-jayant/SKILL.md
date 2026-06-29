---
name: biznews-jayant
description: Use this skill to research any topic across the full public Bharatnama, BizNews by Jay, and Decoding the Dragon Substack archives. It runs Python archive API retrieval, article cleanup, caching, topic filtering, and recency weighting first so the agent synthesizes from compact evidence instead of raw web pages.
---

# biznews-jayant

This is a standard Agent Skill. It should work in Codex, Claude Code, and other hosts that load Agent Skills from a `SKILL.md` folder. The Python engine uses only the standard library.

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

On Windows, use `python` or `py -3` instead of `python3`. If `$SKILL_DIR` is not set by the host, use the directory that contains this `SKILL.md`. If the host has no shell-variable expansion, resolve the absolute skill directory path first and pass it directly.

3. Read the engine output. It contains full-archive matches, cleaned article text, filtered excerpts, recency weighting, and a consistent synthesis scaffold.
4. Use six analysis roles overall:
   - Source collector: Bharatnama
   - Source collector: BizNews by Jay
   - Source collector: Decoding the Dragon
   - Cross-source synthesizer
   - Evidence skeptic
   - Final editor
5. Emit the final answer following the output contract at `$SKILL_DIR/references/output-contract.md`. The required structure is:

```markdown
biznews-jayant v{version} - Jayant Substack scan

What I found:

**Bold lead-in.** Synthesis paragraph in plain language. Break down any jargon. Embed
links in descriptive phrases — not just article titles.

**Bold lead-in.** Second synthesis paragraph if there is enough evidence.

---

**What this actually means:**

A detailed, multi-paragraph plain-language explainer about the user's query topic — what
is happening, why, what the different perspectives are, and what it means for the reader.
Break down every concept. Be thorough and engaging. Embed links naturally in phrases.

---

KEY PATTERNS from the research:
1. **Source:** [Descriptive phrase about what this article covers](url) — plain explanation.
2. **Source:** [Descriptive phrase](url) — plain explanation.

---
- Bharatnama: ...
- BizNews by Jay: ...
- Decoding the Dragon: ...
- Coverage confidence: strong|mixed|thin|absent
---

Useful source links:
- [Descriptive phrase about what this covers](url) - source, date
```

## Engine Rules

- Do not fetch or paste raw Substack HTML into the final answer.
- Prefer the engine's compact output over manual web reading.
- Search scope is the full public archive for each source through Substack archive API search. The engine then fetches only the strongest matching article pages for full-text cleanup and final ranking. Archive browsing and RSS are fallbacks if searched archive retrieval fails.
- Recency is a ranking input, not a hard filter: articles from the latest 30 days get the strongest boost, then older articles receive progressively lower weights while remaining searchable.
- Preserve the badge, `What I found:`, bold lead-in paragraphs, `**What this actually means:**` explainer, `KEY PATTERNS from the research:`, source-coverage footer, and useful links list.
- If the engine returns no matches, say that the three sources did not have enough on this topic and list what was checked — in plain language, no jargon.
- If one source fails, continue with the other sources and mention the failure briefly under confidence.
- Keep citations inline or in the final useful links list. Do not invent article titles or dates.
- Do not add a trailing `Sources:` block. The `Useful source links:` section is the citation surface.
- **Write in plain language.** The `**What this actually means:**` block must be a detailed, multi-paragraph explanation of the user's query topic — not a summary of articles, but a genuine explainer with concepts broken down. Be thorough and engaging.
- **Hyperlink meaningfully.** Embed every link in a descriptive phrase or sentence fragment that tells the reader what they'll find — never a bare article title as the only anchor text.
- **Never expose internal process details** in the response: no mention of scoring, matched terms, recency weights, Python, archive API, or how the skill works. The user wants the answer, not the method.

## Useful Commands

Run a normal compact research bundle:

```bash
python3 "$SKILL_DIR/scripts/biznews_jayant.py" "India AI policy" --emit compact
```

Windows:

```powershell
python "$env:SKILL_DIR\scripts\biznews_jayant.py" "India AI policy" --emit compact
```

Return machine-readable evidence:

```bash
python3 "$SKILL_DIR/scripts/biznews_jayant.py" "China EVs" --emit json
```

Check local setup and source reachability:

```bash
python3 "$SKILL_DIR/scripts/biznews_jayant.py" --diagnose
```
