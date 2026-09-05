from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "model"
for path in (ROOT, MODEL):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
