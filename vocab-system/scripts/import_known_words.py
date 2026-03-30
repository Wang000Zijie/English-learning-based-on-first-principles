from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.db_manager import DBManager


HEAD_RE = re.compile(r"^[A-Za-z][A-Za-z'\-]*$")


def extract_words(line: str) -> List[str]:
    raw = line.strip()
    if not raw:
        return []
    token = raw.split()[0].strip("\t \r\n,;:()[]{}<>\"'。；，")
    if not token:
        return []

    # Handle entries like "analyse/ze".
    parts = re.split(r"[\/]", token)
    out: List[str] = []
    for p in parts:
        word = p.strip("\t \r\n,;:()[]{}<>\"'.")
        if HEAD_RE.match(word):
            out.append(word.lower())
    return out


def extract_definition(line: str, word: str) -> str:
    idx = line.lower().find(word.lower())
    if idx == -1:
        return ""
    tail = line[idx + len(word) :].strip()
    return tail[:300]


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python scripts/import_known_words.py <word_file> <db_path>")
        return 1

    word_file = Path(sys.argv[1]).resolve()
    db_path = Path(sys.argv[2]).resolve()
    if not word_file.exists():
        print(f"Word file not found: {word_file}")
        return 2

    db = DBManager(str(db_path))

    seen = set()
    total = 0
    for line in word_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        words = extract_words(line)
        if not words:
            continue
        for word in words:
            if word in seen:
                continue
            seen.add(word)
            definition = extract_definition(line, word)
            db.upsert_word(
                {
                    "word": word,
                    "definition": definition,
                    "tone": "",
                    "scenario": "",
                    "memory_hook": "",
                    "source_context": "高中词库导入",
                    "word_bank": "familiar",
                    "level": "familiar",
                }
            )
            total += 1

    print(f"Imported familiar words: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
