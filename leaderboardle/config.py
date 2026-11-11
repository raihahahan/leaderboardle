from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
SGT = ZoneInfo("Asia/Singapore")


@dataclass(frozen=True)
class Config:
    token: str
    db_path: Path
    admins: frozenset[str]


def _load_admins(path: Path) -> frozenset[str]:
    if not path.exists():
        return frozenset()
    return frozenset(
        line.strip().lstrip("@").lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def load_config() -> Config:
    load_dotenv(ROOT / ".env")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing from .env")
    data_dir = ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return Config(
        token=token,
        db_path=data_dir / "leaderboard.sqlite3",
        admins=_load_admins(ROOT / "admins.txt"),
    )

