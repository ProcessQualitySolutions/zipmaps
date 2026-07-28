"""Add the bundled zipmap library to sys.path. Imported by every script."""

import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "src"))
