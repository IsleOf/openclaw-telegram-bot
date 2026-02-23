#!/usr/bin/env python3
"""
Deep Sentiment Research Tool v1

Aggregates data from multiple sources for population sentiment analysis:
- Opinion polls (Norstat, Kantar Emor, Eurobarometer via politpro.eu / estonianworld.com)
- Social media via DuckDuckGo search (Reddit threads, Facebook public pages, Twitter)
- News articles quoting public sentiment / polls
- Political party statements (EKRE, Reform, Isamaa, etc.)

Usage:
  python3 sentiment_research.py --topic "estonian war russia" --lang en
  python3 sentiment_research.py --topic "eesti kodanike hoiakud sõja suhtes" --lang et

Output: JSON with sources, poll_data, social_snippets, news_snippets
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.')

# ── helpers ──────────────────────────────────────────────────────────────────

def web_search(query, max_results=6):
    """Run DuckDuckGo search via existing web_search.py."""
    try:
        r = subprocess.run(
            ['python3', f'{SCRIPTS}/web_search.py', '--query', query,
             '--max-results', str(max_results)],
            capture_output=True, text=True, timeout=25
        )
        text = r.stdout.strip()
        # Strip "Impersonate..." warning line if present
        text = '\n'.join(l for l in text.split('\n') if not l.startswith('Impersonate'))
        return json.loads(text) if text else []
    except Exception as e:
        return [{'error': str(e)}]


def web_fetch(url, max_chars=4000):
    """Fetch page content via existing web_fetch.py."""
    try:
        r = subprocess.run(
            ['python3', f'{SCRIPTS}/web_fetch.py', '--url', url,
             '--max-chars', str(max_chars)],
            capture_output=True, text=True, timeout=40
        )
        return r.stdout.strip()
    except Exception:
        return None


def extract_numbers(text):
    """Pull percentage/number patterns like '42%', '2 in 3', '67 percent'."""
    patterns = [
        r'\d{1,3}(?:\.\d)?%',
        r'\d+ percent',
        r'\d+ in \d+',
        r'\d+\.\d+ percent',
    ]
    found = []
    for p in patterns:
        found.extend(re.findall(p, text, re.IGNORECASE))
    return list(dict.fromkeys(found))  # deduplicate preserving order


# ── data sources ──────────────────────────────────────────────────────────────

POLL_SOURCES = [
    {
        'name': 'Estonian World — Ukraine/Russia sentiment tracker',
        'url': 'https://estonianworld.com/security/blog-russia-ukraine-crisis-a-view-from-estonia/',
        'type': 'poll_tracker',
    },
    {
        'name': 'Politpro — Norstat/Emor polls',
        'url': 'https://politpro.eu/en/estonia',
        'type': 'poll_aggregator',
    },
    {
        'name': 'Wikipedia — Estonian opinion polling',
        'url': 'https://en.wikipedia.org/wiki/Opinion_polling_for_the_next_Estonian_parliamentary_election',
        'type': 'wiki_polls',
    },
]

SOCIAL_SEARCH_TEMPLATES = [
    'site:reddit.com/r/Eesti OR site:reddit.com/r/europe "estonia" "{topic}" 2026',
    'EKRE facebook "{topic}" eestlased 2026',
    '"{topic}" estonia public opinion survey 2026',
    'Estonia conservatives "{topic}" social media reaction 2026',
    'eestlased hoiakud "{topic}" küsitlus 2026',
]

POLL_SEARCH_TEMPLATES = [
    'Norstat Kantar Emor "{topic}" estonia poll 2026',
    'Eurobarometer Estonia "{topic}" survey 2026',
    '"{topic}" estonia citizens survey statistics percent 2026',
    'Estonian public opinion "{topic}" percent support 2026',
]

PARTY_SOURCES = {
    'EKRE (Conservative)': 'EKRE statement "{topic}" estonia 2026',
    'Reform Party': 'Reform Party estonia "{topic}" 2026',
    'Isamaa': 'Isamaa party estonia "{topic}" 2026',
    'Social Democrats (SDE)': 'SDE Social Democrats estonia "{topic}" 2026',
}


# ── main research pipeline ────────────────────────────────────────────────────

def research(topic, lang='en', verbose=False):
    results = {
        'topic': topic,
        'timestamp': time.strftime('%Y-%m-%d %H:%M UTC'),
        'poll_data': [],
        'social_media': [],
        'party_positions': [],
        'news': [],
        'key_statistics': [],
        'sources_fetched': [],
    }

    def log(msg):
        if verbose:
            print(f'[sentiment_research] {msg}', file=sys.stderr)

    # ── 1. Poll aggregator pages ──────────────────────────────────────────
    log('Fetching poll tracker pages...')
    for src in POLL_SOURCES:
        content = web_fetch(src['url'], max_chars=3500)
        if content and len(content) > 200:
            # Extract numbers as evidence of poll data
            stats = extract_numbers(content)
            snippet = content[:800].replace('\n', ' ')
            results['poll_data'].append({
                'source': src['name'],
                'url': src['url'],
                'type': src['type'],
                'stats_found': stats[:15],
                'excerpt': snippet,
            })
            results['sources_fetched'].append(src['url'])
            log(f"  Got {len(content)} chars from {src['name']}, stats: {stats[:5]}")
        time.sleep(0.5)

    # ── 2. Poll search queries ────────────────────────────────────────────
    log('Searching for poll articles...')
    for template in POLL_SEARCH_TEMPLATES[:3]:
        query = template.replace('{topic}', topic)
        items = web_search(query, max_results=4)
        for item in items:
            if any(kw in item.get('url', '').lower() for kw in ['wiki', 'politpro', 'estonianworld', 'err.ee']):
                # Already fetched or will fetch — skip to avoid duplicate
                continue
            snippet = item.get('snippet', '')
            stats = extract_numbers(snippet)
            results['poll_data'].append({
                'source': item.get('title', ''),
                'url': item.get('url', ''),
                'type': 'poll_search_result',
                'stats_found': stats,
                'excerpt': snippet[:300],
            })
        time.sleep(0.3)

    # ── 3. Social media searches ──────────────────────────────────────────
    log('Searching social media discussions...')
    for template in SOCIAL_SEARCH_TEMPLATES[:4]:
        query = template.replace('{topic}', topic)
        items = web_search(query, max_results=4)
        for item in items:
            url = item.get('url', '')
            title = item.get('title', '')
            snippet = item.get('snippet', '')
            platform = 'unknown'
            if 'reddit.com' in url:
                platform = 'reddit'
            elif 'facebook.com' in url:
                platform = 'facebook'
            elif 'twitter.com' in url or 'x.com' in url:
                platform = 'twitter/x'
            elif 'telegram' in url:
                platform = 'telegram'
            results['social_media'].append({
                'platform': platform,
                'title': title[:120],
                'url': url,
                'snippet': snippet[:300],
                'stats': extract_numbers(snippet),
            })
        time.sleep(0.3)

    # ── 4. Try to fetch a Reddit thread if found ──────────────────────────
    reddit_urls = [s['url'] for s in results['social_media'] if s['platform'] == 'reddit']
    for rurl in reddit_urls[:2]:
        # Try old Reddit (less likely to block)
        old_url = rurl.replace('www.reddit.com', 'old.reddit.com')
        content = web_fetch(old_url, max_chars=2000)
        if content and 'blocked' not in content.lower() and len(content) > 300:
            results['social_media'].append({
                'platform': 'reddit (fetched)',
                'url': rurl,
                'content': content[:1500],
                'stats': extract_numbers(content),
            })
            log(f'  Fetched Reddit thread: {rurl[:60]}')
            break
        time.sleep(0.5)

    # ── 5. Political party positions ──────────────────────────────────────
    log('Searching party positions...')
    for party, template in list(PARTY_SOURCES.items())[:3]:
        query = template.replace('{topic}', topic)
        items = web_search(query, max_results=3)
        for item in items[:2]:
            results['party_positions'].append({
                'party': party,
                'title': item.get('title', '')[:100],
                'url': item.get('url', ''),
                'snippet': item.get('snippet', '')[:250],
            })
        time.sleep(0.3)

    # ── 6. Fetch key poll article (estonianworld war tracker if available) ─
    ew_poll = next((p for p in results['poll_data']
                    if 'estonianworld' in p.get('url', '') and len(p.get('excerpt', '')) > 200), None)
    if ew_poll:
        full = web_fetch(ew_poll['url'], max_chars=5000)
        if full:
            ew_poll['full_content'] = full[:3000]
            results['key_statistics'].extend(extract_numbers(full))

    # ── 7. Recent news about sentiment ───────────────────────────────────
    log('Fetching recent sentiment news...')
    news_items = web_search(
        f'Estonia public opinion sentiment {topic} 2026 survey poll percent', max_results=5
    )
    for item in news_items:
        results['news'].append({
            'title': item.get('title', '')[:120],
            'url': item.get('url', ''),
            'snippet': item.get('snippet', '')[:300],
            'stats': extract_numbers(item.get('snippet', '')),
        })

    # ── Deduplicate key_statistics ────────────────────────────────────────
    results['key_statistics'] = list(dict.fromkeys(
        results['key_statistics'] +
        [s for p in results['poll_data'] for s in p.get('stats_found', [])]
    ))[:30]

    return results


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--topic', required=True, help='Topic to research')
    parser.add_argument('--lang', default='en', help='Language hint (en/et)')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    data = research(args.topic, lang=args.lang, verbose=args.verbose)
    print(json.dumps(data, ensure_ascii=False, indent=2))
