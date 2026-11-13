import sqlite3
from datetime import date

from leaderboardle.db import Database, Submission
from score_editor import add_manual_member, connect, known_members, parse_score, save_score


def test_parse_scores():
    assert parse_score("Wordle", "3") == (3, 6, True)
    assert parse_score("Wordle", "x") == (7, 6, False)
    assert parse_score("Minecraftle", "8") == (8, 10, True)
    assert parse_score("Poople", "81") == (81, None, True)
    assert parse_score("Krillion", "420") == (420, None, True)


def test_save_score_updates_existing_result(tmp_path):
    path = tmp_path / "test.sqlite3"
    db = Database(path)
    db.save_submission(Submission(
        chat_id=-1, message_id=1, update_id=1, user_id=7,
        username="player", display_name="Player", game="Poople",
        played_on=date(2026, 11, 12), attempts=81, max_attempts=None,
        success=True, raw_text="fixture",
    ))
    db.close()
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    member = connection.execute("SELECT * FROM submissions").fetchone()

    assert save_score(
        connection, -1, member, "Poople", date(2026, 11, 12),
        (15, None, True),
    ) == "Updated"
    row = connection.execute("SELECT attempts, raw_text FROM submissions").fetchone()
    assert row["attempts"] == 15
    assert row["raw_text"] == "manual edit"


def test_new_manual_member_appears_in_member_list(tmp_path):
    path = tmp_path / "test.sqlite3"
    db = Database(path)
    db.close()
    connection = connect(path)

    member, created = add_manual_member(
        connection, -1, "newplayer", "New Player"
    )

    assert created is True
    assert member["user_id"] < 0
    assert [row["username"] for row in known_members(connection, -1)] == ["newplayer"]
