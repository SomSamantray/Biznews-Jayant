# Biznews-Jayant

`biznews-jayant` is an Agent Skill for researching topics across three Jayant-authored Substack sources. It is designed for Agent Skills-compatible hosts including Codex, Claude Code, Cursor-style agents, and other tools supported by `skills add`.

- Bharatnama: `https://bharatnama.substack.com`
- BizNews by Jay: `https://biznewsbyjay.substack.com`
- Decoding the Dragon: `https://decodingthedragon.substack.com`

The skill runs Python retrieval first, searching each full public Substack archive through Substack's archive API, then fetching only the strongest matching article pages for full-text cleanup and final ranking. This keeps the archive search broad while keeping runtime and context usage low.

## Install

macOS / Linux:

```bash
./bin/install.sh
```

Windows PowerShell:

```powershell
.\bin\install.ps1
```

This installs the skill globally for Agent Skills-compatible hosts. The same source folder is used by Codex, Claude Code, and other supported agents; unsupported hosts are skipped by the installer.

Direct installer command, if you do not want to use the wrapper:

```bash
npx -y skills@latest add ./biznews-jayant -g -y
```

Windows PowerShell equivalent:

```powershell
npx -y skills@latest add .\biznews-jayant -g -y
```

## Validate

macOS / Linux:

```bash
./bin/validate.sh
```

Windows PowerShell:

```powershell
python .\bin\validate.py
```

If your Windows Python install uses the launcher instead, run:

```powershell
py -3 .\bin\validate.py
```

## Direct engine run

macOS / Linux:

```bash
python3 biznews-jayant/scripts/biznews_jayant.py "India AI policy" --emit compact
```

Windows PowerShell:

```powershell
python .\biznews-jayant\scripts\biznews_jayant.py "India AI policy" --emit compact
```

Or:

```powershell
py -3 .\biznews-jayant\scripts\biznews_jayant.py "India AI policy" --emit compact
```

The output follows an original report shape: badge, `What I found:`, bold lead-ins, key patterns, source coverage, and useful source links. Recent posts get more ranking weight, especially within the latest 30 days, but older archive posts remain searchable.

## Contents

- `biznews-jayant/SKILL.md` - skill instructions
- `biznews-jayant/scripts/` - Python retrieval and rendering engine
- `biznews-jayant/references/` - output contract reference
- `tests/` - fixture-backed tests for retrieval, cleanup, and output shape
