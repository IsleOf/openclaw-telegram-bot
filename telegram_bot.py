#!/usr/bin/env python3
"""
Claw Telegram Bot — Voice-Enabled

Replaces OpenClaw's Telegram integration with a Python-native bot that:
  - Handles voice messages: Whisper transcription → LLM rewrite → AI response
  - Handles text messages: directly through the CLI Router
  - Manages per-chat conversation history (last 20 exchanges)
  - Supports /clear, /lang, /status commands
  - Auto-detects Estonian / English in voice messages

Setup:
  export TELEGRAM_BOT_TOKEN="your_token_here"
  export GROQ_API_KEY="your_groq_key"  # optional but recommended
  python3 telegram_bot.py

Dependencies:
  pip install python-telegram-bot groq requests faster-whisper
"""
import asyncio
import json
import logging
import os
import re
import sys
import time
import tempfile
from collections import defaultdict, deque

import requests
from telegram import Update, constants
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

# ─── Config ──────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
ROUTER_URL = os.environ.get('ROUTER_URL', 'http://localhost:4097/v1/chat/completions')
ROUTER_MODEL = os.environ.get('ROUTER_MODEL', 'opencode/minimax-m2.5-free')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
WHISPER_MODEL = os.environ.get('WHISPER_MODEL', 'small')
ALLOWED_CHAT_IDS = set(
    int(x) for x in os.environ.get('ALLOWED_CHAT_IDS', '').split(',') if x.strip()
)  # empty = allow all

# Path to voice_transcribe.py (same dir as this file)
TRANSCRIBE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'voice_transcribe.py')

# System prompt for the AI
SYSTEM_PROMPT = """You are Claw 🦞, a direct and resourceful AI assistant. User: DaN.
Be direct, concise, and opinionated. Do the task — don't describe what you could do.
When given web search results or tool output, synthesize them into a useful answer.
Never list your capabilities. Just help."""

# ─── Conversation history ─────────────────────────────────────────────────────
# Per-chat, keep last 20 exchanges (40 messages: 20 user + 20 assistant)
HISTORY: dict = defaultdict(lambda: deque(maxlen=40))

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/telegram_bot.log'),
    ]
)
log = logging.getLogger(__name__)


# ─── Router call ─────────────────────────────────────────────────────────────

def call_router(chat_history: list, timeout=300) -> str:
    """Send conversation to CLI Router v6 and return response."""
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}] + list(chat_history)
    try:
        r = requests.post(
            ROUTER_URL,
            json={'model': ROUTER_MODEL, 'stream': False, 'messages': messages},
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()['choices'][0]['message']['content'].strip()
    except requests.Timeout:
        return 'Still thinking — free model is slow. Try again in a moment.'
    except Exception as e:
        log.error('Router error: %s', e)
        return f'Router error: {e}'


# ─── Voice processing ─────────────────────────────────────────────────────────

def download_tg_file(file_id: str, suffix: str = '.ogg') -> str:
    """Download a Telegram file, return local temp path."""
    r = requests.get(
        f'https://api.telegram.org/bot{BOT_TOKEN}/getFile',
        params={'file_id': file_id}, timeout=15,
    )
    r.raise_for_status()
    tg_path = r.json()['result']['file_path']
    url = f'https://api.telegram.org/file/bot{BOT_TOKEN}/{tg_path}'

    r2 = requests.get(url, timeout=60, stream=True)
    r2.raise_for_status()

    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    for chunk in r2.iter_content(8192):
        tmp.write(chunk)
    tmp.close()
    return tmp.name


def transcribe_audio(audio_path: str) -> dict:
    """
    Call voice_transcribe.py as subprocess.
    Returns dict with: text, organized, language, backend, changed
    """
    env = os.environ.copy()
    env['GROQ_API_KEY'] = GROQ_API_KEY
    env['ROUTER_URL'] = ROUTER_URL
    env['ROUTER_MODEL'] = ROUTER_MODEL
    env['WHISPER_MODEL'] = WHISPER_MODEL

    result = __import__('subprocess').run(
        [sys.executable, TRANSCRIBE_SCRIPT, '--file', audio_path],
        capture_output=True, text=True, timeout=180, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f'Transcription failed: {result.stderr[:300]}')

    return json.loads(result.stdout)


# ─── Auth check ───────────────────────────────────────────────────────────────

def is_allowed(update: Update) -> bool:
    if not ALLOWED_CHAT_IDS:
        return True
    return update.effective_chat.id in ALLOWED_CHAT_IDS


# ─── Handlers ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '🦞 *Claw online*\n\n'
        'Send text or voice messages. Voice is auto-transcribed (🇪🇪 / 🇬🇧).\n\n'
        'Commands:\n'
        '• /clear — reset conversation history\n'
        '• /lang — language detection info\n'
        '• /status — system status',
        parse_mode='Markdown',
    )


async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    HISTORY[update.effective_chat.id].clear()
    await update.message.reply_text('🗑️ History cleared.')


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    history_len = len(HISTORY[chat_id]) // 2
    backend = 'Groq/whisper-large-v3' if GROQ_API_KEY else f'faster-whisper/{WHISPER_MODEL}'
    status = (
        f'🦞 *Claw Status*\n\n'
        f'• Router: `{ROUTER_URL}`\n'
        f'• Model: `{ROUTER_MODEL}`\n'
        f'• Voice: `{backend}`\n'
        f'• History: {history_len} exchanges\n'
        f'• Chat ID: `{chat_id}`'
    )
    await update.message.reply_text(status, parse_mode='Markdown')


async def cmd_lang(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '🎙️ *Voice language detection*\n\n'
        'Estonian 🇪🇪 detected by: ä, ö, ü, õ, š, ž characters or common Estonian words.\n'
        'English 🇬🇧 is the default if no Estonian markers found.\n\n'
        'Custom word lists boost recognition of:\n'
        '• Estonian: Riigikogu, kaitsevägi, Tallinn, Tartu, EKRE...\n'
        '• English: OpenClaw, VPS, NATO, Estonia, API...\n\n'
        'Filler words removed automatically (noh, ee, nagu / um, uh, like)',
        parse_mode='Markdown',
    )


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Voice message: download → Whisper → rewrite → Router → reply."""
    if not is_allowed(update):
        return

    chat_id = update.effective_chat.id
    voice = update.message.voice or update.message.audio
    duration = getattr(voice, 'duration', '?')

    # Show processing status
    status_msg = await update.message.reply_text(f'🎙️ Transcribing ({duration}s)...')

    try:
        # Download
        audio_path = download_tg_file(voice.file_id, '.ogg')
        log.info('Voice from chat %s: %ss, file downloaded to %s', chat_id, duration, audio_path)

        # Transcribe + rewrite (via voice_transcribe.py subprocess)
        await status_msg.edit_text('🎙️ Processing audio...')
        result = transcribe_audio(audio_path)

        raw = result.get('text', '')
        organized = result.get('organized', raw)
        language = result.get('language', 'en')
        backend = result.get('backend', '?')
        changed = result.get('changed', False)

        lang_flag = '🇪🇪' if language == 'et' else '🇬🇧'
        log.info('Transcribed [%s/%s]: %s', language, backend, raw[:100])

        # Show transcript
        transcript_display = organized if changed else raw
        await status_msg.edit_text(
            f'{lang_flag} _{transcript_display}_',
            parse_mode='Markdown',
        )

        # Process through router as text
        HISTORY[chat_id].append({'role': 'user', 'content': organized})
        thinking_msg = await update.message.reply_text('🤔...')

        response = call_router(list(HISTORY[chat_id]))
        HISTORY[chat_id].append({'role': 'assistant', 'content': response})

        await thinking_msg.delete()
        # Split long responses for Telegram's 4096 char limit
        for chunk in _split_message(response):
            await update.message.reply_text(chunk)

    except Exception as e:
        log.error('Voice handler error: %s', e, exc_info=True)
        await status_msg.edit_text(f'❌ Voice error: {e}')


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Text message: add to history → Router → reply."""
    if not is_allowed(update):
        return

    chat_id = update.effective_chat.id
    text = update.message.text or ''
    if not text:
        return

    log.info('Text from chat %s: %s', chat_id, text[:80])
    HISTORY[chat_id].append({'role': 'user', 'content': text})

    # Show typing indicator
    await ctx.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)

    response = call_router(list(HISTORY[chat_id]))
    HISTORY[chat_id].append({'role': 'assistant', 'content': response})

    for chunk in _split_message(response):
        await update.message.reply_text(chunk)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _split_message(text: str, limit: int = 4000):
    """Split text into Telegram-safe chunks."""
    if len(text) <= limit:
        yield text
        return
    # Split at paragraph boundaries
    paragraphs = text.split('\n\n')
    chunk = ''
    for para in paragraphs:
        if len(chunk) + len(para) + 2 > limit:
            if chunk:
                yield chunk.strip()
            chunk = para
        else:
            chunk = chunk + '\n\n' + para if chunk else para
    if chunk:
        yield chunk.strip()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        print('ERROR: Set TELEGRAM_BOT_TOKEN environment variable', file=sys.stderr)
        sys.exit(1)

    log.info('Starting Claw Telegram Bot...')
    log.info('Router: %s | Model: %s', ROUTER_URL, ROUTER_MODEL)
    log.info('Voice backend: %s', 'Groq' if GROQ_API_KEY else f'faster-whisper/{WHISPER_MODEL}')

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('clear', cmd_clear))
    app.add_handler(CommandHandler('status', cmd_status))
    app.add_handler(CommandHandler('lang', cmd_lang))

    # Voice / audio messages
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

    # Text messages (not commands)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info('Bot running. Press Ctrl+C to stop.')
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
