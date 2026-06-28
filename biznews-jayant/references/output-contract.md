# Output Contract

Use this when the user asks for a report, memo, or comparison based on `biznews-jayant` results.

## Standard Report

```markdown
biznews-jayant v{version} - Jayant Substack scan

What I found:

**Strongest signal.** Evidence-backed synthesis paragraph with inline article links.

**Second angle.** Optional second paragraph when another source adds useful contrast.

KEY PATTERNS from the research:
1. **Source:** [Article title](url) - why it matters.
2. **Source:** [Article title](url) - why it matters.
3. **Source:** [Article title](url) - why it matters.

<!-- PASS-THROUGH FOOTER: keep this source-coverage block visible in the final response. -->
---
All source collectors reported back.
- Bharatnama: {n} matches from {n} archive candidates
- BizNews by Jay: {n} matches from {n} archive candidates
- Decoding the Dragon: {n} matches from {n} archive candidates
- Coverage confidence: strong|mixed|thin|absent
- Retrieval path: Python archive API search -> article fetch -> HTML cleanup -> topic scoring -> recency weighting -> compact excerpts
---
<!-- END PASS-THROUGH FOOTER -->

Useful source links:
- [Article title](url) - source, date
```

## Comparison Report

Use the same scaffold, but make the first two synthesis paragraphs:

- `**Quick verdict.**`
- `**Where the sources differ.**`

Keep the key patterns, source-coverage footer, and useful links list.

## Recency Policy

The Python engine searches the full public archive for every source. Recency affects ranking only:

- Latest 30 days: strongest boost
- 31-90 days: high boost
- 91-180 days: moderate boost
- 181-365 days: neutral weight
- Older posts: lower weight, still searchable
