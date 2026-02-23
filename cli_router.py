#!/usr/bin/env python3
"""
OpenClaw-to-OpenCode Router v6

Changes over v5:
  NEW: sentiment_research intent — runs sentiment_research.py (polls + social media
       + party positions + news) and formats structured JSON for LLM synthesis
  NEW: format_sentiment_data() converts research JSON into readable report context
  Updated: intent detection expanded with social/sentiment/polls keywords
"""
import json, subprocess, os, re, time, sys
from http.server import HTTPServer, BaseHTTPRequestHandler

LOG = '/tmp/router_debug.log'
MODEL = os.environ.get('ROUTER_MODEL', 'opencode/minimax-m2.5-free')
OPENCODE = os.environ.get('OPENCODE_BIN', '/home/ubuntu/.opencode/bin/opencode')
TIMEOUT = int(os.environ.get('ROUTER_TIMEOUT', '300'))
TOOL_TIMEOUT = 30        # seconds for basic tool calls
SENTIMENT_TIMEOUT = 90   # seconds for deep research (multiple fetches)

WORKSPACE = '/home/ubuntu/.openclaw/workspace'
SKILLS_DIR = f'{WORKSPACE}/skills/web-browser/scripts'
WEB_SEARCH = f'{SKILLS_DIR}/web_search.py'
WEB_FETCH = f'{SKILLS_DIR}/web_fetch.py'
SENTIMENT_TOOL = f'{SKILLS_DIR}/sentiment_research.py'

# Prompt size limits
MAX_PROMPT_CHARS = 10000
MAX_SYSTEM_CHARS = 2000
MAX_HISTORY_CHARS = 2500
MAX_TOOL_RESULT_CHARS = 4000  # larger for research results


def log(msg):
    with open(LOG, 'a') as f:
        f.write(f'[{time.strftime("%H:%M:%S")}] {msg}\n')


def content_to_text(content):
    """Convert OpenAI content (string or array of parts) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                if p.get('type') == 'text':
                    parts.append(p.get('text', ''))
                elif p.get('type') == 'tool_result':
                    parts.append(f"[Tool result: {p.get('content', '')}]")
        return '\n'.join(parts)
    return str(content) if content else ''


def clean_user_msg(text):
    """Strip OpenClaw's 'Conversation info (untrusted metadata)' wrapper."""
    cleaned = re.sub(
        r'Conversation info \(untrusted metadata\):\s*```json\s*\{[^}]*\}\s*```\s*',
        '', text
    ).strip()
    return cleaned


def compress_system_prompt(text):
    """
    Extract essential identity and behavior from OpenClaw's 26K system prompt.
    Return a minimal ~2K char version.
    """
    if not text or len(text) < 500:
        return text

    essential_parts = []

    # Try to extract IDENTITY.md content
    identity_match = re.search(
        r'(?:## Identity|# Identity|IDENTITY\.md)(.*?)(?=\n#|\n===|\Z)',
        text, re.DOTALL | re.IGNORECASE
    )
    if identity_match:
        essential_parts.append(identity_match.group(1).strip()[:400])

    # Extract user context
    user_match = re.search(
        r'(?:## User|# User|USER\.md)(.*?)(?=\n#|\n===|\Z)',
        text, re.DOTALL | re.IGNORECASE
    )
    if user_match:
        essential_parts.append(user_match.group(1).strip()[:200])

    # Extract behavior/personality rules
    for pattern in [
        r'(?:## Behavior|## Rules|## Instructions)(.*?)(?=\n#|\n===|\Z)',
        r'(?:## Core Personality|## Personality)(.*?)(?=\n#|\n===|\Z)',
    ]:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            essential_parts.append(match.group(1).strip()[:300])
            break

    # Core identity prefix — always included
    prefix = (
        "You are Claw 🦞, an AI assistant running on a VPS. "
        "User: DaN (@Iselter). "
        "Be direct, concise, opinionated. Do the task, don't describe what you could do. "
        "When given web search results or tool output, synthesize them into a useful answer."
    )

    if essential_parts:
        body = '\n\n'.join(essential_parts)
    else:
        # Fallback: first non-JSON lines up to limit
        lines = []
        for line in text.split('\n'):
            if re.match(r'^\s*[\{\}"|\u251c\u2514\u2502]', line):
                continue
            if re.search(r'additionalProperties|parameters.*schema|enum:', line):
                continue
            lines.append(line)
            if len('\n'.join(lines)) > 800:
                break
        body = '\n'.join(lines)

    result = prefix + '\n\n' + body
    return result[:MAX_SYSTEM_CHARS]


# ─── Intent detection & pre-execution ───────────────────────────────────────

ESTONIAN_NEWS_KEYWORDS = [
    'estonian news', 'estonia news', 'eesti uudised', 'eesti uudis',
    'err.ee', 'postimees', 'delfi', 'estonian', 'estonia',
]

SENTIMENT_KEYWORDS = [
    'sentiment', 'public opinion', 'what do people think', 'what are people saying',
    'what are conservatives', 'what are liberals', 'social media', 'facebook',
    'twitter', 'polls', 'poll', 'survey', 'opinion poll', 'population thinks',
    'citizens think', 'society thinks', 'public view', 'community thinks',
    'what does society', 'population sentiment', 'deep research', 'scientific research',
    'how do estonians', 'eestlased', 'hoiakud', 'rahvaküsitlus', 'küsitlus',
    'what do estonians think', 'estonian opinion', 'citizen sentiment',
]

def detect_intent(user_msg):
    """Return (intent, query) tuple."""
    msg_lower = user_msg.lower()

    # Sentiment / deep research — check before news/search (more specific)
    if any(kw in msg_lower for kw in SENTIMENT_KEYWORDS):
        return ('sentiment_research', user_msg)

    # Estonian news
    if any(kw in msg_lower for kw in ESTONIAN_NEWS_KEYWORDS):
        if any(w in msg_lower for w in ['news', 'uudis', 'report', 'today', 'latest', 'what', 'tell']):
            return ('estonian_news', user_msg)

    # Explicit web search
    if re.search(r'\b(search|look up|find|google|research|web)\b', msg_lower):
        query_match = re.search(
            r'(?:search(?:\s+for)?|look\s+up|find|google|research)\s+(.+)', msg_lower
        )
        if query_match:
            return ('web_search', query_match.group(1).strip())
        return ('web_search', user_msg)

    # URL in message — fetch it
    url_match = re.search(r'https?://\S+', user_msg)
    if url_match:
        return ('web_fetch', url_match.group(0))

    return (None, user_msg)


def format_sentiment_data(data):
    """Convert sentiment_research.py JSON output into a readable context for the LLM."""
    lines = [f'DEEP RESEARCH DATA — Topic: {data.get("topic", "unknown")}',
             f'Timestamp: {data.get("timestamp", "")}', '']

    # Key statistics first
    stats = data.get('key_statistics', [])
    if stats:
        lines.append(f'KEY STATISTICS FOUND: {", ".join(stats[:15])}')
        lines.append('')

    # Poll data
    polls = data.get('poll_data', [])
    if polls:
        lines.append('=== POLL & SURVEY DATA ===')
        for p in polls[:5]:
            lines.append(f'Source: {p.get("source", "")}')
            if p.get('stats_found'):
                lines.append(f'  Statistics: {", ".join(p["stats_found"][:8])}')
            # Use full_content if available, otherwise excerpt
            content = p.get('full_content') or p.get('excerpt', '')
            if content:
                lines.append(f'  Data: {content[:400]}')
            lines.append('')

    # Social media
    social = data.get('social_media', [])
    if social:
        lines.append('=== SOCIAL MEDIA FINDINGS ===')
        # Group by platform
        by_platform = {}
        for s in social:
            plat = s.get('platform', 'unknown')
            by_platform.setdefault(plat, []).append(s)
        for plat, items in list(by_platform.items())[:4]:
            lines.append(f'Platform: {plat}')
            for item in items[:3]:
                title = item.get('title', '')
                snippet = item.get('snippet', '') or item.get('content', '')
                if title or snippet:
                    lines.append(f'  • {title[:80]}')
                    if snippet:
                        lines.append(f'    {snippet[:200]}')
            lines.append('')

    # Party positions
    parties = data.get('party_positions', [])
    if parties:
        lines.append('=== POLITICAL PARTY POSITIONS ===')
        seen_parties = set()
        for p in parties:
            party = p.get('party', '')
            if party not in seen_parties:
                seen_parties.add(party)
                lines.append(f'{party}: {p.get("snippet", "")[:200]}')
        lines.append('')

    # News
    news = data.get('news', [])
    if news:
        lines.append('=== RELEVANT NEWS ===')
        for n in news[:4]:
            lines.append(f'• {n.get("title", "")[:80]}')
            if n.get('snippet'):
                lines.append(f'  {n["snippet"][:150]}')
        lines.append('')

    return '\n'.join(lines)


def run_tool(cmd, timeout=TOOL_TIMEOUT):
    """Run a shell command and return stdout, stripping ANSI and warning lines."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd='/home/ubuntu'
        )
        out = result.stdout + result.stderr
        # Strip ANSI
        out = re.sub(r'\x1b\[[0-9;]*m', '', out)
        # Strip "Impersonate ... does not exist" warnings
        out = '\n'.join(
            l for l in out.split('\n')
            if not l.startswith('Impersonate')
        ).strip()
        return out
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        log(f'Tool error: {e}')
        return None


def fetch_estonian_news():
    """Fetch Estonian news headlines via web search + err.ee."""
    log('Pre-exec: fetching Estonian news')
    results = []

    # Search for today's news
    search_out = run_tool([
        'python3', WEB_SEARCH,
        '--query', 'Estonia news today site:err.ee OR site:postimees.ee OR site:delfi.ee',
        '--max-results', '6'
    ])
    if search_out:
        try:
            data = json.loads(search_out)
            for item in data[:6]:
                title = item.get('title', '')
                snippet = item.get('snippet', '')[:200]
                url = item.get('url', '')
                results.append(f"• {title}\n  {snippet}\n  {url}")
        except Exception:
            results.append(search_out[:1000])

    # Also try a general search
    if not results:
        search_out2 = run_tool([
            'python3', WEB_SEARCH,
            '--query', f'Estonia news {time.strftime("%B %Y")}',
            '--max-results', '5'
        ])
        if search_out2:
            try:
                data = json.loads(search_out2)
                for item in data[:5]:
                    title = item.get('title', '')
                    snippet = item.get('snippet', '')[:200]
                    results.append(f"• {title}\n  {snippet}")
            except Exception:
                results.append(search_out2[:800])

    if results:
        return 'LIVE WEB DATA (Estonian news):\n' + '\n\n'.join(results)
    return None


def do_web_search(query):
    """Run DuckDuckGo search and return formatted results."""
    log(f'Pre-exec: web search "{query[:60]}"')
    out = run_tool([
        'python3', WEB_SEARCH,
        '--query', query,
        '--max-results', '5'
    ])
    if not out:
        return None
    try:
        data = json.loads(out)
        lines = []
        for item in data[:5]:
            title = item.get('title', '')
            snippet = item.get('snippet', '')[:200]
            url = item.get('url', '')
            lines.append(f"• {title}\n  {snippet}\n  {url}")
        return 'LIVE WEB SEARCH RESULTS:\n' + '\n\n'.join(lines)
    except Exception:
        return f'SEARCH RESULTS:\n{out[:1000]}'


def do_web_fetch(url):
    """Fetch a URL and return readable text."""
    log(f'Pre-exec: web fetch {url[:80]}')
    out = run_tool([
        'python3', WEB_FETCH,
        '--url', url,
        '--max-chars', '3000'
    ])
    if out:
        return f'FETCHED CONTENT from {url}:\n{out[:2000]}'
    return None


def do_sentiment_research(user_msg):
    """Run sentiment_research.py for deep social/poll/media analysis."""
    log(f'Pre-exec: sentiment research for "{user_msg[:60]}"')
    # Extract the core topic — strip polite framing
    topic = re.sub(
        r'^(please|pls|can you|i want|i need|tell me|give me|do|perform|run|'
        r'what are|what do|how do|research|analyze|investigate|find out about)\s+',
        '', user_msg.lower()
    ).strip()
    # Keep a reasonable topic length
    topic = topic[:120]
    try:
        result = subprocess.run(
            ['python3', SENTIMENT_TOOL, '--topic', topic, '--lang', 'en'],
            capture_output=True, text=True, timeout=SENTIMENT_TIMEOUT,
            cwd='/home/ubuntu'
        )
        if result.stdout:
            data = json.loads(result.stdout)
            formatted = format_sentiment_data(data)
            log(f'Sentiment research complete: {len(formatted)} chars')
            return formatted
    except subprocess.TimeoutExpired:
        log('Sentiment research timed out — falling back to web search')
        return do_web_search(topic + ' public opinion poll sentiment 2026')
    except Exception as e:
        log(f'Sentiment research error: {e}')
    return None


def pre_execute_tools(user_msg):
    """
    Detect user intent and pre-execute appropriate tools.
    Returns tool_context string to inject into prompt, or None.
    """
    intent, param = detect_intent(user_msg)
    log(f'Intent detected: {intent}')

    if intent == 'sentiment_research':
        return do_sentiment_research(param)
    elif intent == 'estonian_news':
        return fetch_estonian_news()
    elif intent == 'web_search':
        return do_web_search(param)
    elif intent == 'web_fetch':
        return do_web_fetch(param)
    return None


# ─── Prompt assembly ─────────────────────────────────────────────────────────

def build_prompt(messages, tools=None):
    """
    Build a compact prompt for the LLM.

    v5 changes:
    - History is properly limited (fixes v4 bug where history_text never updated)
    - User message is ALWAYS included (truncate history, not the end of the prompt)
    - Tool results are injected before the user message
    """
    system_text = ''
    history_entries = []
    last_user_msg = ''

    for msg in messages:
        role = msg.get('role', '')
        text = content_to_text(msg.get('content', ''))

        if role == 'system':
            system_text = text
        elif role == 'user':
            last_user_msg = text
            cleaned = clean_user_msg(text)
            if cleaned:
                history_entries.append(('user', cleaned))
        elif role == 'assistant':
            if text:
                truncated = text[:200] + '…' if len(text) > 200 else text
                history_entries.append(('assistant', truncated))
            for tc in msg.get('tool_calls', []):
                fn = tc.get('function', {})
                history_entries.append(('tool_call', f"{fn.get('name','?')}({fn.get('arguments','')[:60]})"))
        elif role == 'tool':
            history_entries.append(('tool_result', text[:150]))

    # Clean current user message
    current_user = clean_user_msg(last_user_msg)

    # Pre-execute tools based on intent
    tool_context = None
    if current_user:
        tool_context = pre_execute_tools(current_user)
        if tool_context:
            tool_context = tool_context[:MAX_TOOL_RESULT_CHARS]

    # Build compressed system prompt
    sys_compressed = compress_system_prompt(system_text) if system_text else (
        "You are Claw 🦞, a direct AI assistant. User: DaN. Be concise, do tasks, don't describe capabilities."
    )

    # Build history — CORRECTLY limit to MAX_HISTORY_CHARS
    # Take most recent entries that fit
    history_lines = []
    history_total = 0
    for role, text in reversed(history_entries[:-1]):  # exclude last user (added separately)
        prefix = {'user': 'U', 'assistant': 'A', 'tool_call': 'T', 'tool_result': 'R'}.get(role, role[0].upper())
        line = f'{prefix}: {text}'
        if history_total + len(line) + 1 > MAX_HISTORY_CHARS:
            break
        history_lines.insert(0, line)
        history_total += len(line) + 1

    # Assemble prompt — user message is ALWAYS present
    parts = [sys_compressed, '']

    if history_lines:
        parts.append('--- Recent ---')
        parts.extend(history_lines)
        parts.append('---')
        parts.append('')

    if tool_context:
        parts.append(tool_context)
        parts.append('')

    parts.append(f'USER: {current_user}')
    parts.append('')
    parts.append('Respond:')

    prompt = '\n'.join(parts)

    # Safety truncation — never truncate past the user message
    if len(prompt) > MAX_PROMPT_CHARS:
        # Find position of user message block and protect it
        user_marker = f'USER: {current_user}'
        user_pos = prompt.rfind(user_marker)
        if user_pos > 0:
            # Truncate only the beginning (history/system)
            overage = len(prompt) - MAX_PROMPT_CHARS
            prompt = prompt[overage:]
            log(f'Truncated {overage} chars from start to protect user message')
        else:
            prompt = prompt[:MAX_PROMPT_CHARS]

    log(f'Prompt built: {len(prompt)} chars, tool_context: {bool(tool_context)}, history_entries: {len(history_lines)}')
    return prompt


# ─── HTTP Handler ─────────────────────────────────────────────────────────────

class RouterHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        log(f'HTTP: {fmt % args}')

    def do_GET(self):
        if self.path == '/v1/models':
            self._json({'object': 'list', 'data': [
                {'id': MODEL, 'object': 'model'},
                {'id': 'opencode/minimax-m2.5-free', 'object': 'model'},
                {'id': 'opencode/trinity-large-preview-free', 'object': 'model'},
                {'id': 'opencode/glm-5-free', 'object': 'model'},
            ]})
        else:
            self._json({'status': 'openclaw router v5'})

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length))
        model = body.get('model', MODEL)
        messages = body.get('messages', [])
        is_stream = body.get('stream', False)
        tools = body.get('tools', [])

        msg_count = len(messages)
        sys_len = sum(len(content_to_text(m.get('content', ''))) for m in messages if m.get('role') == 'system')
        last_user_preview = ''
        for m in reversed(messages):
            if m.get('role') == 'user':
                last_user_preview = clean_user_msg(content_to_text(m.get('content', '')))[:80]
                break
        log(f'POST msgs={msg_count} sys={sys_len} model={model} user="{last_user_preview}"')

        if self.path not in ('/v1/chat/completions', '/v1/completions'):
            self._json({'error': 'not found'}, 404)
            return

        # Build prompt (includes tool pre-execution)
        prompt = build_prompt(messages, tools)

        # Map model names
        actual_model = model
        if 'kimi' in model.lower():
            actual_model = 'opencode/glm-5-free'

        # Call OpenCode CLI
        env = os.environ.copy()
        env['PATH'] = os.path.dirname(OPENCODE) + ':' + env.get('PATH', '')
        try:
            result = subprocess.run(
                [OPENCODE, 'run', '-m', actual_model, prompt],
                capture_output=True, text=True, timeout=TIMEOUT,
                env=env, cwd='/home/ubuntu'
            )
            raw = result.stdout + result.stderr
            # Clean ANSI
            cleaned = re.sub(r'\x1b\[[0-9;]*m', '', raw)
            # Remove opencode startup noise
            lines = []
            for line in cleaned.split('\n'):
                line = line.strip()
                if line and not line.startswith('>') and 'build' not in line.lower()[:20]:
                    lines.append(line)
            cleaned = '\n'.join(lines).strip() or 'No response'
            log(f'LLM response ({len(cleaned)} chars): {cleaned[:150]}')
        except subprocess.TimeoutExpired:
            cleaned = f'Taking longer than {TIMEOUT}s — free model is still working. Try again in a moment.'
            log(f'TIMEOUT after {TIMEOUT}s')
        except Exception as e:
            cleaned = f'Router error: {e}'
            log(f'Error: {e}')

        ts = int(time.time())
        chat_id = f'chatcmpl-{ts}'
        prompt_tokens = max(len(prompt.split()), 1)
        completion_tokens = max(len(cleaned.split()), 1)

        if is_stream:
            self._stream_response(chat_id, ts, model, cleaned, prompt_tokens, completion_tokens, body)
        else:
            self._json({
                'id': chat_id, 'object': 'chat.completion', 'created': ts, 'model': model,
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': cleaned}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 'total_tokens': prompt_tokens + completion_tokens}
            })

    def _stream_response(self, chat_id, ts, model, text, prompt_tokens, completion_tokens, body):
        chunks = [
            'data: ' + json.dumps({
                'id': chat_id, 'object': 'chat.completion.chunk', 'created': ts, 'model': model,
                'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': ''}, 'finish_reason': None}]
            }) + '\n\n',
            'data: ' + json.dumps({
                'id': chat_id, 'object': 'chat.completion.chunk', 'created': ts, 'model': model,
                'choices': [{'index': 0, 'delta': {'content': text}, 'finish_reason': None}]
            }) + '\n\n',
        ]
        finish = {
            'id': chat_id, 'object': 'chat.completion.chunk', 'created': ts, 'model': model,
            'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}],
        }
        if body.get('stream_options', {}).get('include_usage'):
            finish['usage'] = {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': prompt_tokens + completion_tokens
            }
        chunks.append('data: ' + json.dumps(finish) + '\n\n')
        chunks.append('data: [DONE]\n\n')

        payload = ''.join(chunks).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'close')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()
        log(f'Streamed {len(text)} chars')

    def _json(self, data, code=200):
        payload = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(payload)


if __name__ == '__main__':
    port = int(os.environ.get('ROUTER_PORT', '4097'))
    log(f'=== OpenClaw Router v6 starting on 0.0.0.0:{port} ===')
    log(f'Model: {MODEL}, Timeout: {TIMEOUT}s')
    server = HTTPServer(('0.0.0.0', port), RouterHandler)
    server.serve_forever()
