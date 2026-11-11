import logging
from datetime import datetime

from leaderboardle.config import SGT
from leaderboardle.logging_setup import DailyFileHandler


def test_daily_file_handler_switches_on_sgt_date(tmp_path):
    handler = DailyFileHandler(tmp_path)
    handler.setFormatter(logging.Formatter("%(message)s"))
    first = logging.LogRecord("test", logging.INFO, "", 0, "first", (), None)
    first.created = datetime(2026, 11, 11, 23, 59, tzinfo=SGT).timestamp()
    second = logging.LogRecord("test", logging.INFO, "", 0, "second", (), None)
    second.created = datetime(2026, 11, 12, 0, 0, tzinfo=SGT).timestamp()
    handler.emit(first)
    handler.emit(second)
    handler.close()

    assert (tmp_path / "leaderboardle-2026-11-11.log").read_text() == "first\n"
    assert (tmp_path / "leaderboardle-2026-11-12.log").read_text() == "second\n"
