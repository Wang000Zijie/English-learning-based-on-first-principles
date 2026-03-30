from __future__ import annotations

from pathlib import Path

from core.api_client import APIClient
from data.db_manager import DBManager


def main() -> None:
    base = Path(__file__).resolve().parent
    cfg = base / "config.yaml"
    db_file = base / "data" / "foundation_test.db"

    if db_file.exists():
        db_file.unlink()

    print("[foundation] 初始化数据库")
    db = DBManager(str(db_file))

    print("[foundation] 校验数据库结构")
    with db._connect() as conn:  # internal check for foundation stage
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            ).fetchall()
        }
    required = {"words", "review_records", "sentences", "passages", "word_stats"}
    missing = required - tables
    if missing:
        raise RuntimeError(f"数据库缺少对象: {sorted(missing)}")

    print("[foundation] 测试 API 连通")
    api = APIClient(str(cfg))
    text = api.ask("只回复 OK")
    if not text.strip():
        raise RuntimeError("API 返回为空")
    print("API 返回:", text[:80])

    print("[foundation] 通过")


if __name__ == "__main__":
    main()
