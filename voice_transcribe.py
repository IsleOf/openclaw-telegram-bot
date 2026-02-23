#!/usr/bin/env python3
"""
Voice Transcription Engine — WhisperFlow-style

Handles audio transcription for the Telegram bot with:
- Dual-backend: Groq Whisper API (fast, free) or faster-whisper local (offline)
- Automatic Estonian / English language detection
- Custom word library biasing for improved domain recognition
- Rambling-to-organized rewriter via LLM router

Usage (standalone):
  python3 voice_transcribe.py --file audio.ogg
  python3 voice_transcribe.py --file_id BQACAgEA... --token YOUR_BOT_TOKEN
  python3 voice_transcribe.py --file audio.ogg --no-rewrite

Output: JSON {"text": "...", "organized": "...", "language": "et", "backend": "groq"}
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

import requests

# ─── Config ──────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
ROUTER_URL = os.environ.get('ROUTER_URL', 'http://localhost:4097/v1/chat/completions')
ROUTER_MODEL = os.environ.get('ROUTER_MODEL', 'opencode/minimax-m2.5-free')
WHISPER_MODEL = os.environ.get('WHISPER_MODEL', 'small')   # tiny/base/small/medium
WORD_LISTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'word_lists')

# Estonian filler words to clean in rewriting
ESTONIAN_FILLERS = ['noh', 'ee', 'eem', 'nagu', 'siis', 'tähendab', 'vaata',
                    'kuule', 'niiöelda', 'ütleme', 'nii et']
ENGLISH_FILLERS = ['um', 'uh', 'like', 'you know', 'basically', 'literally',
                   'actually', 'I mean', 'kind of', 'sort of']


# ─── Word lists ───────────────────────────────────────────────────────────────

def load_word_list(filename, max_words=50):
    """Load domain-specific word list for Whisper initial_prompt biasing."""
    path = os.path.join(WORD_LISTS_DIR, filename)
    words = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    words.extend(line.split())
    return words[:max_words]


def build_initial_prompt(language_hint=None):
    """
    Build Whisper initial_prompt from both word lists.
    The initial_prompt acts as fake preceding text — Whisper biases toward
    words/spelling that appear in it. Use domain terms, proper nouns, place names.
    """
    est_words = load_word_list('estonian.txt', max_words=40)
    en_words = load_word_list('english.txt', max_words=30)

    if language_hint == 'et':
        # Lean heavily Estonian
        words = est_words + en_words[:10]
        prefix = 'Eesti keeles räägitud tekst. '
    elif language_hint == 'en':
        words = en_words + est_words[:10]
        prefix = 'Spoken in English. '
    else:
        words = est_words[:25] + en_words[:25]
        prefix = ''

    return prefix + ', '.join(words)


# ─── Audio download ───────────────────────────────────────────────────────────

def download_telegram_file(file_id, bot_token):
    """Download a Telegram file by file_id. Returns local path."""
    r = requests.get(
        f'https://api.telegram.org/bot{bot_token}/getFile',
        params={'file_id': file_id}, timeout=15
    )
    r.raise_for_status()
    tg_path = r.json()['result']['file_path']
    url = f'https://api.telegram.org/file/bot{bot_token}/{tg_path}'

    r2 = requests.get(url, timeout=60, stream=True)
    r2.raise_for_status()

    ext = os.path.splitext(tg_path)[1] or '.ogg'
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    for chunk in r2.iter_content(8192):
        tmp.write(chunk)
    tmp.close()
    return tmp.name


def convert_to_wav(input_path):
    """Convert audio to 16kHz mono WAV using ffmpeg (Whisper preferred format)."""
    out_path = input_path.rsplit('.', 1)[0] + '_converted.wav'
    cmd = ['ffmpeg', '-y', '-i', input_path, '-ar', '16000', '-ac', '1',
           '-f', 'wav', out_path]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode != 0:
        # ffmpeg failed, try to use original
        return input_path
    return out_path


# ─── Language detection ───────────────────────────────────────────────────────

def detect_language_heuristic(text):
    """Quick heuristic before/without Whisper language detection."""
    est_chars = set('äöüõšžÄÖÜÕŠŽ')
    est_common = {'ja', 'on', 'ei', 'see', 'et', 'aga', 'ning', 'kas', 'mis',
                  'nii', 'kui', 'ma', 'ta', 'me', 'te', 'nad', 'seda', 'olen',
                  'pole', 'saab', 'peaks', 'tahab', 'ütles', 'noh', 'nagu'}
    lower = text.lower()
    if any(c in lower for c in est_chars):
        return 'et'
    words = set(re.findall(r'\b\w+\b', lower))
    if len(words & est_common) >= 2:
        return 'et'
    return 'en'


# ─── Transcription backends ───────────────────────────────────────────────────

def transcribe_groq(audio_path, language_hint=None):
    """
    Groq Whisper API — free tier, whisper-large-v3, ~real-time speed.
    Free limits: 7200 audio seconds/day.
    Requires: pip install groq
    """
    try:
        from groq import Groq
    except ImportError:
        raise RuntimeError('groq package not installed: pip install groq')

    client = Groq(api_key=GROQ_API_KEY)
    prompt = build_initial_prompt(language_hint)

    with open(audio_path, 'rb') as f:
        response = client.audio.transcriptions.create(
            file=(os.path.basename(audio_path), f),
            model='whisper-large-v3',
            prompt=prompt,
            response_format='verbose_json',
            language=language_hint,   # None = auto-detect
        )

    text = response.text.strip()
    lang = getattr(response, 'language', None) or detect_language_heuristic(text)
    return {'text': text, 'language': lang, 'backend': 'groq/whisper-large-v3'}


def transcribe_local(audio_path, language_hint=None):
    """
    faster-whisper local — offline, CPU, uses WHISPER_MODEL env var.
    Model sizes and approx RAM on CPU:
      tiny  ~75MB   ~0.5s/s audio (poor Estonian)
      base  ~142MB  ~1s/s audio
      small ~244MB  ~3s/s audio (good balance) ← default
      medium ~769MB ~8s/s audio (best accuracy)
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError('faster-whisper not installed: pip install faster-whisper')

    prompt = build_initial_prompt(language_hint)

    # Cache model globally to avoid reloading on every call
    global _whisper_model, _whisper_model_size
    model_size = WHISPER_MODEL
    if not globals().get('_whisper_model') or globals().get('_whisper_model_size') != model_size:
        _whisper_model = WhisperModel(model_size, device='cpu', compute_type='int8')
        _whisper_model_size = model_size

    segments, info = _whisper_model.transcribe(
        audio_path,
        language=language_hint,   # None = auto-detect
        initial_prompt=prompt,
        beam_size=5,
        vad_filter=True,           # skip silence (faster)
        vad_parameters={'min_silence_duration_ms': 500},
        word_timestamps=False,
    )
    text = ' '.join(s.text.strip() for s in segments).strip()
    lang = info.language or detect_language_heuristic(text)
    return {'text': text, 'language': lang, 'backend': f'faster-whisper/{model_size}'}


def transcribe(audio_path, language_hint=None, cleanup=True):
    """
    Main transcription entry point. Tries Groq first, falls back to local.
    audio_path: local path to audio file (OGG, WAV, MP3, M4A...)
    language_hint: 'et' / 'en' / None (auto)
    """
    wav_path = None
    try:
        # Convert to WAV for best compatibility
        wav_path = convert_to_wav(audio_path)

        if GROQ_API_KEY:
            result = transcribe_groq(wav_path, language_hint)
        else:
            result = transcribe_local(wav_path, language_hint)

        # Ensure language is detected
        if not result.get('language'):
            result['language'] = detect_language_heuristic(result['text'])

        return result

    finally:
        if cleanup:
            for p in [audio_path, wav_path]:
                if p and os.path.exists(p) and p != audio_path:
                    try:
                        os.unlink(p)
                    except Exception:
                        pass
            if cleanup and os.path.exists(audio_path):
                try:
                    os.unlink(audio_path)
                except Exception:
                    pass


# ─── Text rewriter ─────────────────────────────────────────────────────────────

def rewrite_transcript(raw_text, language):
    """
    Turn raw speech-to-text into organized text via LLM.
    Removes fillers, fixes repetitions, groups thoughts, preserves language.
    """
    lang_name = {'et': 'Estonian', 'en': 'English'}.get(language, 'the same language as the input')
    fillers = ESTONIAN_FILLERS if language == 'et' else ENGLISH_FILLERS
    filler_str = ', '.join(f'"{w}"' for w in fillers[:8])

    prompt = (
        f'You are a voice transcript editor. The following is raw speech-to-text in {lang_name}.\n'
        f'Task: rewrite it into clear, organized text.\n'
        f'Rules:\n'
        f'- Remove filler words/sounds: {filler_str}\n'
        f'- Remove repetitions and false starts\n'
        f'- Fix sentence structure and punctuation\n'
        f'- Group related thoughts into coherent sentences\n'
        f'- Keep the original language ({lang_name})\n'
        f'- Keep the meaning exactly — do not add or invent content\n'
        f'- Output ONLY the cleaned text, nothing else\n\n'
        f'Raw transcript:\n{raw_text}'
    )

    try:
        r = requests.post(
            ROUTER_URL,
            json={
                'model': ROUTER_MODEL,
                'stream': False,
                'messages': [{'role': 'user', 'content': prompt}],
            },
            timeout=90,
        )
        r.raise_for_status()
        organized = r.json()['choices'][0]['message']['content'].strip()
        # Sanity check — if LLM returned something very short/wrong, use raw
        if len(organized) > 10 and len(organized) > len(raw_text) * 0.3:
            return organized
        return raw_text
    except Exception:
        return raw_text   # fallback: return raw transcript unchanged


# ─── CLI interface ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Transcribe audio with Whisper + rewrite')
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument('--file', help='Local audio file path')
    src.add_argument('--file_id', help='Telegram file_id (requires --token)')
    parser.add_argument('--token', help='Telegram bot token (for --file_id)')
    parser.add_argument('--lang', default=None, choices=['et', 'en'],
                        help='Force language (default: auto-detect)')
    parser.add_argument('--no-rewrite', action='store_true',
                        help='Skip LLM rewriting step')
    parser.add_argument('--model', default=None,
                        help='Whisper model size (tiny/base/small/medium)')
    args = parser.parse_args()

    if args.model:
        WHISPER_MODEL = args.model

    # Get audio file
    if args.file_id:
        if not args.token:
            print('ERROR: --token required with --file_id', file=sys.stderr)
            sys.exit(1)
        audio = download_telegram_file(args.file_id, args.token)
    else:
        audio = args.file
        if not os.path.exists(audio):
            print(f'ERROR: file not found: {audio}', file=sys.stderr)
            sys.exit(1)

    # Transcribe
    result = transcribe(audio, language_hint=args.lang, cleanup=(args.file_id is not None))

    raw = result['text']
    lang = result['language']
    backend = result.get('backend', 'unknown')

    # Rewrite
    organized = raw
    if not args.no_rewrite and raw:
        organized = rewrite_transcript(raw, lang)

    output = {
        'text': raw,
        'organized': organized,
        'language': lang,
        'backend': backend,
        'changed': organized != raw,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
