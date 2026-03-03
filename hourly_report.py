#!/usr/bin/env python3
"""
Claw Hourly Report

Generates a digest of latest AI/tech/Estonia news and sends it to Telegram.
Designed to run from cron: 0 * * * * python3 ~/hourly_report.py

Environment (set in crontab or .profile):
  TELEGRAM_BOT_TOKEN — required
  TELEGRAM_CHAT_ID   — required (your Telegram chat ID)
  REPORT_TOPIC       — optional, default "AI news and Estonian tech"
"""
import json, os, subprocess, sys, time, requests

BOT_TOKEN   = os.environ.get('TELEGRAM_BOT_TOKEN', '')
CHAT_ID     = os.environ.get('TELEGRAM_CHAT_ID', '')
TOPIC       = os.environ.get('REPORT_TOPIC', 'latest AI news and tech developments')
ROUTER_URL  = os.environ.get('ROUTER_URL', 'http://localhost:4097/v1/chat/completions')
ROUTER_MODEL = os.environ.get('ROUTER_MODEL', 'opencode/minimax-m2.5-free')

SKILLS_DIR = os.path.expanduser('~/.openclaw/workspace/skills/web-browser/scripts')
WEB_SEARCH  = f'{SKILLS_DIR}/web_search.py'


def web_search(query, n=8):
    try:
        r = subprocess.run(
            ['python3', WEB_SEARCH, '--query', query, '--max-results', str(n)],
            capture_output=True, text=True, timeout=30, cwd=os.path.expanduser('~')
        )
        return json.loads(r.stdout) if r.stdout else []
    except Exception:
        return []


def call_router(prompt):
    try:
        r = requests.post(
            ROUTER_URL,
            json={
                'model': ROUTER_MODEL,
                'stream': False,
                'messages': [
                    {'role': 'system', 'content':
                     'You are Claw, a direct AI assistant. Summarize the given news into a '
                     'concise hourly digest. Use plain text, no markdown headers or #. '
                     'Be factual, 200-350 words. End with 1 sentence of your opinion/insight.'},
                    {'role': 'user', 'content': prompt}
                ]
            },
            timeout=120,
        )
        r.raise_for_status()
        return r.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        return f'Could not generate digest: {e}'


def send_telegram(text):
    """Send a message via Telegram Bot API, splitting if over 4000 chars."""
    if not BOT_TOKEN or not CHAT_ID:
        print('ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set', file=sys.stderr)
        sys.exit(1)

    def chunks(t, limit=4000):
        if len(t) <= limit:
            yield t
            return
        for i in range(0, len(t), limit):
            yield t[i:i + limit]

    for chunk in chunks(text):
        r = requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
            json={'chat_id': CHAT_ID, 'text': chunk},
            timeout=15
        )
        r.raise_for_status()


def main():
    hour = time.strftime('%H:%M')
    date = time.strftime('%b %d, %Y')

    # Fetch news
    ai_results   = web_search('latest AI technology news today 2026', n=6)
    tech_results = web_search('Estonia tech startups news today', n=4)

    # Format for LLM
    articles = []
    for item in ai_results + tech_results:
        title   = item.get('title', '').strip()
        snippet = item.get('snippet', '').strip()[:200]
        url     = item.get('url', '')
        if title:
            articles.append(f'- {title}\n  {snippet}\n  {url}')

    if not articles:
        send_telegram(f'[{hour}] Hourly report: could not fetch news articles.')
        return

    news_block = '\n\n'.join(articles[:10])
    prompt = (
        f"Today is {date}, {hour} UTC. Here are the latest news articles:\n\n"
        f"{news_block}\n\n"
        f"Write a concise hourly digest summarizing the most important developments."
    )

    digest = call_router(prompt)
    message = f"Hourly digest — {date} {hour} UTC\n\n{digest}"
    send_telegram(message)
    print(f'Report sent ({len(message)} chars)')


if __name__ == '__main__':
    main()
