#!/usr/bin/env python3
"""
Build reddit_health_communities.json from a CSV with columns:
    language,subreddit_url,subreddit,focus,community_type

For every subreddit it fetches the rules from the wiki page (.../wiki/rules/)
and, if there is none, from Reddit's built-in sidebar rules.

Three ways of fetching (Reddit blocks plain scripts with HTTP 403, so use 2 or 3):
  --method requests    plain HTTP (default; often blocked)
  --method praw        official Reddit API  (pip install praw)
                       needs env vars REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET
                       (create an app at https://www.reddit.com/prefs/apps)
  --method browser     headless Chrome      (pip install playwright;
                                             playwright install chromium)

Usage:
    pip install requests beautifulsoup4
    python build_reddit_rules_json.py communities.csv reddit_health_communities.json --method browser

--debug saves every raw response into ./debug/ so you can inspect failures.
"""
import argparse
import csv
import os
import html as htmllib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (research script; contact: you@example.com)"}
DELAY = 2  # seconds between subreddits
BLOCK_MARKERS = (
    "blocked by network security",
    "whoa there, pardner",
    "you've been blocked",
    "verify you are human",
    "please wait for verification",
)
NUMBERED = re.compile(r"^\s*(?:rule\s*)?(\d{1,2})\s*[.):\-\u2013]\s*(.+)$", re.I | re.S)


# ----------------------------------------------------------------- helpers
def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def http_get(url: str):
    """Return (status_code, text). status is None on network error."""
    for attempt in range(2):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 429 and attempt == 0:
                time.sleep(int(r.headers.get("Retry-After", 10)))
                continue
            return r.status_code, r.text
        except Exception as e:  # noqa: BLE001
            return None, str(e)
    return 429, ""


def is_blocked(body: str) -> bool:
    low = body[:5000].lower()
    return any(m in low for m in BLOCK_MARKERS)


def links_in(el):
    return [
        {"text": clean(a.get_text()), "url": a["href"]}
        for a in el.find_all("a", href=True)
    ]


def split_title(text: str, strong_text: str | None = None):
    """Split 'Title. Description...' into (title, description)."""
    text = clean(text)
    if strong_text:
        st = clean(strong_text)
        rest = text[len(st):] if text.startswith(st) else text.replace(st, "", 1)
        return st.rstrip(".:!- "), rest.lstrip(" .:-\u2013").strip()
    m = re.match(r"(.{3,120}?[.!?:])\s+(.*)", text, re.S)
    if m:
        return m.group(1).rstrip(".:"), m.group(2).strip()
    if len(text) <= 120:
        return text, ""
    return text[:120].rstrip() + "…", text


def lead_strong(el):
    """Return the bold text if the element STARTS with a <strong>/<b>, else None."""
    first = next((c for c in el.children if getattr(c, "name", None) or clean(str(c))), None)
    if first is not None and getattr(first, "name", None) in ("strong", "b"):
        t = clean(first.get_text())
        if 3 <= len(t) <= 120:
            return t
    return None


# ----------------------------------------------------------------- parsing
def parse_headings(root):
    """Layout 1: each rule is a heading (h1-h6). Level is auto-detected."""
    counts = Counter(int(h.name[1]) for h in root.find_all(re.compile(r"^h[1-6]$")))
    rule_level = next((lvl for lvl in sorted(counts) if counts[lvl] >= 2), None)
    if rule_level is None and counts:
        rule_level = min(counts)

    tags = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "blockquote"]
    intro, rules, current = [], [], None
    for el in root.find_all(tags):
        if el.name == "p" and el.find_parent(["ul", "ol", "blockquote"]):
            continue
        if re.fullmatch(r"h[1-6]", el.name):
            title = clean(el.get_text())
            if int(el.name[1]) == rule_level:
                m = re.match(r"(?i)^rule\s*(\d+)\s*[:.\-\u2013]\s*(.*)$", title)
                current = {
                    "number": int(m.group(1)) if m else len(rules) + 1,
                    "title": m.group(2) if m else title,
                    "description": "",
                    "links": [],
                }
                rules.append(current)
            elif current is not None:
                current["description"] = (current["description"] + " " + title).strip()
            continue
        if el.name in ("ul", "ol"):
            text = " ".join("- " + clean(li.get_text()) for li in el.find_all("li"))
        else:
            text = clean(el.get_text())
        if not text:
            continue
        if current is None:
            intro.append(text)
        else:
            current["description"] = (current["description"] + " " + text).strip()
            current["links"].extend(links_in(el))
    return {"intro": " ".join(intro), "rules": rules}


def parse_no_headings(root):
    """Layout 2: no headings. Rules are an <ol>, numbered paragraphs ('1. ...')
    or paragraphs that start with a bold title."""
    intro, rules, current = [], [], None
    blocks = [
        el for el in root.find_all(["p", "ol", "ul", "blockquote"])
        if not el.find_parent(["ol", "ul", "blockquote", "li"])
    ]
    for el in blocks:
        if el.name == "ol":
            items = el.find_all("li", recursive=False)
            if len(items) >= 2:
                for li in items:
                    title, desc = split_title(li.get_text(), lead_strong(li))
                    current = {"number": len(rules) + 1, "title": title,
                               "description": desc, "links": links_in(li)}
                    rules.append(current)
                continue
        if el.name == "p":
            text = clean(el.get_text())
            if not text:
                continue
            m = NUMBERED.match(text)
            strong = lead_strong(el)
            if m:
                title, desc = split_title(m.group(2), strong)
                current = {"number": int(m.group(1)), "title": title,
                           "description": desc, "links": links_in(el)}
                rules.append(current)
                continue
            if strong:
                title, desc = split_title(text, strong)
                current = {"number": len(rules) + 1, "title": title,
                           "description": desc, "links": links_in(el)}
                rules.append(current)
                continue
        text = (" ".join("- " + clean(li.get_text()) for li in el.find_all("li"))
                if el.name in ("ul", "ol") else clean(el.get_text()))
        if not text:
            continue
        if current is None:
            intro.append(text)
        else:
            current["description"] = (current["description"] + " " + text).strip()
            current["links"].extend(links_in(el))
    return {"intro": " ".join(intro), "rules": rules}


def parse_rules(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    wiki_div = soup.select_one("div.md.wiki")
    root = wiki_div or soup

    result = parse_headings(root)
    if not result["rules"]:
        alt = parse_no_headings(root)
        if len(alt["rules"]) >= 2:  # avoid false positives
            result = alt
    if not result["rules"]:
        result["raw_text"] = clean(root.get_text())[:5000]
    result["wiki_div"] = wiki_div is not None
    return result


def parse_official_rules(body: str):
    """Reddit's built-in rules: /about/rules.json"""
    data = json.loads(body)
    out = []
    for i, r in enumerate(data.get("rules", [])):
        out.append({
            "number": int(r.get("priority", i)) + 1,
            "title": clean(r.get("short_name") or ""),
            "description": clean(r.get("description") or r.get("violation_reason") or ""),
            "links": [],
        })
    return out


# ----------------------------------------------------------------- fetchers
def save_debug(debug_dir, name, text):
    if debug_dir:
        (debug_dir / f"{name}.txt").write_text(text, encoding="utf-8")


def sub_name(url: str, fallback: str) -> str:
    m = re.search(r"/r/([^/?#]+)", url)
    return m.group(1) if m else fallback.replace("r/", "").strip()


class RequestsFetcher:
    """Plain HTTP. Frequently answered with 403 by Reddit."""

    def wiki_candidates(self, base, sub, debug_dir):
        old = base.replace("://www.reddit.com", "://old.reddit.com")
        sources = [
            ("wiki_json", f"{base}/wiki/rules.json", "json"),
            ("wiki_old", f"{old}/wiki/rules/", "html"),
            ("wiki_new", f"{base}/wiki/rules/", "html"),
        ]
        for src, url, kind in sources:
            status, body = http_get(url)
            save_debug(debug_dir, f"{sub}_{src}", f"{status}\n{body}")
            if status != 200:
                yield src, None, f"{src}: HTTP {status}"
            elif is_blocked(body):
                yield src, None, f"{src}: blocked by Reddit"
            elif kind == "json":
                try:
                    yield src, htmllib.unescape(json.loads(body)["data"]["content_html"]), ""
                except Exception:  # noqa: BLE001
                    yield src, None, f"{src}: no content_html"
            else:
                yield src, body, ""

    def sidebar_rules(self, base, sub, debug_dir):
        status, body = http_get(f"{base}/about/rules.json")
        save_debug(debug_dir, f"{sub}_about_rules", f"{status}\n{body}")
        if status != 200 or is_blocked(body):
            return None, f"about_rules: HTTP {status}"
        try:
            rules = parse_official_rules(body)
            return rules, f"about_rules: {len(rules)} rules"
        except Exception:  # noqa: BLE001
            return None, "about_rules: invalid JSON"

    def close(self):
        pass


class PrawFetcher:
    """Official Reddit API through PRAW (needs a free app key)."""

    def __init__(self):
        import praw  # noqa: PLC0415

        self.reddit = praw.Reddit(
            client_id=os.environ["REDDIT_CLIENT_ID"],
            client_secret=os.environ["REDDIT_CLIENT_SECRET"],
            user_agent=os.environ.get("REDDIT_USER_AGENT", "rules-scraper by u/your_username"),
        )
        self.reddit.read_only = True

    def wiki_candidates(self, base, sub, debug_dir):
        try:
            html = self.reddit.subreddit(sub).wiki["rules"].content_html
            save_debug(debug_dir, f"{sub}_wiki_api", html)
            yield "wiki_api", html, ""
        except Exception as e:  # noqa: BLE001
            yield "wiki_api", None, f"wiki_api: {type(e).__name__}"

    def sidebar_rules(self, base, sub, debug_dir):
        try:
            rules = []
            for i, r in enumerate(self.reddit.subreddit(sub).rules):
                rules.append({
                    "number": int(getattr(r, "priority", i) or i) + 1,
                    "title": clean(getattr(r, "short_name", "") or ""),
                    "description": clean(getattr(r, "description", "") or getattr(r, "violation_reason", "") or ""),
                    "links": [],
                })
            return rules, f"rules_api: {len(rules)} rules"
        except Exception as e:  # noqa: BLE001
            return None, f"rules_api: {type(e).__name__}"

    def close(self):
        pass


class BrowserFetcher:
    """Headless Chrome via Playwright: loads the page like a normal visitor."""

    def __init__(self):
        from playwright.sync_api import sync_playwright  # noqa: PLC0415

        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=True)
        ctx = self.browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
            locale="en-US",
        )
        self.page = ctx.new_page()

    def wiki_candidates(self, base, sub, debug_dir):
        try:
            resp = self.page.goto(f"{base}/wiki/rules/", wait_until="domcontentloaded", timeout=30000)
            status = resp.status if resp else None
            try:
                self.page.wait_for_selector("div.md.wiki", timeout=10000)
            except Exception:  # noqa: BLE001
                pass
            html = self.page.content()
            save_debug(debug_dir, f"{sub}_wiki_browser", f"{status}\n{html}")
            if status != 200:
                yield "wiki_browser", None, f"wiki_browser: HTTP {status}"
            else:
                yield "wiki_browser", html, ""
        except Exception as e:  # noqa: BLE001
            yield "wiki_browser", None, f"wiki_browser: {type(e).__name__}"

    def sidebar_rules(self, base, sub, debug_dir):
        try:
            resp = self.page.goto(f"{base}/about/rules.json", timeout=30000)
            status = resp.status if resp else None
            if status != 200:
                return None, f"about_rules: HTTP {status}"
            body = resp.text()
            save_debug(debug_dir, f"{sub}_about_rules", body)
            rules = parse_official_rules(body)
            return rules, f"about_rules: {len(rules)} rules"
        except Exception as e:  # noqa: BLE001
            return None, f"about_rules: {type(e).__name__}"

    def close(self):
        self.browser.close()
        self._pw.stop()


FETCHERS = {"requests": RequestsFetcher, "praw": PrawFetcher, "browser": BrowserFetcher}


def collect(fetcher, base: str, sub: str, debug_dir):
    notes, empty = [], None
    for src, html, note in fetcher.wiki_candidates(base, sub, debug_dir):
        if html is None:
            notes.append(note)
            continue
        parsed = parse_rules(html)
        notes.append(f"{src}: {len(parsed['rules'])} rules, wiki_div={parsed.pop('wiki_div')}")
        if parsed["rules"]:
            return parsed, "wiki", notes
        empty = empty or parsed

    rules, note = fetcher.sidebar_rules(base, sub, debug_dir)
    notes.append(note)
    if rules:
        return {"intro": "", "rules": rules}, "sidebar_rules", notes
    return (empty or {"intro": "", "rules": []}), None, notes


def main(csv_path: str, out_path: str, method: str, debug: bool) -> None:
    debug_dir = Path("debug") if debug else None
    if debug_dir:
        debug_dir.mkdir(exist_ok=True)
    fetcher = FETCHERS[method]()

    results = []
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                url = row["subreddit_url"].strip()
                base = url.rstrip("/")
                sub = sub_name(url, row["subreddit"])
                entry = {
                    "language": row["language"].strip(),
                    "subreddit": row["subreddit"].strip(),
                    "subreddit_url": url,
                    "focus": row["focus"].strip(),
                    "community_type": row["community_type"].strip(),
                    "rules_url": base + "/wiki/rules/",
                }
                parsed, source, notes = collect(fetcher, base, sub, debug_dir)
                entry.update(parsed)
                entry["rules_source"] = source
                entry["status"] = "ok" if parsed["rules"] else "no_rules_found"
                entry["fetch_notes"] = notes
                line = f"{entry['subreddit']}: {entry['status']} via {source} ({len(parsed['rules'])} rules)"
                if entry["status"] != "ok":
                    line += "  <- " + " | ".join(notes)
                    if any("wiki_div=False" in n for n in notes):
                        line += "  [page loaded but is not the wiki: probably a bot-check; use --method browser/praw]"
                print(line)
                results.append(entry)
                with open(out_path, "w", encoding="utf-8") as out:  # save progress each row
                    json.dump(results, out, ensure_ascii=False, indent=2)
                time.sleep(DELAY)
    finally:
        fetcher.close()
    print(f"Saved {len(results)} communities to {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("out")
    ap.add_argument("--method", choices=list(FETCHERS), default="requests")
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    main(a.csv, a.out, a.method, a.debug)