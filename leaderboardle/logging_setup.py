from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO

from .config import SGT


class DailyFileHandler(logging.Handler):
    """Write to a date-named file, switching at midnight Singapore time."""

    def __init__(self, log_dir: Path):
        super().__init__()
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._day: str | None = None
        self._stream: TextIO | None = None

    def _stream_for(self, record: logging.LogRecord) -> TextIO:
        day = datetime.fromtimestamp(record.created, SGT).date().isoformat()
        if day != self._day or self._stream is None:
            if self._stream:
                self._stream.close()
            path = self.log_dir / f"leaderboardle-{day}.log"
            self._stream = path.open("a", encoding="utf-8", buffering=1)
            self._day = day
        return self._stream

    def emit(self, record: logging.LogRecord) -> None:
        try:
            stream = self._stream_for(record)
            stream.write(self.format(record) + "\n")
            stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        if self._stream:
            self._stream.close()
            self._stream = None
        super().close()


class SingaporeFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):  # noqa: N802 - logging API name
        current = datetime.fromtimestamp(record.created, SGT)
        return current.strftime(datefmt or "%Y-%m-%d %H:%M:%S")


def configure_logging(log_dir: Path) -> None:
    formatter = SingaporeFormatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    daily_file = DailyFileHandler(log_dir)
    daily_file.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(daily_file)

    # httpx INFO messages include the Telegram token inside request URLs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
