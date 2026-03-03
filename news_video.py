#!/usr/bin/env python3
"""
Estonia News Video Generator

Pipeline:
  1. Fetch Estonia news via web_search.py
  2. LLM generates a ~60s Estonian voiceover script
  3. edge-tts (et-EE-AnuNeural) → audio + word-level timestamps
  4. Pillow renders frames: current word large+white, context words dimmer
  5. ffmpeg pipes frames + audio → MP4
  6. Sends video to Telegram

Usage:
  TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy \
    ROUTER_URL=http://localhost:4097/v1/chat/completions \
    python3 news_video.py
"""
import asyncio, json, os, re, subprocess, sys, tempfile, time
from pathlib import Path
import requests

# ─── CLI args (allow natural-language invocation from telegram_bot.py) ────────
import argparse as _ap
_parser = _ap.ArgumentParser(add_help=False)
_parser.add_argument('--topic',   default='')   # what to make video about
_parser.add_argument('--chat-id', default='')   # override TELEGRAM_CHAT_ID
_ARGS, _ = _parser.parse_known_args()

# ─── Config ──────────────────────────────────────────────────────────────────
SKILLS_DIR  = Path.home() / '.openclaw/workspace/skills/web-browser/scripts'
WEB_SEARCH  = str(SKILLS_DIR / 'web_search.py')
BOT_TOKEN   = os.environ.get('TELEGRAM_BOT_TOKEN', '')
CHAT_ID     = _ARGS.chat_id or os.environ.get('TELEGRAM_CHAT_ID', '')
ROUTER_URL  = os.environ.get('ROUTER_URL',  'http://localhost:4097/v1/chat/completions')
ROUTER_MODEL= os.environ.get('ROUTER_MODEL','opencode/minimax-m2.5-free')
VOICE       = 'et-EE-KalleNeural'  # male Estonian neural TTS
VOICE_PITCH = '-15Hz'              # lower pitch for baritone effect
TOPIC       = _ARGS.topic          # '' = default Estonia news
GOOGLE_AI_KEY = os.environ.get('GOOGLE_AI_KEY', '')  # Gemini for better Estonian

# ─── Video params ─────────────────────────────────────────────────────────────
FPS    = 25
WIDTH  = 1280
HEIGHT = 720
FONT   = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

# Colours
BG_TOP     = (10, 12, 28)
BG_BOT     = (6, 8, 18)
EST_BLUE   = (0, 114, 206)
EST_BLACK  = (0, 0, 0)
EST_WHITE  = (255, 255, 255)
COL_CUR    = (255, 255, 255)      # current word
COL_NEAR   = (160, 170, 200)      # ±1 word
COL_FAR    = (70, 78, 110)        # ±2 word
COL_TICKER = (130, 145, 190)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def web_search(query: str, n: int = 8) -> list:
    try:
        r = subprocess.run(
            ['python3', WEB_SEARCH, '--query', query, '--max-results', str(n)],
            capture_output=True, text=True, timeout=30, cwd=str(Path.home())
        )
        return json.loads(r.stdout) if r.stdout.strip() else []
    except Exception as e:
        print(f'[search error] {e}', file=sys.stderr)
        return []


def call_llm(user_msg: str, system: str) -> str:
    # Use Gemini when key is available (better multilingual quality)
    if GOOGLE_AI_KEY:
        try:
            r = requests.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/'
                f'gemini-2.0-flash:generateContent?key={GOOGLE_AI_KEY}',
                json={
                    'systemInstruction': {'parts': [{'text': system}]},
                    'contents': [{'parts': [{'text': user_msg}]}],
                    'generationConfig': {'temperature': 0.7, 'maxOutputTokens': 512},
                },
                timeout=60,
            )
            r.raise_for_status()
            return r.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        except Exception as e:
            print(f'[gemini error] {e} — falling back to router', file=sys.stderr)

    # Fallback: CLI Router
    try:
        r = requests.post(
            ROUTER_URL,
            json={
                'model': ROUTER_MODEL,
                'stream': False,
                'messages': [
                    {'role': 'system', 'content': system},
                    {'role': 'user',   'content': user_msg},
                ],
            },
            timeout=120,
        )
        r.raise_for_status()
        return r.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        return f'LLM error: {e}'


def load_font(size: int):
    from PIL import ImageFont
    if os.path.exists(FONT):
        try:
            return ImageFont.truetype(FONT, size)
        except Exception:
            pass
    return ImageFont.load_default()


# ─── Step 1: news ─────────────────────────────────────────────────────────────

def fetch_news(topic: str = '') -> str:
    today = time.strftime('%B %d %Y')
    if topic:
        # Topic-driven: search for what the user asked about
        items  = web_search(f'{topic} news {today}', n=7)
        items += web_search(f'{topic} Eesti uudised', n=4)
    else:
        # Default: latest Estonia news
        items  = web_search(f'Estonia news today {today}', n=7)
        items += web_search('Eesti uudised täna ERR Postimees', n=5)
    seen, lines = set(), []
    for it in items:
        t = it.get('title', '').strip()
        s = it.get('snippet', '').strip()[:250]
        if t and t not in seen:
            seen.add(t)
            lines.append(f'- {t}\n  {s}')
    return '\n\n'.join(lines[:10])


# ─── Step 2: Estonian script ──────────────────────────────────────────────────

def make_estonian_script(news: str, topic: str = '') -> str:
    system = (
        'Sa oled Eesti teleuudiste diktor. Kirjuta loomulik, selge eestikeelne uudistekst. '
        'Ära kasuta numbreid, hashtage ega kirjavahemärke peale punkti ja koma. '
        'Ainult lihtlausetest koosnev, kõnesobilik tekst.'
    )
    topic_line = f'Teema: {topic}.\n\n' if topic else ''
    prompt = (
        f'{topic_line}Uudised:\n\n{news}\n\n'
        f'Kirjuta 60-sekundiline eestikeelne uudistesaate tekst. '
        f'Maksimaalselt 120 sõna. Alusta kohe uudistega, ilma tervituseta.'
    )
    return call_llm(prompt, system)


# ─── Step 3: TTS + word timestamps ───────────────────────────────────────────

def align_words_to_script(script_text: str, whisper_timings: list) -> list:
    """
    Map original script words to whisper timestamps via proportional alignment.
    Whisper timing is accurate; whisper text is not (transcription errors).
    We keep timing from whisper but display the original script words.
    """
    orig_words = re.findall(r'\S+', script_text)
    if not orig_words or not whisper_timings:
        return whisper_timings

    n_orig = len(orig_words)
    n_wh   = len(whisper_timings)
    result = []

    for i, word in enumerate(orig_words):
        # Map original word index proportionally into whisper timing range
        wh_lo = int(i * n_wh / n_orig)
        wh_hi = int((i + 1) * n_wh / n_orig) - 1
        wh_hi = max(wh_lo, min(wh_hi, n_wh - 1))

        start = whisper_timings[wh_lo][0]
        end   = whisper_timings[wh_hi][1]
        result.append((start, end, word))

    return result


async def generate_tts(text: str, audio_path: str) -> list:
    """
    Generate TTS audio, then use faster-whisper to get word-level timestamps.
    Returns list of (start_s, end_s, word) tuples using ORIGINAL script words.
    """
    import edge_tts

    # Step A: Generate audio via edge-tts (male voice, lowered pitch for baritone)
    communicate = edge_tts.Communicate(text, voice=VOICE, pitch=VOICE_PITCH)
    with open(audio_path, 'wb') as af:
        async for chunk in communicate.stream():
            if chunk['type'] == 'audio':
                af.write(chunk['data'])

    # Step B: Convert MP3 → 16kHz mono WAV for Whisper
    wav_path = audio_path.replace('.mp3', '.wav')
    subprocess.run(
        ['ffmpeg', '-y', '-i', audio_path, '-ar', '16000', '-ac', '1', wav_path],
        capture_output=True, check=True
    )

    # Step C: faster-whisper for timing only (text from original script)
    print('     Running faster-whisper for word timestamps...')
    from faster_whisper import WhisperModel
    model = WhisperModel('small', device='cpu', compute_type='int8')
    segments, _ = model.transcribe(
        wav_path,
        language='et',
        word_timestamps=True,
        vad_filter=True,
    )

    whisper_timings = []
    for seg in segments:
        if seg.words:
            for w in seg.words:
                whisper_timings.append((w.start, w.end, w.word.strip()))

    # Step D: Replace whisper words with original script words, keep timing
    n_script = len(text.split())
    print(f'     Aligning {n_script} script words → {len(whisper_timings)} whisper timestamps...')
    return align_words_to_script(text, whisper_timings)


# ─── Step 4+5: Render frames → ffmpeg ─────────────────────────────────────────

def current_word_idx(timings: list, t: float) -> int:
    """Index of the word being spoken at time t."""
    for i, (s, e, _) in enumerate(timings):
        if s <= t <= e:
            return i
    # Between words: find next upcoming
    for i, (s, _, _) in enumerate(timings):
        if s > t:
            return max(0, i - 1)
    return len(timings) - 1


def build_background() -> bytes:
    """Pre-render background gradient as raw RGB bytes."""
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        r_ratio = y / HEIGHT
        r = int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * r_ratio)
        g = int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * r_ratio)
        b = int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * r_ratio)
        draw.line([(0, y), (WIDTH-1, y)], fill=(r, g, b))
    # Estonian flag stripe at top (8px each: blue | black | white)
    draw.rectangle([0,  0, WIDTH,  8], fill=EST_BLUE)
    draw.rectangle([0,  8, WIDTH, 16], fill=EST_BLACK)
    draw.rectangle([0, 16, WIDTH, 24], fill=EST_WHITE)
    # Bottom dark bar
    draw.rectangle([0, HEIGHT-48, WIDTH, HEIGHT], fill=(4, 5, 14))
    return img.tobytes()


def render_words(base_bytes: bytes, timings: list, idx: int, date_str: str) -> bytes:
    """Copy background, draw word context, return raw RGB bytes."""
    from PIL import Image, ImageDraw

    img = Image.frombytes('RGB', (WIDTH, HEIGHT), base_bytes)
    draw = ImageDraw.Draw(img)

    cx = WIDTH  // 2
    cy = HEIGHT // 2

    def word_at(offset):
        i = idx + offset
        return timings[i][2] if 0 <= i < len(timings) else ''

    def draw_centered(text, font, color, y):
        if not text:
            return
        bbox = draw.textbbox((0, 0), text, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((cx - w // 2, y - h // 2), text, font=font, fill=color)

    # Load fonts (cached outside for perf — passed as closure via module-level cache)
    f_cur  = load_font(92)
    f_near = load_font(52)
    f_far  = load_font(36)
    f_tick = load_font(22)

    draw_centered(word_at(-2), f_far,  COL_FAR,    cy - 210)
    draw_centered(word_at(-1), f_near, COL_NEAR,   cy - 128)
    draw_centered(word_at( 0), f_cur,  COL_CUR,    cy)
    draw_centered(word_at( 1), f_near, COL_NEAR,   cy + 128)
    draw_centered(word_at( 2), f_far,  COL_FAR,    cy + 200)

    # Ticker
    draw.text((20, HEIGHT - 34), date_str, font=f_tick, fill=COL_TICKER)

    return img.tobytes()


def generate_video(timings: list, audio_path: str, out_path: str) -> bool:
    if not timings:
        print('No word timings.', file=sys.stderr)
        return False

    total_s = timings[-1][1] + 1.0
    total_frames = int(total_s * FPS) + 1
    date_str = time.strftime('Eesti Uudised — %d. %B %Y — claw.ai')

    print(f'Rendering {total_frames} frames ({total_s:.1f}s @ {FPS}fps)...')

    bg = build_background()

    # Font cache: load once, store globally so render_words reuses them
    global _font_cache
    _font_cache = {
        92: load_font(92),
        52: load_font(52),
        36: load_font(36),
        22: load_font(22),
    }

    ffmpeg = subprocess.Popen(
        [
            'ffmpeg', '-y',
            '-f', 'rawvideo', '-vcodec', 'rawvideo',
            '-s', f'{WIDTH}x{HEIGHT}', '-pix_fmt', 'rgb24', '-r', str(FPS),
            '-i', 'pipe:0',
            '-i', audio_path,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '22',
            '-c:a', 'aac', '-b:a', '128k',
            '-pix_fmt', 'yuv420p',
            '-shortest',
            out_path,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    prev_idx = -1
    cached_frame = None

    for n in range(total_frames):
        t   = n / FPS
        idx = current_word_idx(timings, t)

        if idx != prev_idx or cached_frame is None:
            cached_frame = render_words(bg, timings, idx, date_str)
            prev_idx = idx

        try:
            ffmpeg.stdin.write(cached_frame)
        except BrokenPipeError:
            break

        if n % 250 == 0:
            print(f'  frame {n}/{total_frames}  word: "{timings[idx][2]}"', flush=True)

    try:
        ffmpeg.stdin.close()
    except Exception:
        pass
    # Read stderr then wait — avoids the communicate() stdin flush bug
    try:
        err = ffmpeg.stderr.read()
        ffmpeg.wait()
    except Exception:
        try:
            ffmpeg.kill()
        except Exception:
            pass
        err = b''
    if ffmpeg.returncode not in (0, None):
        err_text = err.decode(errors='replace')[-600:]
        if 'Error' in err_text or 'Invalid' in err_text:
            print('ffmpeg stderr:\n' + err_text, file=sys.stderr)
            return False

    mb = os.path.getsize(out_path) / 1024 / 1024
    print(f'Video saved: {out_path} ({mb:.1f} MB)')
    return True


# ─── Step 6: Send to Telegram ─────────────────────────────────────────────────

def send_video(path: str, caption: str):
    if not BOT_TOKEN or not CHAT_ID:
        print(f'No TELEGRAM_BOT_TOKEN/CHAT_ID — video at {path}')
        return
    print('Sending to Telegram...')
    with open(path, 'rb') as f:
        r = requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendVideo',
            data={'chat_id': CHAT_ID, 'caption': caption, 'supports_streaming': 'true'},
            files={'video': ('estonia_news.mp4', f, 'video/mp4')},
            timeout=180,
        )
    if r.ok:
        print('Sent!')
    else:
        print(f'Send failed: {r.text[:300]}', file=sys.stderr)


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    topic = TOPIC  # from --topic arg or empty
    label = f'"{topic}"' if topic else 'Estonia news'
    print(f'=== Eesti Uudiste Videomasin — {label} ===\n')

    # 1. News
    print('1/6  Fetching news...')
    news = fetch_news(topic)
    if not news:
        sys.exit('Could not fetch news.')
    print(f'     Got {news.count(chr(10)) + 1} lines.')

    # 2. Script
    print('2/6  Generating Estonian voiceover script...')
    script = make_estonian_script(news, topic)
    print(f'     Script ({len(script)} chars):\n     {script[:120]}...\n')

    # 3. TTS
    with tempfile.TemporaryDirectory() as tmp:
        audio = os.path.join(tmp, 'voice.mp3')
        out   = os.path.expanduser('~/estonia_news.mp4')

        print(f'3/6  TTS: {VOICE}...')
        timings = await generate_tts(script, audio)
        if not timings:
            sys.exit('TTS produced no word timings.')
        audio_mb = os.path.getsize(audio) / 1024 / 1024
        print(f'     {len(timings)} words, {audio_mb:.2f} MB audio')

        # 4+5. Video
        print('4/6  Rendering video...')
        ok = generate_video(timings, audio, out)
        if not ok:
            sys.exit('Video generation failed.')

    # 6. Send
    caption_topic = topic if topic else 'Eesti uudised'
    caption = f'{caption_topic} — {time.strftime("%d. %B %Y")}'
    print('5/6  Sending to Telegram...')
    send_video(out, caption)
    print('\nDone.')


if __name__ == '__main__':
    asyncio.run(main())
