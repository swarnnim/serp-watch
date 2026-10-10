# serp-watch

Watch a Google search query over time and get a plain-text report of what changed:
**new entries, rank changes, and dropped URLs** — powered by the
[SerpApi](https://serpapi.com/) Google Search API.

## What it does

Search rankings move constantly. serp-watch keeps a local snapshot of the top
10 organic results for each query you watch. Every time you run a check, it
compares the fresh results against the last snapshot and prints a diff:

```
Query: best noise cancelling headphones 2026
Checked: 2026-10-10T11:05:00+00:00  |  Top 10 organic results

Changes since last check:
  NEW (1):
    + #1 BREAKING: brand-new top result for 'best noise cancelling headphones 2026'
  RANK CHANGES (7):
    ▼ #1 → #2 Result 1 for '...' [a1b2c3d4]
    ...
  DROPPED (2):
    - was #8 Result 8 for '...' [e5f6a7b8]
```

Use cases: track your own site's ranking, watch competitors, monitor news
cycles around a topic, or just notice when the internet changes its mind.

## Setup

```bash
cd serp-watch
pip install -r requirements.txt   # only dependency: requests
chmod +x serp_watch.py
```

Set your SerpApi key (get a free one at https://serpapi.com — free plan
included, no card required):

```bash
export SERPAPI_API_KEY="your_key_here"
```

No key? serp-watch runs in a **clearly-labeled MOCK mode** with deterministic
sample data, so the demo works end-to-end without one.

## Usage

```bash
./serp_watch.py add "best noise cancelling headphones 2026"
./serp_watch.py list
./serp_watch.py check                        # check all watched queries
./serp_watch.py check "your query"           # check a single query
./serp_watch.py remove "your query"
```

Watched queries and their last snapshots live in `data/watchlist.json`
(plain JSON — back it up or version it however you like).

To demo the diff without a key:

```bash
export SERP_MOCK_CYCLE=1 && ./serp_watch.py check "demo query"   # baseline
export SERP_MOCK_CYCLE=2 && ./serp_watch.py check "demo query"   # see the diff
```

## How SerpApi is used

serp-watch calls the SerpApi **Google Search API** endpoint
`https://serpapi.com/search.json` with `engine=google`, the watched query,
and `num=10`. It reads the `organic_results` array (position, title, link,
snippet) — nothing else. One API call per query per check; snapshots are
stored locally so repeat `list`/`diff` views cost zero API calls.

## Project structure

```
serp-watch/
├── serp_watch.py      # the CLI (stdlib + requests only)
├── requirements.txt
├── data/
│   └── watchlist.json # watched queries + last snapshots (created on first run)
├── README.md
├── WRITEUP.md         # hackathon writeup
└── DEMO_SCRIPT.md     # ≤3-min demo video script
```

## Future work

- Scheduled checks (cron) with email/Telegram alerts on big changes
- Track more than the top 10; persist full history and chart rank over time
- Support other SerpApi engines (Google News, Google Trends, Bing)
- Export diffs as Markdown/HTML reports
