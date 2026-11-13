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
            CREATE TABLE IF NOT EXISTS image_inbox (
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                update_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                display_name TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                played_on TEXT NOT NULL,
                image BLOB,
                status TEXT NOT NULL,
                detected_game TEXT,
                last_error TEXT,
                scan_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(chat_id, message_id)
            );
            CREATE INDEX IF NOT EXISTS idx_image_inbox_unresolved
                ON image_inbox(played_on, status);
            CREATE TABLE IF NOT EXISTS manual_members (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                display_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(chat_id, user_id),
                UNIQUE(chat_id, username COLLATE NOCASE)
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

    def stage_image(
        self,
        *,
        chat_id: int,
        message_id: int,
        update_id: int,
        user_id: int,
        username: str | None,
        display_name: str,
        sent_at: datetime,
        played_on: date,
        image: bytes,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """
            INSERT INTO image_inbox(
                chat_id, message_id, update_id, user_id, username, display_name,
                sent_at, played_on, image, status, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,'pending',?)
            ON CONFLICT(chat_id, message_id) DO NOTHING
            """,
            (
                chat_id, message_id, update_id, user_id, username, display_name,
                sent_at.isoformat(), played_on.isoformat(), image, now,
            ),
        )
        self.conn.commit()

    def mark_image_result(
        self,
        chat_id: int,
        message_id: int,
        status: str,
        *,
        detected_game: str | None = None,
        last_error: str | None = None,
        clear_image: bool = False,
    ) -> None:
        self.conn.execute(
            """
            UPDATE image_inbox
            SET status=?, detected_game=?, last_error=?,
                scan_count=scan_count+1,
                image=CASE WHEN ? THEN NULL ELSE image END,
                updated_at=?
            WHERE chat_id=? AND message_id=?
            """,
            (
                status, detected_game, last_error, int(clear_image),
                datetime.now().isoformat(timespec="seconds"), chat_id, message_id,
            ),
        )
        self.conn.commit()

    def unresolved_images(self, played_on: date) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT * FROM image_inbox
                WHERE played_on=?
                  AND status IN ('pending', 'rejected', 'error')
                  AND image IS NOT NULL
                ORDER BY update_id
                """,
                (played_on.isoformat(),),
            )
        )

    def merge_manual_member(
        self,
        chat_id: int,
        user_id: int,
        username: str | None,
        display_name: str,
    ) -> bool:
        if not username:
            return False
        manual = self.conn.execute(
            """
            SELECT * FROM manual_members
            WHERE chat_id=? AND username=? COLLATE NOCASE
            """,
            (chat_id, username.lstrip("@")),
        ).fetchone()
        if not manual or manual["user_id"] == user_id:
            return False
        temporary_id = manual["user_id"]
        rows = self.conn.execute(
            "SELECT * FROM submissions WHERE chat_id=? AND user_id=?",
            (chat_id, temporary_id),
        ).fetchall()
        for row in rows:
            conflict = self.conn.execute(
                """
                SELECT id FROM submissions
                WHERE chat_id=? AND user_id=? AND game=? AND played_on=?
                """,
                (chat_id, user_id, row["game"], row["played_on"]),
            ).fetchone()
            if conflict:
                self.conn.execute("DELETE FROM submissions WHERE id=?", (row["id"],))
            else:
                self.conn.execute(
                    """
                    UPDATE submissions
                    SET user_id=?, username=?, display_name=?
                    WHERE id=?
                    """,
                    (user_id, username, display_name, row["id"]),
                )
        self.conn.execute(
            "DELETE FROM manual_members WHERE chat_id=? AND user_id=?",
            (chat_id, temporary_id),
        )
        self.conn.commit()
        return True

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

