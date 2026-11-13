# Contributing to Leaderboardle

Leaderboardle is intentionally small. Please keep changes local, deterministic, and easy to understand.

## Before changing recognition

Screenshot recognition uses OCR and image heuristics. It is not machine learning, and it will sometimes fail because of cropping, themes, browser controls, ads, compression, or a game changing its design.

When fixing a failed screenshot:

- Keep the original image as a private local fixture unless you have permission to publish it.
- Reproduce the failure offline. Do not test against the live Telegram bot or live database.
- Make the smallest useful change to the classifier or extractor.
- Add a regression test for the new screenshot shape or text pattern.
- Run the full test suite and confirm existing games still work.

The main files are:

- `leaderboardle/vision.py`: game detection and score extraction
- `leaderboardle/bot.py`: Telegram message handling and summaries
- `leaderboardle/db.py`: SQLite storage and reconciliation
- `score_editor.py`: local score editor
- `tests/`: regression and behavior tests

## Prompt for a screenshot that did not work

Attach the failed screenshot to your coding agent and use a prompt like this:

> Open this local Leaderboardle repository. The attached screenshot should be recognized as `<game>` with a score of `<score>`, but the bot rejected it or extracted the wrong value. Reproduce the behavior offline without touching the running bot or live database. Update the deterministic OCR or image heuristics, add a regression test for this edge case, and run the full test suite. Preserve behavior for Wordle, Minecraftle, Poople, and Krillion. Do not restart the service.

If the live database also contains a wrong result, handle that separately and state the group, date, username, game, old value, and correct value explicitly.

## Prompt for adding another daily game

Attach several representative result screenshots, including different screen sizes or themes if possible, then use:

> Extend this local Leaderboardle Telegram bot to support `<game>`. The attached images are representative results. The score is `<describe the value to extract>`, and `<higher or lower>` is better. Keep recognition deterministic and local with OCR or image heuristics. Do not add an LLM, cloud backend, or manual submission flow. Add game detection, score extraction, database and leaderboard support, startup reconciliation, and regression tests. Keep the leaderboard brief and preserve all existing games. Update the documentation, but do not restart the running service or modify live scores.

Useful details to include:

- What value determines the score
- Whether higher or lower is better
- How a win, loss, or incomplete result appears
- Whether the screenshot contains a puzzle date or should use the Telegram message date
- Several screenshots that show likely layout variations

## Run tests

```sh
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

Please do not commit `.env`, bot tokens, private group data, the SQLite database, logs, or personal screenshots.
