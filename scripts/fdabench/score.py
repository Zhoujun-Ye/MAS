"""Score FDABench choices offline; report judges require explicit authorization."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.common.score import main

if __name__ == "__main__":
    raise SystemExit(main(benchmark="fdabench"))
