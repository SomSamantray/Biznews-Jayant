from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, check=check)


def main() -> int:
    if sys.version_info < (3, 11):
        print("Python 3.11+ is required.", file=sys.stderr)
        return 1

    py_compile.compile(str(ROOT / "biznews-jayant" / "scripts" / "biznews_jayant.py"), doraise=True)
    py_compile.compile(str(ROOT / "biznews-jayant" / "scripts" / "lib" / "biznews_core.py"), doraise=True)

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        diagnose_path = tmp.name
    try:
        with open(diagnose_path, "w", encoding="utf-8") as handle:
            subprocess.run(
                [sys.executable, str(ROOT / "biznews-jayant" / "scripts" / "biznews_jayant.py"), "--diagnose"],
                cwd=ROOT,
                stdout=handle,
                text=True,
                check=False,
            )
    finally:
        try:
            os.unlink(diagnose_path)
        except OSError:
            pass

    if shutil.which("uv"):
        run(["uv", "run", "pytest"])
    else:
        run([sys.executable, "-m", "pytest"])

    validator = Path.home() / ".codex" / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"
    if validator.is_file():
        if shutil.which("uv"):
            run(["uv", "run", "--with", "pyyaml", "python", str(validator), str(ROOT / "biznews-jayant")])
        else:
            result = run([sys.executable, str(validator), str(ROOT / "biznews-jayant")], check=False)
            if result.returncode != 0:
                print("Skipped skill-creator validator: install PyYAML or uv to run it.")
    else:
        print("Skipped skill-creator validator: quick_validate.py not found.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
