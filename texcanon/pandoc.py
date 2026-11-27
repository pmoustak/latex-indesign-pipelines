"""Running Pandoc (LaTeX → Pandoc JSON AST)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

READER = "latex+raw_tex-auto_identifiers"
REPO_ROOT = Path(__file__).resolve().parent.parent


class PandocError(RuntimeError):
    pass


def find_pandoc(configured: str | None = None, base: Path | None = None) -> Path:
    """Configured path → $TEXCANON_PANDOC → La2X2In/tools/pandoc-*/ → PATH."""
    candidates: list[Path] = []
    if configured:
        p = Path(configured)
        candidates.append(p if p.is_absolute() or base is None else base / p)
    if os.environ.get("TEXCANON_PANDOC"):
        candidates.append(Path(os.environ["TEXCANON_PANDOC"]))
    tools = REPO_ROOT.parent / "tools"
    if tools.is_dir():
        for d in sorted(tools.glob("pandoc-*"), reverse=True):
            candidates += [d / "pandoc.exe", d / "pandoc"]
    found = shutil.which("pandoc")
    if found:
        candidates.append(Path(found))
    for c in candidates:
        if c.is_file():
            return c.resolve()
    raise PandocError("Δεν βρέθηκε το Pandoc (ούτε στο La2X2In/tools ούτε στο PATH).")


def pandoc_version(exe: Path) -> str:
    out = subprocess.run([str(exe), "--version"], capture_output=True, check=True).stdout
    return out.decode("utf-8", "replace").splitlines()[0].split()[-1]


def latex_to_ast(exe: Path, text: str) -> tuple[dict, list[str]]:
    proc = subprocess.run(
        [str(exe), "-f", READER, "-t", "json"],
        input=text.encode("utf-8"), capture_output=True,
    )
    warnings = [ln for ln in proc.stderr.decode("utf-8", "replace").splitlines() if ln.strip()]
    if proc.returncode != 0:
        raise PandocError("Το Pandoc απέτυχε: " + " | ".join(warnings[:5]))
    return json.loads(proc.stdout.decode("utf-8")), warnings
