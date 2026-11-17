"""Tests of sentier-diagnostics. Standard library only: `python3 -m unittest discover -s tests -t .`

Where the package is not installed, the source folder is put on the path, so that a fresh
clone runs the tests without installing anything.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    import sentier_diagnostics  # noqa: F401
except ImportError:
    sys.path.insert(0, str(ROOT / "src"))
