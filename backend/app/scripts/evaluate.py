"""Run CraftFlow's isolated offline workflow evaluation from the repository root."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.evaluation.runner import main  # noqa: E402

if __name__ == "__main__":
    main()
