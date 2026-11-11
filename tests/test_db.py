from datetime import date, timedelta

from leaderboardle.db import Database, Submission


def test_newer_submission_replaces_same_daily_game(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    base = dict(
        chat_id=-1, update_id=1, user_id=7, username="player",
        display_name="Player", game="Wordle", played_on=date(2026, 11, 11),
        max_attempts=6, success=True, raw_text="Wordle 4/6",
    )
    assert db.save_submission(Submission(message_id=10, attempts=4, **base))
    assert db.save_submission(Submission(message_id=11, attempts=3, **base))
    rows = db.leaderboard(-1, date(2026, 11, 11))
    assert len(rows) == 1
    assert rows[0]["attempts"] == 3


def test_reset_is_scoped_to_chat_and_day(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    for chat_id, message_id in [(-1, 1), (-2, 2)]:
        db.save_submission(Submission(
            chat_id=chat_id, message_id=message_id, update_id=message_id,
            user_id=1, username=None, display_name="P", game="Poople",
            played_on=date(2026, 11, 11), attempts=2, max_attempts=None,
            success=True, raw_text="Poople 2 attempts",
        ))
    assert db.reset_day(-1, date(2026, 11, 11)) == 1
    assert len(db.leaderboard(-2, date(2026, 11, 11))) == 1


def test_participation_streak_is_per_member_and_game(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    last_day = date(2026, 11, 11)
    for offset in (2, 1, 0):
        day = last_day - timedelta(days=offset)
        db.save_submission(Submission(
            chat_id=-1, message_id=100 + offset, update_id=100 + offset,
            user_id=7, username="player", display_name="Player", game="Wordle",
            played_on=day, attempts=3, max_attempts=6, success=True,
            raw_text="Wordle 3/6",
        ))
    assert db.participation_streak(-1, 7, "Wordle", last_day) == 3
    assert db.participation_streak(-1, 7, "Minecraftle", last_day) == 0


def test_streak_breaks_on_missed_day(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    last_day = date(2026, 11, 11)
    for index, day in enumerate((last_day - timedelta(days=2), last_day)):
        db.save_submission(Submission(
            chat_id=-1, message_id=200 + index, update_id=200 + index,
            user_id=8, username=None, display_name="P", game="Poople",
            played_on=day, attempts=10, max_attempts=None, success=True,
            raw_text="Poople",
        ))
    assert db.participation_streak(-1, 8, "Poople", last_day) == 1

