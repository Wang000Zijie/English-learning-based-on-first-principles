from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


class DBManager:
    def __init__(self, db_path: str = "data/vocab.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT NOT NULL UNIQUE,
                    definition TEXT,
                    tone TEXT,
                    nuance TEXT,
                    scenario TEXT,
                    collocations TEXT,
                    memory_hook TEXT,
                    example_sentence TEXT,
                    common_mistake TEXT,
                    source_context TEXT,
                    word_bank TEXT DEFAULT 'new',
                    level TEXT DEFAULT 'new',
                    passage_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS review_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word_id INTEGER NOT NULL,
                    review_date DATE NOT NULL,
                    result TEXT NOT NULL,
                    next_review_date DATE,
                    interval_index INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (word_id) REFERENCES words(id)
                );

                CREATE TABLE IF NOT EXISTS sentences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word_id INTEGER NOT NULL,
                    original_sentence TEXT NOT NULL,
                    corrected_sentence TEXT,
                    word_usage_analysis TEXT,
                    more_natural_version TEXT,
                    grammar_issues TEXT,
                    encouragement TEXT,
                    is_correct INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (word_id) REFERENCES words(id)
                );

                CREATE TABLE IF NOT EXISTS passages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT DEFAULT '',
                    content TEXT NOT NULL,
                    translation TEXT,
                    vocabulary_notes TEXT,
                    word_ids TEXT NOT NULL,
                    level_mix TEXT,
                    story_direction TEXT DEFAULT 'freeform',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS storylines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    word_ids TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    direction_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS storyline_chapters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    storyline_id INTEGER NOT NULL,
                    chapter_number INTEGER NOT NULL,
                    passage_id INTEGER NOT NULL,
                    mastery_snapshot TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (storyline_id) REFERENCES storylines(id),
                    FOREIGN KEY (passage_id) REFERENCES passages(id)
                );

                CREATE TABLE IF NOT EXISTS news_articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    source_url TEXT,
                    content TEXT NOT NULL,
                    summary TEXT,
                    related_word_ids TEXT,
                    provider TEXT,
                    published_date TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            self._migrate_legacy_schema(conn)
            self._recreate_word_stats_view(conn)

    def _migrate_legacy_schema(self, conn: sqlite3.Connection) -> None:
        self._migrate_review_records(conn)

        words_cols = {row["name"] for row in conn.execute("PRAGMA table_info(words)").fetchall()}
        words_additions = [
            ("nuance", "TEXT"),
            ("collocations", "TEXT"),
            ("example_sentence", "TEXT"),
            ("common_mistake", "TEXT"),
            ("word_bank", "TEXT DEFAULT 'new'"),
            ("level", "TEXT DEFAULT 'new'"),
            ("passage_count", "INTEGER DEFAULT 0"),
        ]
        for col, col_type in words_additions:
            if col not in words_cols:
                conn.execute(f"ALTER TABLE words ADD COLUMN {col} {col_type}")

        review_cols = {row["name"] for row in conn.execute("PRAGMA table_info(review_records)").fetchall()}
        if "interval_index" not in review_cols:
            conn.execute("ALTER TABLE review_records ADD COLUMN interval_index INTEGER NOT NULL DEFAULT 0")

        sent_cols = {row["name"] for row in conn.execute("PRAGMA table_info(sentences)").fetchall()}
        sent_additions = [
            ("word_usage_analysis", "TEXT"),
            ("more_natural_version", "TEXT"),
            ("grammar_issues", "TEXT"),
            ("encouragement", "TEXT"),
            ("is_correct", "INTEGER"),
        ]
        for col, col_type in sent_additions:
            if col not in sent_cols:
                conn.execute(f"ALTER TABLE sentences ADD COLUMN {col} {col_type}")

        passage_cols = {row["name"] for row in conn.execute("PRAGMA table_info(passages)").fetchall()}
        if "title" not in passage_cols:
            conn.execute("ALTER TABLE passages ADD COLUMN title TEXT DEFAULT ''")
        if "story_direction" not in passage_cols:
            conn.execute("ALTER TABLE passages ADD COLUMN story_direction TEXT DEFAULT 'freeform'")

    def _migrate_review_records(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='review_records'"
        ).fetchone()
        if not row or not row[0]:
            return
        ddl = str(row[0]).lower()
        need_rebuild = (
            "current_interval_index" in ddl
            or "interval_index integer not null default 0" not in ddl
        )
        if not need_rebuild:
            return

        cols = {r["name"] for r in conn.execute("PRAGMA table_info(review_records)").fetchall()}
        has_interval_index = "interval_index" in cols
        has_current_interval_index = "current_interval_index" in cols

        interval_expr_parts: List[str] = []
        if has_interval_index:
            interval_expr_parts.append("interval_index")
        if has_current_interval_index:
            interval_expr_parts.append("current_interval_index")
        interval_expr = "COALESCE(" + ", ".join(interval_expr_parts + ["0"]) + ")"

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS review_records_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word_id INTEGER NOT NULL,
                review_date DATE NOT NULL,
                result TEXT NOT NULL,
                next_review_date DATE,
                interval_index INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (word_id) REFERENCES words(id)
            )
            """
        )
        conn.execute(
            f"""
            INSERT INTO review_records_new (id, word_id, review_date, result, next_review_date, interval_index)
            SELECT
                id,
                word_id,
                review_date,
                CASE
                    WHEN LOWER(CAST(result AS TEXT)) IN ('1', 'remembered', 'true', 'yes') THEN 'remembered'
                    ELSE 'forgotten'
                END,
                next_review_date,
                {interval_expr}
            FROM review_records
            """
        )
        conn.execute("DROP VIEW IF EXISTS word_stats")
        conn.execute("DROP TABLE review_records")
        conn.execute("ALTER TABLE review_records_new RENAME TO review_records")

    def _recreate_word_stats_view(self, conn: sqlite3.Connection) -> None:
        conn.execute("DROP VIEW IF EXISTS word_stats")
        conn.execute(
            """
            CREATE VIEW word_stats AS
            SELECT
                w.id,
                w.word,
                w.level,
                w.created_at,
                COUNT(DISTINCT r.id) AS total_reviews,
                COALESCE(SUM(CASE WHEN r.result = 'remembered' THEN 1 ELSE 0 END), 0) AS remembered_count,
                COALESCE(SUM(CASE WHEN r.result = 'forgotten' THEN 1 ELSE 0 END), 0) AS forgotten_count,
                MAX(r.review_date) AS last_review_date,
                MIN(CASE WHEN r.next_review_date >= DATE('now') THEN r.next_review_date END) AS next_review_date,
                COUNT(DISTINCT s.id) AS total_sentences
            FROM words w
            LEFT JOIN review_records r ON w.id = r.word_id
            LEFT JOIN sentences s ON w.id = s.word_id
            GROUP BY w.id
            """
        )

    def upsert_word(self, item: Dict[str, Any]) -> int:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO words (
                    word, definition, tone, nuance, scenario, collocations, memory_hook,
                    example_sentence, common_mistake, source_context, word_bank, level, passage_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                ON CONFLICT(word) DO UPDATE SET
                    definition=excluded.definition,
                    tone=excluded.tone,
                    nuance=excluded.nuance,
                    scenario=excluded.scenario,
                    collocations=excluded.collocations,
                    memory_hook=excluded.memory_hook,
                    example_sentence=excluded.example_sentence,
                    common_mistake=excluded.common_mistake,
                    source_context=excluded.source_context,
                    word_bank=excluded.word_bank
                """,
                (
                    item["word"].lower(),
                    item.get("definition"),
                    item.get("tone"),
                    item.get("nuance"),
                    item.get("scenario"),
                    json.dumps(item.get("collocations", []), ensure_ascii=False),
                    item.get("memory_hook"),
                    item.get("example_sentence"),
                    item.get("common_mistake"),
                    item.get("source_context"),
                    item.get("word_bank", "new"),
                    item.get("level", "new"),
                    int(item.get("passage_count", 0) or 0),
                    item.get("created_at"),
                ),
            )
            row = conn.execute("SELECT id FROM words WHERE word = ?", (item["word"].lower(),)).fetchone()
            if not row:
                raise RuntimeError("Failed to load inserted word id")
            return int(row["id"])

    def get_word_by_id(self, word_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM words WHERE id = ?", (word_id,)).fetchone()
            return dict(row) if row else None

    def get_word_by_text(self, word: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM words WHERE word = ?", (word.lower(),)).fetchone()
            return dict(row) if row else None

    def get_word_info(self, word: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT word, definition, tone, memory_hook, scenario, source_context, level FROM words WHERE LOWER(word)=LOWER(?)",
                (word,),
            ).fetchone()
            return dict(row) if row else None

    def list_words(self, word_bank: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            if word_bank and word_bank.strip():
                rows = conn.execute(
                    "SELECT * FROM words WHERE word_bank = ? ORDER BY created_at DESC",
                    (word_bank.strip(),),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM words ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    def list_words_advanced(
        self,
        query: str = "",
        levels: Optional[List[str]] = None,
        sort_by: str = "created_at_desc",
        word_bank: Optional[str] = None,
        sort_keys: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        where_clauses: List[str] = []
        params: List[Any] = []
        if query.strip():
            where_clauses.append("(w.word LIKE ? OR w.definition LIKE ?)")
            like = f"%{query.strip()}%"
            params.extend([like, like])
        if levels:
            placeholders = ",".join("?" for _ in levels)
            where_clauses.append(f"w.level IN ({placeholders})")
            params.extend(levels)
        if word_bank and word_bank.strip():
            where_clauses.append("w.word_bank = ?")
            params.append(word_bank.strip())

        order_map = {
            "created_at_desc": "w.created_at DESC",
            "created_at_asc": "w.created_at ASC",
            "usage_count_desc": "COALESCE(w.passage_count, 0) DESC",
            "usage_count_asc": "COALESCE(w.passage_count, 0) ASC",
            "reviews_desc": "total_reviews DESC",
            "reviews_asc": "total_reviews ASC",
            "accuracy_desc": "pass_rate DESC",
            "accuracy_asc": "pass_rate ASC",
            "alphabet_asc": "w.word ASC",
            "alphabet_desc": "w.word DESC",
            # Backward compatibility
            "created_at": "w.created_at DESC",
            "reviews": "total_reviews DESC",
            "mastery": "pass_rate DESC",
            "alphabet": "w.word ASC",
        }

        normalized_keys: List[str] = []
        if sort_keys:
            normalized_keys = [str(k).strip() for k in sort_keys if str(k).strip()]
        elif sort_by and "+" in str(sort_by):
            normalized_keys = [seg.strip() for seg in str(sort_by).split("+") if seg.strip()]
        elif sort_by:
            normalized_keys = [str(sort_by).strip()]

        order_parts: List[str] = []
        for key in normalized_keys:
            clause = order_map.get(key)
            if clause and clause not in order_parts:
                order_parts.append(clause)
        if "w.created_at DESC" not in order_parts:
            order_parts.append("w.created_at DESC")
        order_by = ", ".join(order_parts)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        sql = f"""
            SELECT
                w.*,
                COUNT(r.id) AS total_reviews,
                COALESCE(SUM(CASE WHEN r.result='remembered' THEN 1 ELSE 0 END), 0) AS remembered_count,
                CASE WHEN COUNT(r.id)=0 THEN 0
                     ELSE ROUND(100.0 * SUM(CASE WHEN r.result='remembered' THEN 1 ELSE 0 END) / COUNT(r.id), 2)
                END AS pass_rate,
                MAX(r.next_review_date) AS next_review_date
            FROM words w
            LEFT JOIN review_records r ON r.word_id = w.id
            {where_sql}
            GROUP BY w.id
            ORDER BY {order_by}
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def delete_words(self, word_ids: List[int]) -> None:
        if not word_ids:
            return
        unique_ids = sorted({int(wid) for wid in word_ids if int(wid) > 0})
        if not unique_ids:
            return
        placeholders = ",".join("?" for _ in unique_ids)
        with self._connect() as conn:
            conn.execute(f"DELETE FROM review_records WHERE word_id IN ({placeholders})", unique_ids)
            conn.execute(f"DELETE FROM sentences WHERE word_id IN ({placeholders})", unique_ids)
            conn.execute(f"DELETE FROM words WHERE id IN ({placeholders})", unique_ids)

    def update_word_fields(self, word_id: int, fields: Dict[str, Any]) -> None:
        wid = int(word_id)
        if wid <= 0:
            raise ValueError("word_id 非法")

        allowed = {
            "word",
            "definition",
            "tone",
            "nuance",
            "scenario",
            "collocations",
            "memory_hook",
            "example_sentence",
            "common_mistake",
            "source_context",
            "word_bank",
            "level",
            "passage_count",
        }
        updates: List[str] = []
        params: List[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "word" and value is not None:
                value = str(value).strip().lower()
            if key == "collocations" and isinstance(value, list):
                value = json.dumps(value, ensure_ascii=False)
            updates.append(f"{key} = ?")
            params.append(value)

        if not updates:
            return

        params.append(wid)
        with self._connect() as conn:
            conn.execute(f"UPDATE words SET {', '.join(updates)} WHERE id = ?", params)

    def get_words_by_levels(self, levels: List[str], word_bank: Optional[str] = None) -> List[Dict[str, Any]]:
        if not levels:
            return []
        placeholders = ",".join("?" for _ in levels)
        query = f"SELECT * FROM words WHERE level IN ({placeholders}) "
        params: List[Any] = list(levels)
        if word_bank and word_bank.strip():
            query += "AND word_bank = ? "
            params.append(word_bank.strip())
        query += "AND definition IS NOT NULL AND TRIM(definition) <> ''"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def update_word_level(self, word_id: int, level: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE words SET level = ? WHERE id = ?", (level, word_id))

    def get_word_stats(self, word_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            if word_id is None:
                rows = conn.execute("SELECT * FROM word_stats").fetchall()
            else:
                rows = conn.execute("SELECT * FROM word_stats WHERE id = ?", (word_id,)).fetchall()
            return [dict(r) for r in rows]

    def add_review_record(
        self,
        word_id: int,
        review_date: str,
        result: str,
        next_review_date: str,
        interval_index: int,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO review_records (
                    word_id, review_date, result, next_review_date, interval_index
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (word_id, review_date, result, next_review_date, interval_index),
            )

    def get_latest_review_record(self, word_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM review_records
                WHERE word_id = ?
                ORDER BY review_date DESC, id DESC
                LIMIT 1
                """,
                (word_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_due_words(self, on_date: str) -> List[Dict[str, Any]]:
        query = """
            SELECT w.*
            FROM words w
            LEFT JOIN (
                SELECT rr.word_id, rr.next_review_date
                FROM review_records rr
                INNER JOIN (
                    SELECT word_id, MAX(id) AS max_id
                    FROM review_records
                    GROUP BY word_id
                ) latest ON latest.max_id = rr.id
            ) lr ON lr.word_id = w.id
            WHERE w.word_bank = 'new' AND (lr.next_review_date IS NULL OR lr.next_review_date <= ?)
            ORDER BY w.created_at ASC
        """
        with self._connect() as conn:
            rows = conn.execute(query, (on_date,)).fetchall()
            return [dict(r) for r in rows]

    def get_recent_reviews(self, word_id: int, limit: int = 3) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM review_records
                WHERE word_id = ?
                ORDER BY review_date DESC, id DESC
                LIMIT ?
                """,
                (word_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def add_sentence_record(
        self,
        word_id: int,
        original_sentence: str,
        corrected_sentence: str,
        word_usage_analysis: str,
        more_natural_version: str,
        grammar_issues: List[Dict[str, Any]],
        encouragement: str,
        is_correct: bool,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sentences (
                    word_id, original_sentence, corrected_sentence, word_usage_analysis,
                    more_natural_version, grammar_issues, encouragement, is_correct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    word_id,
                    original_sentence,
                    corrected_sentence,
                    word_usage_analysis,
                    more_natural_version,
                    json.dumps(grammar_issues, ensure_ascii=False),
                    encouragement,
                    1 if is_correct else 0,
                ),
            )

    def add_passage_record(
        self,
        title: str,
        content: str,
        translation: str,
        vocabulary_notes: List[Dict[str, Any]],
        word_ids: List[int],
        level_mix: str,
        story_direction: str,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO passages (title, content, translation, vocabulary_notes, word_ids, level_mix, story_direction)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (title or "").strip(),
                    content,
                    translation,
                    json.dumps(vocabulary_notes, ensure_ascii=False),
                    json.dumps(word_ids, ensure_ascii=False),
                    level_mix,
                    story_direction,
                ),
            )
            return int(cur.lastrowid)

    def increment_passage_count(self, word_ids: List[int]) -> None:
        if not word_ids:
            return
        with self._connect() as conn:
            conn.executemany("UPDATE words SET passage_count = COALESCE(passage_count, 0) + 1 WHERE id = ?", [(wid,) for wid in word_ids])

    def get_latest_passage(self) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM passages ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
            return dict(row) if row else None

    def list_passages(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM passages ORDER BY created_at DESC, id DESC"
        params: tuple[Any, ...] = ()
        if isinstance(limit, int) and limit > 0:
            sql += " LIMIT ?"
            params = (limit,)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def get_passage_by_id(self, passage_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM passages WHERE id = ?", (passage_id,)).fetchone()
            return dict(row) if row else None

    def delete_passage(self, passage_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM passages WHERE id = ?", (passage_id,))

    def delete_passage_with_relations(self, passage_id: int) -> None:
        pid = int(passage_id)
        if pid <= 0:
            return
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT storyline_id FROM storyline_chapters WHERE passage_id = ?",
                (pid,),
            ).fetchall()
            storyline_ids = [int(r["storyline_id"]) for r in rows]
            conn.execute("DELETE FROM storyline_chapters WHERE passage_id = ?", (pid,))
            conn.execute("DELETE FROM passages WHERE id = ?", (pid,))
            for sid in storyline_ids:
                left = conn.execute(
                    "SELECT COUNT(*) AS c FROM storyline_chapters WHERE storyline_id = ?",
                    (sid,),
                ).fetchone()
                if int(left["c"]) == 0:
                    conn.execute("DELETE FROM storylines WHERE id = ?", (sid,))

    def create_storyline(self, name: str, word_ids: List[int], direction_id: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO storylines (name, word_ids, status, direction_id) VALUES (?, ?, 'active', ?)",
                (name, json.dumps(word_ids, ensure_ascii=False), direction_id),
            )
            return int(cur.lastrowid)

    def get_active_storyline(self, direction_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM storylines WHERE status='active' AND direction_id=? ORDER BY id DESC LIMIT 1",
                (direction_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_storyline_by_id(self, storyline_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM storylines WHERE id = ?", (storyline_id,)).fetchone()
            return dict(row) if row else None

    def add_storyline_chapter(
        self,
        storyline_id: int,
        chapter_number: int,
        passage_id: int,
        mastery_snapshot: Dict[str, Any],
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO storyline_chapters (storyline_id, chapter_number, passage_id, mastery_snapshot) VALUES (?, ?, ?, ?)",
                (storyline_id, chapter_number, passage_id, json.dumps(mastery_snapshot, ensure_ascii=False)),
            )
            return int(cur.lastrowid)

    def get_last_storyline_chapter(self, storyline_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM storyline_chapters WHERE storyline_id=? ORDER BY chapter_number DESC, id DESC LIMIT 1",
                (storyline_id,),
            ).fetchone()
            return dict(row) if row else None

    def delete_storyline_last_chapter(self, storyline_id: int) -> Optional[int]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM storyline_chapters WHERE storyline_id=? ORDER BY chapter_number DESC, id DESC LIMIT 1",
                (storyline_id,),
            ).fetchone()
            if not row:
                return None
            passage_id = int(row["passage_id"])
            conn.execute("DELETE FROM storyline_chapters WHERE id = ?", (int(row["id"]),))
            conn.execute("DELETE FROM passages WHERE id = ?", (passage_id,))
            return passage_id

    def complete_storyline(self, storyline_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE storylines SET status='completed', completed_at=CURRENT_TIMESTAMP WHERE id=?",
                (storyline_id,),
            )

    def save_news_article(
        self,
        title: str,
        source_url: str,
        content: str,
        summary: str,
        related_word_ids: List[int],
        provider: str,
        published_date: str,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO news_articles
                (title, source_url, content, summary, related_word_ids, provider, published_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    source_url,
                    content,
                    summary,
                    json.dumps(related_word_ids, ensure_ascii=False),
                    provider,
                    published_date,
                ),
            )
            return int(cur.lastrowid)

    def get_level_counts(self, word_bank: Optional[str] = None) -> Dict[str, int]:
        with self._connect() as conn:
            if word_bank and word_bank.strip():
                rows = conn.execute(
                    "SELECT level, COUNT(*) AS c FROM words WHERE word_bank = ? GROUP BY level",
                    (word_bank.strip(),),
                ).fetchall()
            else:
                rows = conn.execute("SELECT level, COUNT(*) AS c FROM words GROUP BY level").fetchall()
            result = {"new": 0, "learning": 0, "familiar": 0, "mastered": 0}
            for row in rows:
                result[row["level"]] = int(row["c"])
            return result

    def get_weak_words_recent(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, word FROM words").fetchall()

        weak: List[Dict[str, Any]] = []
        for row in rows:
            recent = self.get_recent_reviews(int(row["id"]), limit=3)
            forgotten = sum(1 for r in recent if r.get("result") == "forgotten")
            if len(recent) == 3 and forgotten >= 2:
                weak.append({"id": int(row["id"]), "word": row["word"]})
        return weak
