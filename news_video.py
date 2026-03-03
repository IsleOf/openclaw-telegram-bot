#!/usr/bin/env python3
"""
Claw News Video — TikTok Edition (9:16)

Pipeline:
  1. Fetch news via web_search.py
  2. Gemini 2.0 Flash generates ~60s Estonian voiceover script (Cyrillic-safe)
  3. TartuNLP public API (tambet — deep male Estonian neural voice) → WAV audio
  4. faster-whisper → word timestamps
  5. Original script words aligned to whisper timestamps
  6. Pillow renders 720x1280 TikTok frames:
       - Cinematic dark background (bokeh orbs + optional real image)
       - Montserrat ExtraBold font (auto-downloaded)
       - Word entrance scale animation + glow
       - Progress bar, brand bar, Estonian flag stripe
  7. ffmpeg pipes frames + audio → MP4
  8. Sends video to Telegram

Usage:
  TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy GOOGLE_AI_KEY=zzz \\
    ROUTER_URL=http://localhost:4097/v1/chat/completions \\
    python3 news_video.py [--topic "global AI news"] [--chat-id 12345]
"""
import asyncio, json, math, os, re, subprocess, sys, tempfile, time, unicodedata
from pathlib import Path
import requests

# ─── CLI args ─────────────────────────────────────────────────────────────────
import argparse as _ap
_parser = _ap.ArgumentParser(add_help=False)
_parser.add_argument('--topic',   default='')
_parser.add_argument('--chat-id', default='')
_ARGS, _ = _parser.parse_known_args()

# ─── Config ───────────────────────────────────────────────────────────────────
SKILLS_DIR    = Path.home() / '.openclaw/workspace/skills/web-browser/scripts'
WEB_SEARCH    = str(SKILLS_DIR / 'web_search.py')
BOT_TOKEN     = os.environ.get('TELEGRAM_BOT_TOKEN', '')
CHAT_ID       = _ARGS.chat_id or os.environ.get('TELEGRAM_CHAT_ID', '')
ROUTER_URL    = os.environ.get('ROUTER_URL',  'http://localhost:4097/v1/chat/completions')
ROUTER_MODEL  = os.environ.get('ROUTER_MODEL', 'opencode/minimax-m2.5-free')
GOOGLE_AI_KEY = os.environ.get('GOOGLE_AI_KEY', '')   # for script generation only
# TartuNLP TTS — free public API, native Estonian neural synthesis
# Male speakers: albert, indrek, kalev, luukas, meelis, peeter, tambet
# Female:        kylli, lee, liivika, mari, vesta
TARTUNLP_URL     = 'https://api.tartunlp.ai/text-to-speech/v2'
TARTUNLP_SPEAKER = os.environ.get('TARTUNLP_SPEAKER', 'tambet')  # deep male voice
TARTUNLP_SPEED   = float(os.environ.get('TARTUNLP_SPEED', '0.95'))
TOPIC            = _ARGS.topic

# ─── Video params — TikTok 9:16 ───────────────────────────────────────────────
FPS    = 25
WIDTH  = 720
HEIGHT = 1280

# ─── Font system (Montserrat ExtraBold, auto-downloaded) ──────────────────────
_FONT_CACHE_DIR  = os.path.expanduser('~/.openclaw/fonts')
_MONTSERRAT_PATH = os.path.join(_FONT_CACHE_DIR, 'Montserrat-ExtraBold.ttf')
_MONTSERRAT_URL  = (
    'https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/'
    'Montserrat-ExtraBold.ttf'
)
_FONT_FALLBACKS = [
    '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
]
_PIL_FONT_CACHE: dict = {}
_BASE_FONT_PATH: str = ''


def _resolve_font() -> str:
    global _BASE_FONT_PATH
    if _BASE_FONT_PATH:
        return _BASE_FONT_PATH

    if not os.path.exists(_MONTSERRAT_PATH):
        os.makedirs(_FONT_CACHE_DIR, exist_ok=True)
        print('     Downloading Montserrat ExtraBold font...')
        try:
            r = requests.get(_MONTSERRAT_URL, timeout=30)
            r.raise_for_status()
            with open(_MONTSERRAT_PATH, 'wb') as f:
                f.write(r.content)
            print('     Font downloaded.')
        except Exception as e:
            print(f'     Font download failed: {e}', file=sys.stderr)

    if os.path.exists(_MONTSERRAT_PATH):
        _BASE_FONT_PATH = _MONTSERRAT_PATH
        return _BASE_FONT_PATH

    for p in _FONT_FALLBACKS:
        if os.path.exists(p):
            _BASE_FONT_PATH = p
            print(f'     Using fallback font: {p}')
            return _BASE_FONT_PATH

    _BASE_FONT_PATH = ''
    return ''


def load_font(size: int):
    if size in _PIL_FONT_CACHE:
        return _PIL_FONT_CACHE[size]
    from PIL import ImageFont
    path = _resolve_font()
    font = None
    if path:
        try:
            font = ImageFont.truetype(path, size)
        except Exception:
            pass
    if font is None:
        font = ImageFont.load_default()
    _PIL_FONT_CACHE[size] = font
    return font


# ─── Color palette (cinematic dark news broadcast) ────────────────────────────
COL_BG_TOP   = (3,   5,  18)
COL_BG_BOT   = (8,   3,  24)
COL_CUR      = (255, 255, 255)
COL_NEAR     = (145, 175, 230)
COL_FAR      = (50,  65,  105)
COL_ACCENT   = (0,   190, 255)
COL_GLOW     = (0,   110, 200)
COL_TICKER   = (90,  125, 180)
COL_PROG_BG  = (20,  32,   58)
COL_BRAND    = (0,   160, 240)
EST_BLUE     = (0,   114, 206)
EST_BLACK    = (0,     0,   0)
EST_WHITE    = (255, 255, 255)

# ─── Helpers ──────────────────────────────────────────────────────────────────

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
    """Script generation: Gemini 2.0 Flash first, router fallback."""
    if GOOGLE_AI_KEY:
        try:
            r = requests.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/'
                f'gemini-2.0-flash:generateContent?key={GOOGLE_AI_KEY}',
                json={
                    'systemInstruction': {'parts': [{'text': system}]},
                    'contents':          [{'parts': [{'text': user_msg}]}],
                    'generationConfig':  {'temperature': 0.7, 'maxOutputTokens': 512},
                },
                timeout=60,
            )
            r.raise_for_status()
            return r.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        except Exception as e:
            print(f'[gemini] {e} — falling back to router', file=sys.stderr)
    try:
        r = requests.post(
            ROUTER_URL,
            json={
                'model': ROUTER_MODEL, 'stream': False,
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


# ─── Step 1: News ─────────────────────────────────────────────────────────────

def fetch_news(topic: str = '') -> str:
    today = time.strftime('%B %d %Y')
    if topic:
        items  = web_search(f'{topic} news {today}', n=7)
        items += web_search(f'{topic} Eesti uudised', n=4)
    else:
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

def _strip_cyrillic(text: str) -> str:
    """Remove any Cyrillic characters (MiniMax sometimes code-switches to Russian)."""
    cleaned = ''.join(
        c for c in text
        if 'CYRILLIC' not in unicodedata.name(c, '')
    )
    if len(cleaned) < len(text) * 0.8:
        print(f'[warn] Stripped {len(text)-len(cleaned)} Cyrillic chars from script', file=sys.stderr)
    return cleaned.strip()


def make_estonian_script(news: str, topic: str = '') -> str:
    system = (
        'Sa oled Eesti teleuudiste diktor. '
        'Kirjuta loomulik, selge eestikeelne uudistekst AINULT LADINA TÄHESTIKUS. '
        'Eesti tähed (ä, ö, ü, õ, š, ž) on lubatud. '
        'KEELATUD: kürillikaalftähestik, vene keel, numbrid, hashtag\'id. '
        'Kasuta ainult punkte ja komasid. Lihtlaused, kõnesobilik tekst.'
    )
    topic_line = f'Teema: {topic}.\n\n' if topic else ''
    prompt = (
        f'{topic_line}Uudised:\n\n{news}\n\n'
        f'Kirjuta 60-sekundiline eestikeelne uudistesaate tekst. '
        f'Maksimaalselt 120 sõna. Alusta kohe uudistega, ilma tervituseta. '
        f'Kasuta ainult ladina tähestikku.'
    )
    script = call_llm(prompt, system)
    return _strip_cyrillic(script)


# ─── Step 3: TTS + word-level alignment ───────────────────────────────────────

def align_words_to_script(script_text: str, whisper_timings: list) -> list:
    """
    Proportionally map original script words to whisper timestamps.
    Timing from whisper is accurate; text is from the original script.
    """
    orig_words = re.findall(r'\S+', script_text)
    if not orig_words or not whisper_timings:
        return whisper_timings
    n_orig = len(orig_words)
    n_wh   = len(whisper_timings)
    result = []
    for i, word in enumerate(orig_words):
        wh_lo = int(i * n_wh / n_orig)
        wh_hi = int((i + 1) * n_wh / n_orig) - 1
        wh_hi = max(wh_lo, min(wh_hi, n_wh - 1))
        result.append((whisper_timings[wh_lo][0], whisper_timings[wh_hi][1], word))
    return result


async def generate_tts(text: str, audio_path: str) -> list:
    """
    Generate speech via TartuNLP public API (native Estonian neural TTS).
    Speaker: configurable via TARTUNLP_SPEAKER env (default: tambet — deep male).
    Available male voices: albert, indrek, kalev, luukas, meelis, peeter, tambet
    """
    print(f'     TartuNLP speaker: {TARTUNLP_SPEAKER} (speed {TARTUNLP_SPEED})')

    # TartuNLP returns WAV directly — save to wav_path
    wav_path = audio_path.replace('.mp3', '.wav')

    # Split long texts into chunks (API handles ~300 words comfortably)
    # For our ~120-word scripts this is never needed, but split at sentence boundaries
    response = requests.post(
        TARTUNLP_URL,
        json={'text': text, 'speaker': TARTUNLP_SPEAKER, 'speed': TARTUNLP_SPEED},
        timeout=90,
    )
    response.raise_for_status()
    with open(wav_path, 'wb') as f:
        f.write(response.content)

    wav_size = os.path.getsize(wav_path) / 1024
    print(f'     WAV: {wav_size:.0f} KB')

    # Resample to 16kHz mono for faster-whisper
    wav16_path = wav_path.replace('.wav', '_16k.wav')
    subprocess.run(
        ['ffmpeg', '-y', '-i', wav_path, '-ar', '16000', '-ac', '1', wav16_path],
        capture_output=True, check=True,
    )

    # Keep the original WAV for ffmpeg video assembly (better quality)
    # but use the 16kHz version for Whisper
    audio_path_for_ffmpeg = wav_path

    print('     Running faster-whisper for word timestamps...')
    from faster_whisper import WhisperModel
    model = WhisperModel('small', device='cpu', compute_type='int8')
    segments, _ = model.transcribe(
        wav16_path, language='et', word_timestamps=True, vad_filter=True,
    )
    whisper_timings = []
    for seg in segments:
        if seg.words:
            for w in seg.words:
                whisper_timings.append((w.start, w.end, w.word.strip()))

    n_script = len(text.split())
    print(f'     Aligning {n_script} script words to {len(whisper_timings)} timestamps...')

    # Store the wav path for generate_video to use (not .mp3)
    # We write a sentinel file so generate_video knows the real audio path
    _AUDIO_WAV_OVERRIDE[0] = wav_path

    return align_words_to_script(text, whisper_timings)


# Mutable singleton to pass the actual audio path from generate_tts → generate_video
_AUDIO_WAV_OVERRIDE: list = [None]


# ─── Step 4: Background ───────────────────────────────────────────────────────

def _draw_orb(draw, cx: int, cy: int, radius: int, color: tuple, alpha_peak: int = 90):
    steps = 14
    for i in range(steps, 0, -1):
        r = int(radius * i / steps)
        a = int(alpha_peak * math.pow(1 - i / steps, 0.6))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*color, a))


def try_fetch_background_image(topic: str):
    """
    Try Wikipedia then curated Unsplash CDN IDs for a dark background.
    Returns PIL Image (RGB, 720x1280) or None.
    """
    from PIL import Image
    import io

    # 1. Wikipedia page thumbnail
    wiki_map = {
        'ai': 'Artificial intelligence',
        'artificial intelligence': 'Artificial intelligence',
        'estonia': 'Estonia',
        'tech': 'Technology',
        '': 'Artificial intelligence',
    }
    wiki_title = 'Artificial intelligence'
    tl = topic.lower()
    for key, title in wiki_map.items():
        if key and key in tl:
            wiki_title = title
            break
    try:
        r = requests.get(
            'https://en.wikipedia.org/w/api.php',
            params={
                'action': 'query', 'titles': wiki_title,
                'prop': 'pageimages', 'format': 'json', 'pithumbsize': 1200,
            },
            timeout=10,
        )
        r.raise_for_status()
        pages = r.json()['query']['pages']
        img_url = next(iter(pages.values())).get('thumbnail', {}).get('source', '')
        if img_url:
            ir = requests.get(img_url, timeout=15, headers={'User-Agent': 'ClawBot/1.0'})
            if ir.ok and len(ir.content) > 5000:
                img = Image.open(io.BytesIO(ir.content)).convert('RGB')
                img = img.resize((WIDTH, HEIGHT), Image.LANCZOS)
                print(f'     Background: Wikipedia "{wiki_title}"')
                return img
    except Exception as e:
        print(f'[bg/wiki] {e}', file=sys.stderr)

    # 2. Curated Unsplash CDN (dark tech/AI)
    for pid in [
        '1620712943543-bcc4688e7485',
        '1518770660439-4636190af475',
        '1639322537228-f710d846310a',
        '1451187580459-43490279c0fa',
    ]:
        try:
            url = f'https://images.unsplash.com/photo-{pid}?w={WIDTH}&h={HEIGHT}&fit=crop&q=80'
            ir = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            if ir.ok and 'image' in ir.headers.get('Content-Type', '') and len(ir.content) > 10000:
                img = Image.open(io.BytesIO(ir.content)).convert('RGB')
                img = img.resize((WIDTH, HEIGHT), Image.LANCZOS)
                print('     Background: Unsplash')
                return img
        except Exception:
            continue

    return None


def build_background(topic: str = '') -> bytes:
    from PIL import Image, ImageDraw, ImageFilter

    # Gradient base
    base = Image.new('RGB', (WIDTH, HEIGHT))
    d = ImageDraw.Draw(base)
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        col = tuple(
            int(COL_BG_TOP[c] + (COL_BG_BOT[c] - COL_BG_TOP[c]) * ratio)
            for c in range(3)
        )
        d.line([(0, y), (WIDTH - 1, y)], fill=col)

    # Optional real image at dim opacity
    real_img = try_fetch_background_image(topic)
    if real_img:
        ri_rgba = real_img.convert('RGBA')
        dark    = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 12, 200))
        ri_rgba = Image.alpha_composite(ri_rgba, dark)
        img = Image.alpha_composite(base.convert('RGBA'), ri_rgba).convert('RGB')
    else:
        img = base

    # Bokeh orbs
    orb_layer = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    od = ImageDraw.Draw(orb_layer)
    _draw_orb(od, WIDTH // 4,       HEIGHT // 5,       300, (0,  90, 210), alpha_peak=115)
    _draw_orb(od, 3 * WIDTH // 4,   4 * HEIGHT // 5,   340, (85,  0, 170), alpha_peak=100)
    _draw_orb(od, WIDTH // 2,       HEIGHT // 8,       160, (0, 150, 230), alpha_peak=55)
    orb_layer = orb_layer.filter(ImageFilter.GaussianBlur(55))
    img = Image.alpha_composite(img.convert('RGBA'), orb_layer).convert('RGB')

    draw = ImageDraw.Draw(img)

    # Top brand bar (dark overlay)
    bar_h = 96
    bar_ov = Image.new('RGBA', (WIDTH, bar_h), (0, 0, 10, 175))
    merged = Image.alpha_composite(
        img.convert('RGBA').crop((0, 0, WIDTH, bar_h)), bar_ov
    ).convert('RGB')
    img.paste(merged, (0, 0))
    draw = ImageDraw.Draw(img)

    brand_font = load_font(30)
    draw.text((WIDTH // 2, bar_h // 2), 'CLAW.AI  UUDISED',
              font=brand_font, fill=COL_BRAND, anchor='mm')

    # Estonian flag stripe below brand bar
    draw.rectangle([0,  bar_h,      WIDTH, bar_h + 7],  fill=EST_BLUE)
    draw.rectangle([0,  bar_h + 7,  WIDTH, bar_h + 14], fill=EST_BLACK)
    draw.rectangle([0,  bar_h + 14, WIDTH, bar_h + 21], fill=EST_WHITE)

    # Bottom dark strip
    btm_y  = HEIGHT - 160
    btm_ov = Image.new('RGBA', (WIDTH, 160), (0, 0, 8, 155))
    btm_merged = Image.alpha_composite(
        img.convert('RGBA').crop((0, btm_y, WIDTH, HEIGHT)), btm_ov
    ).convert('RGB')
    img.paste(btm_merged, (0, btm_y))
    draw = ImageDraw.Draw(img)

    # Estonian flag at very bottom
    draw.rectangle([0, HEIGHT - 13, WIDTH, HEIGHT - 9],  fill=EST_BLUE)
    draw.rectangle([0, HEIGHT - 9,  WIDTH, HEIGHT - 5],  fill=EST_BLACK)
    draw.rectangle([0, HEIGHT - 5,  WIDTH, HEIGHT],      fill=EST_WHITE)

    return img.tobytes()


# ─── Step 5: Per-frame rendering ──────────────────────────────────────────────

def current_word_idx(timings: list, t: float) -> int:
    for i, (s, e, _) in enumerate(timings):
        if s <= t <= e:
            return i
    for i, (s, _, _) in enumerate(timings):
        if s > t:
            return max(0, i - 1)
    return len(timings) - 1


def make_word_glow():
    from PIL import Image, ImageDraw, ImageFilter
    gw, gh = 560, 220
    glow = Image.new('RGBA', (gw, gh), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    for i in range(10, 0, -1):
        rx = gw // 2 * i // 10
        ry = gh // 2 * i // 10
        a  = int(55 * math.pow(1 - i / 10, 0.5))
        d.ellipse([gw//2 - rx, gh//2 - ry, gw//2 + rx, gh//2 + ry],
                  fill=(*COL_GLOW, a))
    return glow.filter(ImageFilter.GaussianBlur(22))


_GLOW_IMG    = None
BASE_FONT_SIZE = 96


def render_frame(
    base_bytes: bytes,
    timings:    list,
    idx:        int,
    date_str:   str,
    t:          float,
    total_s:    float,
    cur_size:   int,
) -> bytes:
    from PIL import Image, ImageDraw
    global _GLOW_IMG

    img = Image.frombytes('RGB', (WIDTH, HEIGHT), base_bytes)

    # Word glow
    if _GLOW_IMG is None:
        _GLOW_IMG = make_word_glow()
    gw, gh = _GLOW_IMG.size
    img.paste(_GLOW_IMG, (WIDTH // 2 - gw // 2, HEIGHT // 2 - gh // 2 - 15), _GLOW_IMG)

    draw = ImageDraw.Draw(img)
    cx   = WIDTH  // 2
    cy   = HEIGHT // 2 + 30    # offset down from center to account for brand bar

    def word_at(offset: int) -> str:
        i = idx + offset
        return timings[i][2] if 0 <= i < len(timings) else ''

    def draw_word(text: str, font, color: tuple, y: int, shadow: bool = False):
        if not text:
            return
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = cx - w // 2
        ty = y - h // 2
        if shadow:
            draw.text((x + 3, ty + 3), text, font=font, fill=(0, 0, 0))
        draw.text((x, ty), text, font=font, fill=color)

    f_cur  = load_font(cur_size)
    f_near = load_font(55)
    f_far  = load_font(37)
    f_tick = load_font(23)

    draw_word(word_at(-2), f_far,  COL_FAR,  cy - 270)
    draw_word(word_at(-1), f_near, COL_NEAR, cy - 155)
    draw_word(word_at( 0), f_cur,  COL_CUR,  cy, shadow=True)
    draw_word(word_at(+1), f_near, COL_NEAR, cy + 155)
    draw_word(word_at(+2), f_far,  COL_FAR,  cy + 255)

    # Progress bar
    pb_y1, pb_y2 = HEIGHT - 118, HEIGHT - 106
    pb_x1, pb_x2 = 55, WIDTH - 55
    draw.rounded_rectangle([pb_x1, pb_y1, pb_x2, pb_y2], radius=5, fill=COL_PROG_BG)
    progress = min(1.0, t / max(total_s, 0.01))
    if progress > 0.001:
        end_x = int(pb_x1 + (pb_x2 - pb_x1) * progress)
        draw.rounded_rectangle([pb_x1, pb_y1, end_x, pb_y2], radius=5, fill=COL_ACCENT)

    # Date ticker
    draw.text((cx, HEIGHT - 91), date_str, font=f_tick, fill=COL_TICKER, anchor='mm')

    return img.tobytes()


# ─── Step 6: Video assembly ────────────────────────────────────────────────────

def generate_video(timings: list, audio_path: str, out_path: str, topic: str = '') -> bool:
    if not timings:
        print('No word timings.', file=sys.stderr)
        return False

    total_s      = timings[-1][1] + 1.0
    total_frames = int(total_s * FPS) + 1
    date_str     = time.strftime('%d. %B %Y  ·  claw.ai')

    print(f'Rendering {total_frames} frames ({total_s:.1f}s @ {FPS}fps)...')

    print('     Building background (fetching image if possible)...')
    bg = build_background(topic)

    global _GLOW_IMG
    _GLOW_IMG = make_word_glow()

    for sz in [BASE_FONT_SIZE, 110, 100, 96, 90, 80, 55, 37, 30, 23]:
        load_font(sz)

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

    prev_idx          = -1
    word_change_frame = 0
    cached_frame      = None

    for n in range(total_frames):
        t   = n / FPS
        idx = current_word_idx(timings, t)

        if idx != prev_idx:
            word_change_frame = n
            prev_idx = idx

        # Entrance animation: 1.25 → 1.0 over 8 frames
        frames_since = n - word_change_frame
        if frames_since < 8:
            scale    = 1.25 - 0.25 * (frames_since / 8.0)
            cur_size = int(BASE_FONT_SIZE * scale)
        else:
            cur_size = BASE_FONT_SIZE

        # Re-render during animation or every 4 frames for progress bar
        if frames_since < 8 or n % 4 == 0 or cached_frame is None:
            cached_frame = render_frame(bg, timings, idx, date_str, t, total_s, cur_size)

        try:
            ffmpeg.stdin.write(cached_frame)
        except BrokenPipeError:
            break

        if n % 250 == 0:
            w = timings[idx][2] if timings else ''
            print(f'  frame {n}/{total_frames}  "{w}"', flush=True)

    try:
        ffmpeg.stdin.close()
    except Exception:
        pass
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


# ─── Step 7: Send to Telegram ─────────────────────────────────────────────────

def send_video(path: str, caption: str):
    if not BOT_TOKEN or not CHAT_ID:
        print(f'No TELEGRAM_BOT_TOKEN/CHAT_ID — video at {path}')
        return
    print('Sending to Telegram...')
    with open(path, 'rb') as f:
        r = requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendVideo',
            data={'chat_id': CHAT_ID, 'caption': caption, 'supports_streaming': 'true'},
            files={'video': ('news.mp4', f, 'video/mp4')},
            timeout=180,
        )
    if r.ok:
        print('Sent!')
    else:
        print(f'Send failed: {r.text[:300]}', file=sys.stderr)


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    topic = TOPIC
    label = f'"{topic}"' if topic else 'Estonia news'
    print(f'=== Claw News Video — {label} ===\n')

    print('1/5  Fetching news...')
    news = fetch_news(topic)
    if not news:
        sys.exit('Could not fetch news.')
    print(f'     {news.count(chr(10)) + 1} lines.')

    print('2/5  Generating Estonian voiceover script (Gemini 2.0 Flash)...')
    script = make_estonian_script(news, topic)
    print(f'     Script ({len(script.split())} words): {script[:100]}...\n')

    with tempfile.TemporaryDirectory() as tmp:
        audio = os.path.join(tmp, 'voice.mp3')
        out   = os.path.expanduser('~/estonia_news.mp4')

        print(f'3/5  TTS: TartuNLP/{TARTUNLP_SPEAKER} speed={TARTUNLP_SPEED}...')
        timings = await generate_tts(script, audio)
        if not timings:
            sys.exit('TTS produced no word timings.')
        actual_audio = _AUDIO_WAV_OVERRIDE[0] or audio
        audio_mb = os.path.getsize(actual_audio) / 1024 / 1024
        print(f'     {len(timings)} word slots, {audio_mb:.2f} MB audio')

        # TartuNLP writes WAV directly; use that for the video instead of .mp3
        actual_audio = _AUDIO_WAV_OVERRIDE[0] or audio

        print('4/5  Rendering 720x1280 TikTok video...')
        ok = generate_video(timings, actual_audio, out, topic)
        if not ok:
            sys.exit('Video generation failed.')

    caption_topic = topic if topic else 'Eesti uudised'
    caption = f'{caption_topic} — {time.strftime("%d. %B %Y")}'
    print('5/5  Sending to Telegram...')
    send_video(out, caption)
    print('\nDone.')


if __name__ == '__main__':
    asyncio.run(main())
