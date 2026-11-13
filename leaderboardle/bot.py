from __future__ import annotations

import asyncio
import html
import json
import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta

import pytesseract
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Config, SGT
from .db import Database, Submission
from .vision import detect_result


LOG = logging.getLogger(__name__)
GAME_ORDER = {name: i for i, name in enumerate(("Wordle", "Minecraftle", "Poople", "Krillion"))}
HIGH_SCORE_GAMES = {"Krillion"}
GAME_ICONS = {
    "Wordle": "🟩",
    "Minecraftle": "⛏️",
    "Poople": "💩",
    "Krillion": "🌊",
}
RANK_LABELS = {1: "🥇", 2: "🥈", 3: "🥉"}


class LeaderboardBot:
    def __init__(self, config: Config):
        self.config = config
        self.db = Database(config.db_path)
        self.app = Application.builder().token(config.token).build()
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.app.add_handler(CommandHandler("leaderboard", self.leaderboard_command))
        self.app.add_handler(CommandHandler("admin", self.admin_command))
        self.app.add_handler(CallbackQueryHandler(self.admin_callback, pattern=r"^admin:"))
        self.app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, self.image_message))

    @staticmethod
    def _chat_allowed(update: Update) -> bool:
        return bool(update.effective_chat and update.effective_chat.type in (ChatType.GROUP, ChatType.SUPERGROUP))

    def _is_admin(self, update: Update) -> bool:
        username = (update.effective_user.username or "").lower() if update.effective_user else ""
        return username in self.config.admins

    def _remember_chat(self, update: Update) -> None:
        chat = update.effective_chat
        if chat:
            self.db.remember_chat(chat.id, chat.title or "")

    async def image_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._chat_allowed(update) or not update.message or not update.effective_user:
            return
        self._remember_chat(update)
        media = update.message.photo[-1] if update.message.photo else update.message.document
        if not media:
            return
        telegram_file = await media.get_file()
        image_bytes = bytes(await telegram_file.download_as_bytearray())
        sent_at = update.message.date.astimezone(SGT)
        user = update.effective_user
        self.db.stage_image(
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
            update_id=update.update_id,
            user_id=user.id,
            username=user.username,
            display_name=user.full_name,
            sent_at=sent_at,
            played_on=sent_at.date(),
            image=image_bytes,
        )
        await self._process_saved_image(
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
            update_id=update.update_id,
            user_id=user.id,
            username=user.username,
            display_name=user.full_name,
            played_on=sent_at.date(),
            image_bytes=image_bytes,
            is_rescan=False,
        )

    async def _process_saved_image(
        self,
        *,
        chat_id: int,
        message_id: int,
        update_id: int,
        user_id: int,
        username: str | None,
        display_name: str,
        played_on: date,
        image_bytes: bytes,
        is_rescan: bool,
    ) -> None:
        try:
            result = await asyncio.to_thread(detect_result, image_bytes)
        except Exception as error:
            self.db.mark_image_result(
                chat_id, message_id, "error", last_error=repr(error)
            )
            LOG.exception("Could not analyze image from message %s", message_id)
            return
        if not result:
            self.db.mark_image_result(chat_id, message_id, "rejected")
            LOG.info(
                "Retained unrecognized image from %s (chat=%s message=%s)",
                display_name, chat_id, message_id,
            )
            return
        if self.db.merge_manual_member(chat_id, user_id, username, display_name):
            LOG.info("Merged manual member @%s into Telegram user %s", username, user_id)
        attempts = result.attempts
        success = result.success
        if result.game == "Wordle" and result.distribution is not None:
            previous = self.db.game_snapshot(chat_id, user_id, result.game)
            attempts, success = self._resolve_wordle_stats(result, previous)
            self.db.save_game_snapshot(
                chat_id,
                user_id,
                result.game,
                result.played_total,
                result.current_streak,
                result.distribution,
            )
            if attempts is None or success is None:
                LOG.info(
                    "Saved initial Wordle stats for %s; need the next distribution delta to infer a score",
                    display_name,
                )
                self.db.mark_image_result(
                    chat_id, message_id, "accepted",
                    detected_game=result.game, clear_image=True,
                )
                return
        item = Submission(
            chat_id=chat_id,
            message_id=message_id,
            update_id=update_id,
            user_id=user_id,
            username=username,
            display_name=display_name,
            game=result.game,
            played_on=result.played_on or played_on,
            attempts=attempts,
            max_attempts=result.max_attempts,
            success=success,
            raw_text=result.raw_text,
        )
        saved = self.db.save_submission(item)
        self.db.mark_image_result(
            chat_id, message_id, "accepted",
            detected_game=result.game, clear_image=True,
        )
        if saved:
            action = "Reconciled" if is_rescan else "Recorded"
            LOG.info("%s %s for %s: %s", action, result.game, display_name, attempts)

    async def _rescan_rejected_today(self) -> None:
        today = datetime.now(SGT).date()
        rows = self.db.unresolved_images(today)
        if not rows:
            return
        LOG.info("Rescanning %s unresolved image(s) for %s", len(rows), today)
        for row in rows:
            await self._process_saved_image(
                chat_id=row["chat_id"],
                message_id=row["message_id"],
                update_id=row["update_id"],
                user_id=row["user_id"],
                username=row["username"],
                display_name=row["display_name"],
                played_on=date.fromisoformat(row["played_on"]),
                image_bytes=bytes(row["image"]),
                is_rescan=True,
            )

    @staticmethod
    def _resolve_wordle_stats(result, previous) -> tuple[int | None, bool | None]:
        current = result.distribution
        if current is None:
            return None, None
        if previous:
            old = tuple(json.loads(previous["distribution"]))
            deltas = [new - prior for new, prior in zip(current, old)]
            if result.played_total == previous["played"]:
                return None, None
            positive = [index + 1 for index, delta in enumerate(deltas) if delta == 1]
            if len(positive) == 1 and sum(deltas) == 1:
                return positive[0], True
            if sum(deltas) == 0 and (
                result.played_total is None or previous["played"] is None
                or result.played_total > previous["played"]
            ):
                return 7, False
            return None, None
        wins = sum(current)
        if result.played_total == 1 and wins == 1:
            return current.index(1) + 1, True
        if result.current_streak == 0 and result.played_total and result.played_total > wins:
            return 7, False
        return None, None

    @staticmethod
    def _name(row) -> str:
        if row["username"]:
            return "@" + html.escape(row["username"])
        return html.escape(row["display_name"])

    def format_leaderboard(self, chat_id: int, day: date) -> str | None:
        rows = self.db.leaderboard(chat_id, day)
        if not rows:
            return None
        grouped = defaultdict(list)
        for row in rows:
            grouped[row["game"]].append(row)
        lines = [f"🏆 <b>{day.strftime('%-d %b')} leaderboard</b>"]
        wins = defaultdict(int)
        for game in sorted(grouped, key=lambda item: GAME_ORDER.get(item, 99)):
            entries = grouped[game]
            entries.sort(
                key=lambda row: (
                    not row["success"],
                    -row["attempts"] if game in HIGH_SCORE_GAMES else row["attempts"],
                    row["display_name"].lower(),
                )
            )
            successful = [row for row in entries if row["success"]]
            if successful:
                best = successful[0]["attempts"]
                for row in successful:
                    if row["attempts"] == best:
                        wins[row["user_id"]] += 1
            icon = GAME_ICONS.get(game, "🎮")
            lines.extend(["", f"{icon} <b>{html.escape(game)}</b>"])
            previous_score = None
            rank = 0
            for position, row in enumerate(entries[:3], start=1):
                score = str(row["attempts"]) if row["success"] else "X"
                rank_score = (row["success"], row["attempts"])
                if rank_score != previous_score:
                    rank = position
                    previous_score = rank_score
                streak = self.db.participation_streak(
                    chat_id, row["user_id"], game, day
                )
                rank_label = RANK_LABELS.get(rank, f"{rank}.")
                lines.append(f"{rank_label} {self._name(row)} — {score} · 🔥{streak}")
        if len(grouped) > 1 and wins:
            leaders = sorted(wins.items(), key=lambda pair: (-pair[1], pair[0]))
            best_wins = leaders[0][1]
            winning_ids = {user_id for user_id, count in leaders if count == best_wins}
            names = []
            for row in rows:
                if row["user_id"] in winning_ids and self._name(row) not in names:
                    names.append(self._name(row))
            lines.extend([
                "",
                f"👑 <b>Overall leaders</b> ({best_wins} win{'s' if best_wins != 1 else ''})",
                ", ".join(names[:3]),
            ])
        return "\n".join(lines)

    async def leaderboard_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._chat_allowed(update) or not update.message:
            return
        self._remember_chat(update)
        day = datetime.now(SGT).date()
        if context.args:
            try:
                day = date.fromisoformat(context.args[0])
            except ValueError:
                await update.message.reply_text("Use /leaderboard or /leaderboard YYYY-MM-DD")
                return
        text = self.format_leaderboard(update.effective_chat.id, day)
        await update.message.reply_text(
            text or f"No results for {day.strftime('%-d %b')} yet.",
            parse_mode=ParseMode.HTML,
        )

    def _admin_keyboard(self, selected: date | None = None) -> InlineKeyboardMarkup:
        today = datetime.now(SGT).date()
        days = [selected] if selected else [today - timedelta(days=i) for i in range(7)]
        rows = [
            [InlineKeyboardButton(f"Reset {day.strftime('%-d %b')}", callback_data=f"admin:ask_day:{day.isoformat()}")]
            for day in days
            if day is not None
        ]
        rows.extend([
            [InlineKeyboardButton("Reset all days", callback_data="admin:ask_all")],
            [InlineKeyboardButton("Close", callback_data="admin:close")],
        ])
        return InlineKeyboardMarkup(rows)

    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._chat_allowed(update) or not update.message:
            return
        if not self._is_admin(update):
            return
        self._remember_chat(update)
        selected = None
        if context.args:
            try:
                selected = date.fromisoformat(context.args[0])
            except ValueError:
                await update.message.reply_text("Use /admin or /admin YYYY-MM-DD")
                return
        await update.message.reply_text("Admin", reply_markup=self._admin_keyboard(selected))

    async def admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return
        if not self._is_admin(update):
            await query.answer("Admin only", show_alert=True)
            return
        await query.answer()
        data = query.data or ""
        chat_id = query.message.chat.id
        if data == "admin:close":
            await query.edit_message_text("Closed.")
        elif data.startswith("admin:ask_day:"):
            day = date.fromisoformat(data.rsplit(":", 1)[1])
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(
                "Confirm reset", callback_data=f"admin:do_day:{day.isoformat()}"
            ), InlineKeyboardButton("Cancel", callback_data="admin:close")]])
            await query.edit_message_text(f"Reset {day.isoformat()}?", reply_markup=keyboard)
        elif data.startswith("admin:do_day:"):
            day = date.fromisoformat(data.rsplit(":", 1)[1])
            count = self.db.reset_day(chat_id, day)
            await query.edit_message_text(f"Reset {day.isoformat()} ({count} result{'s' if count != 1 else ''}).")
        elif data == "admin:ask_all":
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(
                "Confirm reset all", callback_data="admin:do_all"
            ), InlineKeyboardButton("Cancel", callback_data="admin:close")]])
            await query.edit_message_text("Reset every saved day for this group?", reply_markup=keyboard)
        elif data == "admin:do_all":
            count = self.db.reset_all(chat_id)
            await query.edit_message_text(f"Reset all days ({count} results).")

    async def _send_summary(self, chat_id: int, day: date) -> None:
        text = self.format_leaderboard(chat_id, day)
        if text:
            await self.app.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
        self.db.set_checkpoint(f"last_summary:{chat_id}", day.isoformat())

    async def _catch_up_summaries(self) -> None:
        yesterday = datetime.now(SGT).date() - timedelta(days=1)
        for chat_id in self.db.chats():
            for day in self.db.pending_summary_days(chat_id, yesterday):
                await self._send_summary(chat_id, day)

    async def _midnight_loop(self) -> None:
        while True:
            now = datetime.now(SGT)
            tomorrow = now.date() + timedelta(days=1)
            next_midnight = datetime.combine(tomorrow, time.min, tzinfo=SGT)
            await asyncio.sleep(max(1, (next_midnight - now).total_seconds()))
            day = tomorrow - timedelta(days=1)
            for chat_id in self.db.chats():
                try:
                    await self._send_summary(chat_id, day)
                except Exception:
                    LOG.exception("Could not send summary to chat %s", chat_id)

    async def _drain_pending(self, offset: int) -> int:
        while True:
            updates = await self.app.bot.get_updates(
                offset=offset, timeout=0, limit=100,
                allowed_updates=["message", "callback_query"],
            )
            if not updates:
                return offset
            for update in updates:
                await self.app.process_update(update)
                self.db.set_checkpoint("last_update_id", update.update_id)
                offset = update.update_id + 1

    async def run(self) -> None:
        # Fail at startup with a useful message instead of silently ignoring every screenshot.
        await asyncio.to_thread(pytesseract.get_tesseract_version)
        async with self.app:
            await self.app.start()
            await self.app.bot.set_my_commands([
                BotCommand("leaderboard", "show today's leaderboard"),
            ])
            last = int(self.db.checkpoint("last_update_id", "-1") or -1)
            offset = await self._drain_pending(last + 1 if last >= 0 else 0)
            await self._rescan_rejected_today()
            await self._catch_up_summaries()
            midnight_task = asyncio.create_task(self._midnight_loop())
            try:
                while True:
                    try:
                        updates = await self.app.bot.get_updates(
                            offset=offset, timeout=30, limit=100,
                            allowed_updates=["message", "callback_query"],
                        )
                        for update in updates:
                            await self.app.process_update(update)
                            self.db.set_checkpoint("last_update_id", update.update_id)
                            offset = update.update_id + 1
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        LOG.exception("Polling failed; retrying")
                        await asyncio.sleep(5)
            finally:
                midnight_task.cancel()
                await asyncio.gather(midnight_task, return_exceptions=True)
                await self.app.stop()
                self.db.close()

