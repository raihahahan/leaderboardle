import asyncio
from datetime import datetime

from leaderboardle.bot import LeaderboardBot
from leaderboardle.config import SGT
from leaderboardle.db import Database
from leaderboardle.vision import Detection


def test_startup_rescan_reconciles_rejected_image(tmp_path, monkeypatch):
    db = Database(tmp_path / "test.sqlite3")
    today = datetime.now(SGT).date()
    db.stage_image(
        chat_id=-1,
        message_id=75,
        update_id=750,
        user_id=12,
        username="diver",
        display_name="Diver",
        sent_at=datetime.now(SGT),
        played_on=today,
        image=b"previously rejected image",
    )
    db.mark_image_result(-1, 75, "rejected")
    monkeypatch.setattr(
        "leaderboardle.bot.detect_result",
        lambda _: Detection("Krillion", 420, None, True, "fixture"),
    )
    bot = LeaderboardBot.__new__(LeaderboardBot)
    bot.db = db

    asyncio.run(bot._rescan_rejected_today())

    rows = db.leaderboard(-1, today)
    assert len(rows) == 1
    assert rows[0]["game"] == "Krillion"
    assert rows[0]["attempts"] == 420
    assert db.unresolved_images(today) == []
