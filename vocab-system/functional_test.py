from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def run(script: str) -> None:
    cmd = [sys.executable, script]
    print(f"[functional] running: {script}")
    subprocess.run(cmd, check=True)


def main() -> None:
    base = Path(__file__).resolve().parent
    scripts = [
        "test_step2_word_analysis.py",
        "test_step3_review_engine.py",
        "test_step4_sentence_checker.py",
        "test_step5_passage_generator.py",
    ]
    for s in scripts:
        run(str(base / s))
    print("[functional] all step tests passed")


if __name__ == "__main__":
    main()
