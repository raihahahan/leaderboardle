# Leaderboardle

A deliberately small, local-only Telegram bot that watches group screenshots, extracts daily-game results with local OCR, and posts a brief leaderboard at midnight Singapore time.

## What it does

- Watches photo messages and image documents without replying or reacting.
- Recognizes Wordle, Minecraftle, Poople, and Krillion from page phrases, layout/aspect ratio, and color signatures; the title is only a fallback.
- Uses targeted per-game extraction: Poople's “used” guesses, Minecraftle's score, and Krillion's large pixel score. Every game uses the Telegram message's Singapore date.
- For a Wordle statistics-only screenshot, stores the player's six-row distribution and infers today's result from its next delta. A first screenshot can only be scored when it is mathematically unambiguous (for example, a current-streak-zero loss); otherwise it silently becomes the baseline.
- Saves results, Telegram update checkpoints, and summary checkpoints in `data/leaderboard.sqlite3`.
- On restart, consumes Telegram's pending update queue before sending any missed daily summaries.
- Posts the day that just ended at `00:00 Asia/Singapore`.
- Shows a per-member, per-game consecutive participation streak (`🔥N`). Only members who submitted that game on the requested day appear.
- Formats each game as its own ranked section with one member per line, including tied ranks, capped at the top three displayed members. The overall-leaders list is also capped at three names.
- `/leaderboard` shows today. `/leaderboard YYYY-MM-DD` shows another day.
- The unlisted `/admin` command gives whitelisted admins reset buttons for the last seven days or all days. `/admin YYYY-MM-DD` targets any other day. It is omitted from Telegram's command menu, and non-admin attempts are silently ignored.

The bot stays silent when an image is not recognized.

## Telegram limitation

Bot accounts cannot request arbitrary group message history. Telegram retains unreceived Bot API updates for at most 24 hours. The local checkpoint prevents duplicates and catches up after normal laptop downtime, but an outage longer than 24 hours can leave an unrecoverable gap. Full history would require logging in as a Telegram user via MTProto, which is intentionally outside this token-only design.

## Setup (macOS)

1. Install Python 3.11+ and Tesseract OCR:

   ```sh
   brew install python tesseract
   ```

2. Create the environment and install dependencies:

   ```sh
   cd leaderboardle
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

3. In BotFather, run `/setprivacy`, choose this bot, and select **Disable**. Without this, Telegram hides ordinary group screenshots from the bot.

4. Add the bot to the group. It does not need to be an admin.

5. Start it:

   ```sh
   .venv/bin/python main.py
   ```

### Run in the background

Logs are written both to stdout and to a new Singapore-date file each day at
`logs/leaderboardle-YYYY-MM-DD.log`.

```sh
mkdir -p logs
nohup .venv/bin/python main.py > logs/nohup.out 2>&1 &
tail -f logs/nohup.out
```

To follow the current daily file instead:

```sh
tail -f "logs/leaderboardle-$(TZ=Asia/Singapore date +%F).log"
```

The token is read only from `.env`. Admin usernames are lowercase, without `@`, one per line in `admins.txt`.

## Test

```sh
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

## Notes on recognition

OCR is deterministic and local; no image or chat data is sent anywhere except Telegram's normal bot file download. Krillion is ranked as a higher-is-better score; the other games rank fewer guesses first.

