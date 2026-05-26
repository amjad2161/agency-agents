"""
telegram_bot.py — Pass 22
JarvisTelegramBot: async python-telegram-bot v20+ wrapper with mock fallback.
Token from env var TELEGRAM_BOT_TOKEN.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# ── optional dep detection ─────────────────────────────────────────────────────

_PTB_AVAILABLE = False
try:
    from telegram import Update
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
    _PTB_AVAILABLE = True
    logger.info("python-telegram-bot available")
except ImportError:
    logger.warning("python-telegram-bot not installed — using MockTelegramBot")

# ── brain import (lazy to avoid circular) ─────────────────────────────────────

def _get_brain():
    try:
        from runtime.agency.supreme_jarvis_brain import SupremeJarvisBrain
        return SupremeJarvisBrain()
    except Exception:
        try:
            from supreme_jarvis_brain import SupremeJarvisBrain
            return SupremeJarvisBrain()
        except Exception:
            return None


# ── Mock backend ───────────────────────────────────────────────────────────────

class MockTelegramBot:
    """Logs to console; no real Telegram connection."""

    def __init__(self, token: Optional[str] = None):
        self.token = token or "MOCK_TOKEN"
        self._running = False
        self._log: list = []

    def start(self):
        self._running = True
        msg = f"[MockTelegramBot] started (token={self.token[:8]}...)"
        logger.info(msg)
        self._log.append(msg)

    def stop(self):
        self._running = False
        msg = "[MockTelegramBot] stopped"
        logger.info(msg)
        self._log.append(msg)

    def send_message(self, chat_id: int | str, text: str):
        msg = f"[MockTelegramBot] → chat={chat_id}: {text}"
        logger.info(msg)
        self._log.append(msg)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def log(self) -> list:
        return list(self._log)


# ── Real PTB backend ───────────────────────────────────────────────────────────

class _PTBBot:
    """python-telegram-bot v20+ async implementation."""

    HELP_TEXT = (
        "פקודות זמינות:\n"
        "/start — אתחול\n"
        "/help — עזרה\n"
        "/ask <שאלה> — שאל את JARVIS\n"
        "/skill <slug> — הפעל סקיל\n"
        "/status — מצב המערכת\n"
        "/emotion — מצב רגשי נוכחי\n"
    )

    def __init__(self, token: str):
        self.token = token
        self._app: Optional[object] = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False

    def _build_app(self):
        app = Application.builder().token(self.token).build()
        app.add_handler(CommandHandler("start", self._cmd_start))
        app.add_handler(CommandHandler("help", self._cmd_help))
        app.add_handler(CommandHandler("ask", self._cmd_ask))
        app.add_handler(CommandHandler("skill", self._cmd_skill))
        app.add_handler(CommandHandler("status", self._cmd_status))
        app.add_handler(CommandHandler("emotion", self._cmd_emotion))
        return app

    # ── command handlers ───────────────────────────────────────────────────────

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("שלום! אני JARVIS. /help לרשימת פקודות.")

    async def _cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(self.HELP_TEXT)

    async def _cmd_ask(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        question = " ".join(ctx.args) if ctx.args else ""
        if not question:
            await update.message.reply_text("שימוש: /ask <שאלה>")
            return
        brain = _get_brain()
        if brain:
            try:
                answer = brain.route(question)
            except Exception as exc:
                answer = f"שגיאה: {exc}"
        else:
            answer = f"[JARVIS] תשובה ל: {question}"
        await update.message.reply_text(str(answer))

    async def _cmd_skill(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        slug = ctx.args[0] if ctx.args else ""
        if not slug:
            await update.message.reply_text("שימוש: /skill <slug>")
            return
        brain = _get_brain()
        if brain:
            try:
                result = brain.route(f"skill:{slug}")
            except Exception as exc:
                result = f"שגיאה: {exc}"
        else:
            result = f"[JARVIS] מפעיל סקיל: {slug}"
        await update.message.reply_text(str(result))

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        brain = _get_brain()
        if brain and hasattr(brain, "status"):
            status = brain.status()
        else:
            status = "JARVIS פעיל ✅"
        await update.message.reply_text(str(status))

    async def _cmd_emotion(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        try:
            from runtime.agency.emotion_engine import EmotionEngine
            ee = EmotionEngine()
            state = ee.get_current_state()
        except Exception:
            state = "ניטרלי"
        await update.message.reply_text(f"מצב רגשי: {state}")

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("JarvisTelegramBot started")

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._app = self._build_app()
        self._loop.run_until_complete(self._app.run_polling())

    def stop(self):
        self._running = False
        if self._app:
            async def _stop():
                await self._app.stop()
                await self._app.shutdown()
            if self._loop and not self._loop.is_closed():
                asyncio.run_coroutine_threadsafe(_stop(), self._loop).result(timeout=5)
        logger.info("JarvisTelegramBot stopped")

    def send_message(self, chat_id: int | str, text: str):
        if not self._app or not self._loop:
            logger.warning("Bot not started — cannot send message")
            return
        async def _send():
            await self._app.bot.send_message(chat_id=chat_id, text=text)
        asyncio.run_coroutine_threadsafe(_send(), self._loop)

    @property
    def is_running(self) -> bool:
        return self._running


# ── Public facade ──────────────────────────────────────────────────────────────

class JarvisTelegramBot:
    """
    Facade. Selects real PTB bot if token available + lib installed; else Mock.
    """

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if _PTB_AVAILABLE and self.token and self.token != "MOCK_TOKEN":
            self._bot = _PTBBot(self.token)
            self._backend_name = "ptb"
        else:
            self._bot = MockTelegramBot(self.token or "MOCK_TOKEN")
            self._backend_name = "mock"
        logger.info("JarvisTelegramBot backend: %s", self._backend_name)

    @property
    def backend_name(self) -> str:
        return self._backend_name

    def start(self):
        """Start the bot (blocking for PTB, non-blocking for mock)."""
        self._bot.start()

    def stop(self):
        """Stop the bot gracefully."""
        self._bot.stop()

    def send_message(self, chat_id: int | str, text: str):
        """Send a message to a Telegram chat."""
        self._bot.send_message(chat_id, text)

    @property
    def is_running(self) -> bool:
        return self._bot.is_running
