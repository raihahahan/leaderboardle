#!/usr/bin/env python3
"""Curses TUI for editing the local Leaderboardle database."""

from __future__ import annotations

import curses
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "leaderboard.sqlite3"
SGT = ZoneInfo("Asia/Singapore")
GAMES = ("Wordle", "Minecraftle", "Poople", "Krillion")
MAX_ATTEMPTS = {"Wordle": 6, "Minecraftle": 10}


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS manual_members (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            display_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(chat_id, user_id),
            UNIQUE(chat_id, username COLLATE NOCASE)
        )
        """
    )
    connection.commit()
    return connection


def chats(connection):
    return list(connection.execute("SELECT chat_id, title FROM chats ORDER BY title"))


def results(connection, chat_id, day):
    return list(
        connection.execute(
            """
            SELECT * FROM submissions
            WHERE chat_id=? AND played_on=?
            ORDER BY game, display_name COLLATE NOCASE
            """,
            (chat_id, day.isoformat()),
        )
    )


def known_members(connection, chat_id):
    return list(
        connection.execute(
            """
            SELECT user_id, username, display_name
            FROM (
                SELECT user_id, username, display_name FROM submissions WHERE chat_id=?
                UNION ALL
                SELECT user_id, username, display_name FROM manual_members WHERE chat_id=?
            )
            GROUP BY user_id
            ORDER BY display_name COLLATE NOCASE
            """,
            (chat_id, chat_id),
        )
    )


def member_label(row):
    return f"@{row['username']}" if row["username"] else row["display_name"]


def parse_score(game, value):
    value = value.strip().upper()
    maximum = MAX_ATTEMPTS.get(game)
    if value == "X" and maximum:
        return maximum + 1, maximum, False
    if not value.isdigit() or int(value) < 1:
        raise ValueError("Enter a positive number" + (" or X" if maximum else "") + ".")
    score = int(value)
    if maximum and score > maximum:
        raise ValueError(f"{game} must be 1-{maximum} or X.")
    return score, maximum, True


def add_manual_member(connection, chat_id, username, display_name):
    username = username.strip().lstrip("@")
    if not username:
        raise ValueError("Username is required.")
    existing = connection.execute(
        """
        SELECT user_id, username, display_name FROM (
            SELECT user_id, username, display_name FROM submissions WHERE chat_id=?
            UNION ALL
            SELECT user_id, username, display_name FROM manual_members WHERE chat_id=?
        ) WHERE username=? COLLATE NOCASE LIMIT 1
        """,
        (chat_id, chat_id, username),
    ).fetchone()
    if existing:
        return existing, False
    minimum = connection.execute(
        """
        SELECT MIN(user_id) AS value FROM (
            SELECT user_id FROM submissions WHERE chat_id=?
            UNION ALL SELECT user_id FROM manual_members WHERE chat_id=?
        )
        """,
        (chat_id, chat_id),
    ).fetchone()["value"]
    temporary_id = min(-1, (minimum or 0) - 1)
    display_name = display_name.strip() or username
    connection.execute(
        """
        INSERT INTO manual_members(chat_id, user_id, username, display_name, created_at)
        VALUES(?,?,?,?,?)
        """,
        (
            chat_id, temporary_id, username, display_name,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    connection.commit()
    return connection.execute(
        "SELECT user_id, username, display_name FROM manual_members WHERE chat_id=? AND user_id=?",
        (chat_id, temporary_id),
    ).fetchone(), True


def save_score(connection, chat_id, member, game, day, score):
    attempts, maximum, success = score
    existing = connection.execute(
        """
        SELECT id FROM submissions
        WHERE chat_id=? AND user_id=? AND game=? AND played_on=?
        """,
        (chat_id, member["user_id"], game, day.isoformat()),
    ).fetchone()
    now = datetime.now().isoformat(timespec="seconds")
    if existing:
        connection.execute(
            """
            UPDATE submissions
            SET attempts=?, max_attempts=?, success=?, raw_text='manual edit',
                username=?, display_name=?, created_at=?
            WHERE id=?
            """,
            (
                attempts, maximum, int(success), member["username"],
                member["display_name"], now, existing["id"],
            ),
        )
        action = "Updated"
    else:
        next_id = connection.execute(
            "SELECT COALESCE(MIN(message_id), 0) - 1 AS value FROM submissions WHERE chat_id=?",
            (chat_id,),
        ).fetchone()["value"]
        connection.execute(
            """
            INSERT INTO submissions(
                chat_id, message_id, update_id, user_id, username, display_name,
                game, played_on, attempts, max_attempts, success, raw_text, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,'manual edit',?)
            """,
            (
                chat_id, next_id, next_id, member["user_id"], member["username"],
                member["display_name"], game, day.isoformat(), attempts, maximum,
                int(success), now,
            ),
        )
        action = "Added"
    connection.commit()
    return action


def safe_add(screen, row, column, text, style=0):
    height, width = screen.getmaxyx()
    if 0 <= row < height and column < width:
        try:
            screen.addnstr(row, column, str(text), max(0, width - column - 1), style)
        except curses.error:
            pass


def choose(screen, title, options):
    if not options:
        return None
    selected = 0
    while True:
        screen.erase()
        safe_add(screen, 1, 2, title, curses.A_BOLD)
        for index, option in enumerate(options):
            style = curses.A_REVERSE if index == selected else 0
            safe_add(screen, 3 + index, 4, str(option), style)
        safe_add(screen, screen.getmaxyx()[0] - 2, 2, "Up/Down select | Enter confirm | q cancel", curses.A_DIM)
        screen.refresh()
        key = screen.getch()
        if key in (curses.KEY_UP, ord("k")):
            selected = (selected - 1) % len(options)
        elif key in (curses.KEY_DOWN, ord("j")):
            selected = (selected + 1) % len(options)
        elif key in (10, 13, curses.KEY_ENTER):
            return selected
        elif key in (ord("q"), 27):
            return None


def prompt(screen, label, default=""):
    height, width = screen.getmaxyx()
    screen.move(height - 3, 0)
    screen.clrtobot()
    text = f"{label}"
    if default:
        text += f" [{default}]"
    text += ": "
    safe_add(screen, height - 3, 2, text, curses.A_BOLD)
    screen.refresh()
    curses.echo()
    try:
        value = screen.getstr(height - 3, min(width - 2, 2 + len(text)), max(1, width - len(text) - 5))
        decoded = value.decode("utf-8").strip()
        return decoded or default
    finally:
        curses.noecho()


def ask_score(screen, game, current=""):
    while True:
        suffix = f"1-{MAX_ATTEMPTS[game]} or X" if game in MAX_ATTEMPTS else "positive number"
        value = prompt(screen, f"{game} score ({suffix})", str(current) if current != "" else "")
        try:
            return parse_score(game, value), ""
        except ValueError as error:
            return None, str(error)


def tui(screen, connection):
    curses.curs_set(0)
    screen.keypad(True)
    groups = chats(connection)
    selected = choose(screen, "Choose group", [row["title"] or row["chat_id"] for row in groups])
    if selected is None:
        return
    chat = groups[selected]
    day = datetime.now(SGT).date()
    cursor = 0
    status = ""
    while True:
        rows = results(connection, chat["chat_id"], day)
        cursor = min(cursor, max(0, len(rows) - 1))
        screen.erase()
        safe_add(screen, 0, 2, "Leaderboardle Score Editor", curses.A_BOLD)
        safe_add(screen, 1, 2, f"Group: {chat['title'] or chat['chat_id']}   Date: {day.isoformat()}")
        safe_add(screen, 3, 2, "Member", curses.A_UNDERLINE)
        safe_add(screen, 3, 28, "Game", curses.A_UNDERLINE)
        safe_add(screen, 3, 45, "Score", curses.A_UNDERLINE)
        if not rows:
            safe_add(screen, 5, 4, "No results for this date.", curses.A_DIM)
        for index, row in enumerate(rows):
            style = curses.A_REVERSE if index == cursor else 0
            score = row["attempts"] if row["success"] else "X"
            safe_add(screen, 5 + index, 2, member_label(row), style)
            safe_add(screen, 5 + index, 28, row["game"], style)
            safe_add(screen, 5 + index, 45, score, style)
        footer = "Up/Down select | e edit | a add score | n new member | d delete | Left/Right day | g group | q quit"
        safe_add(screen, screen.getmaxyx()[0] - 3, 2, status, curses.A_BOLD)
        safe_add(screen, screen.getmaxyx()[0] - 2, 2, footer, curses.A_DIM)
        screen.refresh()
        status = ""
        key = screen.getch()
        if key in (curses.KEY_UP, ord("k")) and rows:
            cursor = (cursor - 1) % len(rows)
        elif key in (curses.KEY_DOWN, ord("j")) and rows:
            cursor = (cursor + 1) % len(rows)
        elif key == curses.KEY_LEFT:
            day -= timedelta(days=1)
            cursor = 0
        elif key == curses.KEY_RIGHT:
            day += timedelta(days=1)
            cursor = 0
        elif key == ord("t"):
            day = datetime.now(SGT).date()
            cursor = 0
        elif key == ord("g"):
            groups = chats(connection)
            chosen = choose(screen, "Choose group", [row["title"] or row["chat_id"] for row in groups])
            if chosen is not None:
                chat = groups[chosen]
                cursor = 0
        elif key == ord("n"):
            username = prompt(screen, "Telegram username (without @)")
            display_name = prompt(screen, "Display name", username)
            try:
                member, created = add_manual_member(
                    connection, chat["chat_id"], username, display_name
                )
                status = ("Added " if created else "Already exists: ") + member_label(member)
            except (ValueError, sqlite3.Error) as error:
                status = str(error)
        elif key == ord("a"):
            members = known_members(connection, chat["chat_id"])
            chosen = choose(screen, "Choose member", [member_label(row) for row in members])
            if chosen is not None:
                game_index = choose(screen, "Choose game", list(GAMES))
                if game_index is not None:
                    game = GAMES[game_index]
                    score, error = ask_score(screen, game)
                    if score:
                        status = save_score(connection, chat["chat_id"], members[chosen], game, day, score)
                    else:
                        status = error
        elif key == ord("e") and rows:
            row = rows[cursor]
            current = row["attempts"] if row["success"] else "X"
            score, error = ask_score(screen, row["game"], current)
            if score:
                status = save_score(connection, chat["chat_id"], row, row["game"], day, score)
            else:
                status = error
        elif key == ord("d") and rows:
            row = rows[cursor]
            confirmation = prompt(screen, f"Delete {member_label(row)} {row['game']}? Type y")
            if confirmation.lower() == "y":
                connection.execute("DELETE FROM submissions WHERE id=?", (row["id"],))
                connection.commit()
                status = "Deleted"
        elif key in (ord("q"), 27):
            return


def main():
    if not DB_PATH.exists():
        raise SystemExit("Database not found. Start the bot once first.")
    connection = connect()
    try:
        curses.wrapper(tui, connection)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
