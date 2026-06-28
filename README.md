# Biznews-Jayant

`biznews-jayant` is an Agent Skill for researching topics across three Jayant-authored Substack sources:

- Bharatnama: `https://bharatnama.substack.com`
- BizNews by Jay: `https://biznewsbyjay.substack.com`
- Decoding the Dragon: `https://decodingthedragon.substack.com`

The skill runs Python retrieval first, cleaning Substack HTML, filtering by topic relevance, and emitting compact evidence so the agent does not waste context on raw page markup.

## Install

```bash
./bin/install.sh
```

This installs the skill globally for Codex-compatible Agent Skills hosts.

## Validate

```bash
./bin/validate.sh
```

## Direct engine run

```bash
python3 biznews-jayant/scripts/biznews_jayant.py "India AI policy" --emit compact
```

The output follows an original report shape: badge, `What I found:`, bold lead-ins, key patterns, source coverage, and useful source links.

## Contents

- `biznews-jayant/SKILL.md` - skill instructions
- `biznews-jayant/scripts/` - Python retrieval and rendering engine
- `biznews-jayant/references/` - output contract reference
- `tests/` - fixture-backed tests for retrieval, cleanup, and output shape
