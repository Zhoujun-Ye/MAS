"""Inspect dataclawbench task coverage without exporting questions or gold."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.common.catalog import main

if __name__ == "__main__":
    raise SystemExit(main(benchmark="dataclawbench"))
