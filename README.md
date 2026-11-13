# Leaderboardle

Leaderboardle is a local Telegram bot for group chats where friends share screenshots of daily games. Add it to the chat, keep posting screenshots as usual, and let the bot handle the rest.

It currently supports:

- Wordle
- Minecraftle
- Poople
- Krillion

The bot reads each screenshot with local OCR, records the sender's result, tracks participation streaks, and posts a short top-three leaderboard at midnight Singapore time. The schedule uses the `Asia/Singapore` timezone explicitly, regardless of the laptop's configured timezone. No submission form, caption, or special command is needed.

## How it works

- Screenshots are matched using text, layout, color, and game-specific visual patterns.
- Results are stored separately for each Telegram group in a local SQLite database.
- Missed Telegram updates are picked up after normal laptop downtime, subject to Telegram's 24-hour update limit.
- Rejected screenshots from the current day are kept locally and rescanned when the bot starts again.
- `/leaderboard` shows today's standings. `/leaderboard YYYY-MM-DD` shows another day.
- `/admin` is hidden from the command menu and only works for usernames listed in `admins.txt`.

Recognition is rule-based and will not be perfectly accurate. Browser chrome, ads, cropping, compression, and game redesigns can all affect OCR. If a screenshot is not recognized, see [CONTRIBUTING.md](CONTRIBUTING.md) for a ready-to-use agent prompt.

## Example leaderboard

Usernames below are fictional. Each game displays at most three members.

```text
🏆 12 Nov leaderboard

🟩 Wordle
🥇 @alice_daily - 3 · 🔥4
🥈 @bob_blocks - 4 · 🔥2

⛏️ Minecraftle
🥇 @bob_blocks - 5 · 🔥3

💩 Poople
🥇 @carol_guesses - 7 · 🔥1

🌊 Krillion
🥇 @alice_daily - 420 · 🔥2

👑 Overall leaders (2 wins)
@alice_daily
```

## Setup

### 1. Create a Telegram bot

Open [BotFather](https://t.me/BotFather), run `/newbot`, and copy the token it gives you.

### 2. Install the project

Python 3.11 or newer and Tesseract OCR are required. On macOS:

```sh
brew install python tesseract
git clone <your-repository-url>
cd leaderboardle
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 3. Configure the token

```sh
cp .env.example .env
```

Edit `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=paste-token-from-botfather
```

Create the local admin allowlist:

```sh
touch admins.txt
```

For admin access, add lowercase Telegram usernames to `admins.txt`, one per line and without `@`. This file is intentionally included in `.gitignore` because it can contain private Telegram usernames. Leave it empty if you do not need the hidden `/admin` command.

### 4. Disable BotFather privacy mode

In BotFather, run `/setprivacy`, select your bot, then choose **Disable**.

Telegram privacy mode normally hides ordinary group messages from bots. Disabling it is required because Leaderboardle needs to receive screenshots that are posted without a command. The bot does not need to be a group admin.

### 5. Add the bot and start it

Add the bot to your group chat, then run:

```sh
.venv/bin/python main.py
```

That is all your friends need to do. They can continue sharing screenshots normally.

## Run in the background

The Makefile keeps the bot running with `nohup` and writes output to `logs/nohup.log`. The application also creates one dated log file per Singapore day.

```sh
make start
make status
make logs
make restart
make stop
```

Use `make deploy` to pull the current branch, install dependencies, and restart. If the bot was started manually before using the Makefile, run `make adopt` once.

## Local data and privacy

- OCR runs locally. No LLM or cloud image-analysis service is used.
- Scores, checkpoints, and pending screenshot data are stored in `data/leaderboard.sqlite3`.
- Logs are stored under `logs/`.
- Telegram still receives and delivers the original group messages as part of its normal service.
- A bot cannot request arbitrary chat history. Telegram only retains unreceived Bot API updates for up to 24 hours, so longer offline periods can leave gaps.

To inspect or correct scores locally, run:

```sh
.venv/bin/python score_editor.py
```

## Contributing

Contributions for new games, recognition improvements, and regression tests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the project layout, test command, and copyable prompts for coding agents.

