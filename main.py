from __future__ import annotations

import asyncio

from leaderboardle.bot import LeaderboardBot
from leaderboardle.config import ROOT, load_config
from leaderboardle.logging_setup import configure_logging


def main() -> None:
    configure_logging(ROOT / "logs")
    try:
        asyncio.run(LeaderboardBot(load_config()).run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

