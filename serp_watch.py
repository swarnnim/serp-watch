#!/usr/bin/env python3
"""serp-watch — watch a Google search query over time via SerpApi.

Tracks the top organic results for watched queries and reports what changed
between checks: new entries, rank changes, and dropped URLs.

Usage:
    serp-watch add "best noise cancelling headphones"
    serp-watch list
    serp-watch check                 # check all watched queries
    serp-watch check "my query"      # check one query
    serp-watch remove "my query"

The SerpApi key is read from the SERPAPI_API_KEY environment variable.
If it is absent, serp-watch runs in clearly-labeled MOCK mode with
deterministic sample data (set SERP_MOCK_CYCLE=1|2 to simulate two
different result sets and demonstrate the diff).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "watchlist.json"
SERPAPI_URL = "https://serpapi.com/search.json"
TOP_N = 10


# ---------------------------------------------------------------- state

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_state() -> dict:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"queries": {}}


def save_state(state: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- fetch

def fetch_live(query: str, api_key: str) -> list[dict]:
    """Fetch top organic results from the SerpApi Google Search API."""
    if requests is None:
        raise RuntimeError(
            "The 'requests' package is required for live mode. "
            "Install it with: pip install -r requirements.txt"
        )
    resp = requests.get(
        SERPAPI_URL,
        params={
            "engine": "google",
            "q": query,
            "num": TOP_N,
            "api_key": api_key,
        },
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise RuntimeError(f"SerpApi error: {payload['error']}")
    results = []
    for item in payload.get("organic_results", [])[:TOP_N]:
        results.append(
            {
                "position": item.get("position"),
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": (item.get("snippet") or "")[:200],
            }
        )
    return results


def _mock_seed(query: str) -> int:
    return int(hashlib.sha256(query.encode()).hexdigest(), 16) % (10**8)


def fetch_mock(query: str) -> list[dict]:
    """Deterministic sample data so the demo works without an API key.

    SERP_MOCK_CYCLE=1 returns the baseline set; SERP_MOCK_CYCLE=2 returns a
    second set with one new entry at the top, one rank change, and one
    dropped URL — perfect for demonstrating the diff.
    """
    cycle = os.environ.get("SERP_MOCK_CYCLE", "1")
    seed = _mock_seed(query)
    domains = [
        "example.com", "sample.org", "demo.net", "mock.dev",
        "test.io", "fake.ai", "placeholder.co", "stub.app",
        "dummy.site", "trial.tech",
    ]
    base = []
    for i, domain in enumerate(domains[:TOP_N]):
        h = hashlib.sha256(f"{seed}-{i}".encode()).hexdigest()[:8]
        base.append(
            {
                "position": i + 1,
                "title": f"Result {i + 1} for '{query}' [{h}]",
                "link": f"https://{domain}/article-{h}",
                "snippet": f"Sample snippet {h} about {query}. (mock data)",
            }
        )
    if cycle != "2":
        return base
    # Cycle 2: shuffle the deck a little so the diff has something to say.
    new_entry = {
        "position": 1,
        "title": f"BREAKING: brand-new top result for '{query}'",
        "link": "https://fresh-news.example/new-story",
        "snippet": "A brand-new page that appeared since the last check. (mock data)",
    }
    kept = base[:7]  # drop base[7], base[8] (dropped URLs); base[9] moves up
    reordered = [new_entry] + kept
    for i, item in enumerate(reordered):
        item["position"] = i + 1
    return reordered


def fetch_results(query: str) -> tuple[list[dict], str]:
    """Return (results, mode) where mode is 'live' or 'mock'."""
    api_key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if api_key:
        return fetch_live(query, api_key), "live"
    return fetch_mock(query), "mock"


# ---------------------------------------------------------------- diff

def diff_results(old: list[dict], new: list[dict]) -> dict:
    old_by_link = {r["link"]: r for r in old}
    new_by_link = {r["link"]: r for r in new}
    new_entries = [r for r in new if r["link"] not in old_by_link]
    dropped = [r for r in old if r["link"] not in new_by_link]
    moved = []
    for link, cur in new_by_link.items():
        prev = old_by_link.get(link)
        if prev and prev.get("position") != cur.get("position"):
            moved.append(
                {
                    "title": cur["title"],
                    "link": link,
                    "from": prev.get("position"),
                    "to": cur.get("position"),
                }
            )
    moved.sort(key=lambda m: abs((m["to"] or 0) - (m["from"] or 0)), reverse=True)
    return {"new": new_entries, "dropped": dropped, "moved": moved}


def format_check(query: str, results: list[dict], diff: dict | None, mode: str) -> str:
    lines = []
    if mode == "mock":
        lines.append("[MOCK MODE] No SERPAPI_API_KEY set — showing sample data.")
    lines.append(f"Query: {query}")
    lines.append(f"Checked: {utcnow()}  |  Top {len(results)} organic results")
    lines.append("")
    lines.append("Current top results:")
    for r in results:
        lines.append(f"  {r['position']:>2}. {r['title']}")
        lines.append(f"      {r['link']}")
    if diff is None:
        lines.append("")
        lines.append("First check recorded — run 'check' again later to see changes.")
        return "\n".join(lines)
    lines.append("")
    lines.append("Changes since last check:")
    if diff["new"]:
        lines.append(f"  NEW ({len(diff['new'])}):")
        for r in diff["new"]:
            lines.append(f"    + #{r['position']} {r['title']}")
            lines.append(f"      {r['link']}")
    else:
        lines.append("  NEW (0): none")
    if diff["moved"]:
        lines.append(f"  RANK CHANGES ({len(diff['moved'])}):")
        for m in diff["moved"]:
            arrow = "▲" if (m["to"] or 99) < (m["from"] or 99) else "▼"
            lines.append(f"    {arrow} #{m['from']} → #{m['to']} {m['title']}")
    else:
        lines.append("  RANK CHANGES (0): none")
    if diff["dropped"]:
        lines.append(f"  DROPPED ({len(diff['dropped'])}):")
        for r in diff["dropped"]:
            lines.append(f"    - was #{r['position']} {r['title']}")
    else:
        lines.append("  DROPPED (0): none")
    return "\n".join(lines)


# ---------------------------------------------------------------- commands

def cmd_add(args) -> int:
    state = load_state()
    q = args.query.strip()
    if q in state["queries"]:
        print(f"Already watching: {q}")
        return 0
    state["queries"][q] = {"added": utcnow(), "last_check": None, "results": []}
    save_state(state)
    print(f"Watching: {q}")
    return 0


def cmd_remove(args) -> int:
    state = load_state()
    q = args.query.strip()
    if q not in state["queries"]:
        print(f"Not watching: {q}")
        return 1
    del state["queries"][q]
    save_state(state)
    print(f"Stopped watching: {q}")
    return 0


def cmd_list(args) -> int:
    state = load_state()
    queries = state["queries"]
    if not queries:
        print("No watched queries. Add one with: serp-watch add \"your query\"")
        return 0
    print(f"Watched queries ({len(queries)}):")
    for q, meta in queries.items():
        last = meta.get("last_check") or "never checked"
        print(f"  • {q}   (last check: {last})")
    return 0


def cmd_check(args) -> int:
    state = load_state()
    targets = [args.query.strip()] if args.query else list(state["queries"])
    if args.query and args.query.strip() not in state["queries"]:
        print(f"Not watching: {args.query.strip()} (use 'add' first)")
        return 1
    if not targets:
        print("No watched queries. Add one with: serp-watch add \"your query\"")
        return 1
    rc = 0
    for i, q in enumerate(targets):
        if i:
            print("\n" + "=" * 60 + "\n")
        try:
            results, mode = fetch_results(q)
        except Exception as exc:  # network / API errors stay readable
            print(f"Query: {q}\nERROR: {exc}")
            rc = 1
            continue
        meta = state["queries"][q]
        prev = meta.get("results") or []
        diff = diff_results(prev, results) if prev else None
        print(format_check(q, results, diff, mode))
        meta["results"] = results
        meta["last_check"] = utcnow()
    save_state(state)
    return rc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="serp-watch",
        description="Watch Google search results over time via SerpApi; report new/changed top results.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pa = sub.add_parser("add", help="Start watching a query.")
    pa.add_argument("query", help="The search query to watch.")
    pa.set_defaults(func=cmd_add)

    pr = sub.add_parser("remove", help="Stop watching a query.")
    pr.add_argument("query", help="The search query to stop watching.")
    pr.set_defaults(func=cmd_remove)

    pl = sub.add_parser("list", help="List watched queries.")
    pl.set_defaults(func=cmd_list)

    pc = sub.add_parser("check", help="Check for changes (all queries, or one).")
    pc.add_argument("query", nargs="?", default=None, help="Optional single query to check.")
    pc.set_defaults(func=cmd_check)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
