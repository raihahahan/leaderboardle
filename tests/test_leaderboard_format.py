from datetime import date

from leaderboardle.bot import LeaderboardBot
from leaderboardle.db import Database, Submission


def add(db, message_id, user_id, username, game, attempts):
    db.save_submission(Submission(
        chat_id=-1,
        message_id=message_id,
        update_id=message_id,
        user_id=user_id,
        username=username,
        display_name=username,
        game=game,
        played_on=date(2026, 11, 11),
        attempts=attempts,
        max_attempts=None,
        success=True,
        raw_text="fixture",
    ))


def test_leaderboard_uses_ranked_multiline_sections(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    add(db, 1, 1, "raihahan", "Minecraftle", 4)
    add(db, 2, 2, "amir", "Poople", 5)
    add(db, 3, 3, "kai", "Poople", 5)
    add(db, 4, 4, "gian", "Poople", 6)
    add(db, 5, 5, "jolene", "Poople", 15)
    bot = LeaderboardBot.__new__(LeaderboardBot)
    bot.db = db

    text = bot.format_leaderboard(-1, date(2026, 11, 11))

    assert "⛏️ <b>Minecraftle</b>\n🥇 @raihahan — 4 · 🔥1" in text
    assert "💩 <b>Poople</b>\n🥇 @amir — 5 · 🔥1\n🥇 @kai — 5 · 🔥1\n🥉 @gian — 6 · 🔥1" in text
    assert "@jolene" not in text
    assert "👑 <b>Overall leaders</b> (1 win)" in text
