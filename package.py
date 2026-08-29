"""Package the zipmaps skill into a distributable .skill archive.

A .skill file is a zip archive with every skill file nested under a single
top-level ``zipmaps/`` folder, so unzipping yields a ready-to-use skill
directory with SKILL.md at its root.

Usage:
    python package.py              # writes ./zipmaps.skill
    python package.py -o out.skill
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SKILL_NAME = "zipmaps"
DEFAULT_OUTPUT = REPO_ROOT / f"{SKILL_NAME}.skill"

EXCLUDE_RELPATHS = {
    "package.py",
    "idea.md",
}
EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".idea", ".vscode", "dist", "build", "node_modules", ".claude",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".skill", ".zipmap", ".log"}
EXCLUDE_BASENAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
# generated base64-embedding HTML (render/review/view output) never ships —
# it is a per-map artifact, and packaged copies bait agents into reading b64
GENERATED_HTML_SUFFIXES = ("_overlay.html", "_review.html", "_viewer.html")


def _excluded(rel: Path) -> bool:
    if rel.as_posix() in EXCLUDE_RELPATHS:
        return True
    if any(part in EXCLUDE_DIRS or part.endswith(".egg-info") for part in rel.parts):
        return True
    if rel.suffix in EXCLUDE_SUFFIXES:
        return True
    if rel.name in EXCLUDE_BASENAMES:
        return True
    if rel.name.endswith(GENERATED_HTML_SUFFIXES):
        return True
    if rel.name.startswith("__temp"):
        return True
    return False


def collect_files(root: Path, output: Path) -> list[Path]:
    rels = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.resolve() == output.resolve():
            continue
        rel = path.relative_to(root)
        if _excluded(rel):
            continue
        rels.append(rel)
    return rels


def build(output: Path) -> None:
    if not (REPO_ROOT / "SKILL.md").is_file():
        raise SystemExit("SKILL.md not found at repo root; refusing to package.")
    rels = collect_files(REPO_ROOT, output)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in rels:
            zf.write(REPO_ROOT / rel, f"{SKILL_NAME}/{rel.as_posix()}")
    size_kib = output.stat().st_size / 1024
    top_dirs = sorted({rel.parts[0] for rel in rels if len(rel.parts) > 1})
    print(f"Wrote {output} ({len(rels)} files, {size_kib:.1f} KiB)")
    print(f"Archive root: {SKILL_NAME}/")
    print(f"Top-level dirs: {', '.join(top_dirs)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    build(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
