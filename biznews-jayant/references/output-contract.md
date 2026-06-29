# Output Contract

Use this when the user asks for a report, memo, or comparison based on `biznews-jayant` results.

## Writing Principles

Follow these every time you write a response:

- **Plain language.** Write as if explaining to a smart friend who hasn't read any of the articles. If a concept sounds technical, break it down right there — e.g. "quantitative tightening" becomes "the central bank shrinking the money supply by selling off bonds."
- **Detail and depth.** Don't just mention what was found — explain the topic itself, informed by the sources. The `**What this actually means:**` section should read like a well-written explainer, not a bullet-point summary.
- **Engaging, not dry.** Use active voice. Vary sentence length. Make the reader want to keep reading.
- **Never expose process details.** Do not say "the engine found", "scored X", "matched terms", "Python fetched", "archive search", or anything about how the skill works internally. The user wants the research result, not a technical log.
- **Hyperlink meaningfully.** Embed links in descriptive words or phrases that tell the reader what they'll find — not just article titles.
  - ✅ `India's [push to regulate AI](url)`, `[how China is managing its tech giants](url)`
  - ❌ `[India AI Roundup — June 2025](url)` *(bare article title as link)*

---

## Standard Report

```markdown
biznews-jayant v{version} - Jayant Substack scan

What I found:

**Strongest signal.** Synthesis paragraph about what the top source covers and why it
matters. Write in plain terms, breaking down any concepts. Embed at least one link in a
descriptive phrase — not just the article title.

**Second angle.** (Optional) A second paragraph when another source adds contrast or a
different perspective. Plain language, concepts explained.

---

**What this actually means:**

A detailed, multi-paragraph explanation of the user's query topic — informed by everything
the sources said, but written as a genuine explainer, not a summary of articles. Use simple
words throughout. Break down every concept or term that might be unfamiliar. Cover the full
picture: what is happening, why it is happening, what the different sides say, and what it
means for the reader. Be thorough — this is the section the reader will learn the most from.
Embed links naturally in relevant phrases as you go.

---

KEY PATTERNS from the research:
1. **Source:** [Descriptive phrase about what this article covers](url) — what this finding means, in simple terms.
2. **Source:** [Descriptive phrase](url) — explanation.
3. **Source:** [Descriptive phrase](url) — explanation.

---
- Bharatnama: {n} matches from {n} articles checked
- BizNews by Jay: {n} matches from {n} articles checked
- Decoding the Dragon: {n} matches from {n} articles checked
- Coverage confidence: strong|mixed|thin|absent
---

Useful source links:
- [Descriptive phrase about what this article covers](url) - source, date
- [Descriptive phrase](url) - source, date
```

---

## Comparison Report

Use the same scaffold, but replace the first two synthesis paragraphs with:

- `**Quick verdict.**` — What's the bottom line, in plain terms?
- `**Where the sources differ.**` — Explain the contrast: what does each source emphasise and why does that matter?

Then include the `**What this actually means:**` block with a detailed explanation of both sides of the comparison. Keep KEY PATTERNS, the coverage footer, and useful links.

---

## Link Formatting Rules

- **Always** embed links in anchor text that describes what the reader will find: `[India's AI governance framework](url)`, `[the RBI's case for holding rates](url)`
- **Avoid** linking only on article titles unless the title is itself descriptive and self-explanatory
- In `Useful source links`, use a descriptive phrase: `[How India is approaching AI regulation in 2025](url)` rather than the bare article headline

---

## Recency Policy

Recency affects ranking only — all articles remain searchable:

- Latest 30 days: strongest boost
- 31–90 days: high boost
- 91–180 days: moderate boost
- 181–365 days: neutral weight
- Older posts: lower weight, still included
