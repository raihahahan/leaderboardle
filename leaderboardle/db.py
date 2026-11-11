from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class Submission:
    chat_id: int
    message_id: int
    update_id: int
    user_id: int
    username: str | None
    display_name: str
    game: str
    played_on: date
    attempts: int
    max_attempts: int | None
    success: bool
    raw_text: str


class Database:
    def __init__(self, path: Path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                update_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                display_name TEXT NOT NULL,
                game TEXT NOT NULL,
                played_on TEXT NOT NULL,
                attempts INTEGER NOT NULL,
                max_attempts INTEGER,
                success INTEGER NOT NULL,
                raw_text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(chat_id, message_id),
                UNIQUE(chat_id, user_id, game, played_on)
            );
            CREATE TABLE IF NOT EXISTS checkpoints (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_submissions_day
                ON submissions(chat_id, played_on, game);
            CREATE TABLE IF NOT EXISTS game_snapshots (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                game TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                played INTEGER,
                current_streak INTEGER,
                distribution TEXT NOT NULL,
                PRIMARY KEY(chat_id, user_id, game)
            );
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def checkpoint(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM checkpoints WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_checkpoint(self, key: str, value: str | int) -> None:
        self.conn.execute(
            "INSERT INTO checkpoints(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        self.conn.commit()

    def remember_chat(self, chat_id: int, title: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            "INSERT INTO chats(chat_id, title, first_seen_at, last_seen_at) VALUES(?,?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, last_seen_at=excluded.last_seen_at",
            (chat_id, title, now, now),
        )
        self.conn.commit()

    def chats(self) -> list[int]:
        return [row["chat_id"] for row in self.conn.execute("SELECT chat_id FROM chats")]

    def save_submission(self, item: Submission) -> bool:
        before = self.conn.total_changes
        self.conn.execute(
            """
            INSERT INTO submissions(
                chat_id, message_id, update_id, user_id, username, display_name,
                game, played_on, attempts, max_attempts, success, raw_text, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(chat_id, user_id, game, played_on) DO UPDATE SET
                message_id=excluded.message_id,
                update_id=excluded.update_id,
                username=excluded.username,
                display_name=excluded.display_name,
                attempts=excluded.attempts,
                max_attempts=excluded.max_attempts,
                success=excluded.success,
                raw_text=excluded.raw_text,
                created_at=excluded.created_at
            WHERE excluded.message_id > submissions.message_id
            """,
            (
                item.chat_id, item.message_id, item.update_id, item.user_id,
                item.username, item.display_name, item.game, item.played_on.isoformat(),
                item.attempts, item.max_attempts, int(item.success), item.raw_text,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        self.conn.commit()
        return self.conn.total_changes > before

    def leaderboard(self, chat_id: int, played_on: date) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT * FROM submissions
                WHERE chat_id = ? AND played_on = ?
                ORDER BY game COLLATE NOCASE,
                         success DESC,
                         attempts ASC,
                         display_name COLLATE NOCASE
                """,
                (chat_id, played_on.isoformat()),
            )
        )

    def participation_streak(
        self, chat_id: int, user_id: int, game: str, through_day: date
    ) -> int:
        rows = self.conn.execute(
            """
            SELECT played_on FROM submissions
            WHERE chat_id = ? AND user_id = ? AND game = ? AND played_on <= ?
            ORDER BY played_on DESC
            """,
            (chat_id, user_id, game, through_day.isoformat()),
        ).fetchall()
        expected = through_day
        streak = 0
        for row in rows:
            played_on = date.fromisoformat(row["played_on"])
            if played_on != expected:
                break
            streak += 1
            expected -= timedelta(days=1)
        return streak

    def reset_day(self, chat_id: int, played_on: date) -> int:
        cursor = self.conn.execute(
            "DELETE FROM submissions WHERE chat_id = ? AND played_on = ?",
            (chat_id, played_on.isoformat()),
        )
        self.conn.commit()
        return cursor.rowcount

    def reset_all(self, chat_id: int) -> int:
        cursor = self.conn.execute("DELETE FROM submissions WHERE chat_id = ?", (chat_id,))
        self.conn.commit()
        return cursor.rowcount

    def game_snapshot(self, chat_id: int, user_id: int, game: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM game_snapshots WHERE chat_id=? AND user_id=? AND game=?",
            (chat_id, user_id, game),
        ).fetchone()

    def save_game_snapshot(
        self,
        chat_id: int,
        user_id: int,
        game: str,
        played: int | None,
        current_streak: int | None,
        distribution: tuple[int, ...],
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO game_snapshots(
                chat_id, user_id, game, captured_at, played, current_streak, distribution
            ) VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(chat_id, user_id, game) DO UPDATE SET
                captured_at=excluded.captured_at,
                played=excluded.played,
                current_streak=excluded.current_streak,
                distribution=excluded.distribution
            """,
            (
                chat_id, user_id, game, datetime.now().isoformat(timespec="seconds"),
                played, current_streak, json.dumps(distribution),
            ),
        )
        self.conn.commit()

    def pending_summary_days(self, chat_id: int, yesterday: date) -> list[date]:
        key = f"last_summary:{chat_id}"
        raw = self.checkpoint(key)
        if raw:
            start = date.fromisoformat(raw) + timedelta(days=1)
        else:
            row = self.conn.execute(
                "SELECT MIN(played_on) AS first_day FROM submissions WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            start = date.fromisoformat(row["first_day"]) if row and row["first_day"] else yesterday
        if start > yesterday:
            return []
        return [start + timedelta(days=i) for i in range((yesterday - start).days + 1)]

