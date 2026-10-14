#!/usr/bin/env python3
"""Build configuration.csv from a Reddit community metadata dump.

Usage:
    python build_configuration.py [input.json] [configuration.csv] [logs/build_configuration.log]
"""
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

INPUT = sys.argv[1] if len(sys.argv) > 1 else "reddit_health_communities_metadata.json"
OUTPUT = sys.argv[2] if len(sys.argv) > 2 else "configuration.csv"
LOGFILE = sys.argv[3] if len(sys.argv) > 3 else "logs/build_configuration.log"

TARGET_LANGS = {"en", "es", "fr", "hi", "ar"}

GOVERNANCE_FIELDS = [
    # Access
    "subreddit_type", "restrict_posting", "restrict_commenting",
    "disable_contributor_requests", "accept_followers", "allow_discovery", "quarantine",
    # Content
    "allow_images", "allow_videos", "allow_galleries", "allow_videogifs",
    "allow_polls", "allow_predictions", "allow_talks", "submission_type", "over18",
    "all_original_content",
    # Classification
    "link_flair_enabled", "link_flair_position", "user_flair_enabled_in_sr",
    "can_assign_link_flair", "can_assign_user_flair", "original_content_tag_enabled",
    "spoilers_enabled",
    # Knowledge
    "wiki_enabled", "submit_text", "description", "public_description",
    # Visibility
    "comment_score_hide_mins", "collapse_deleted_comments", "suggested_comment_sort",
    "hide_ads", "show_media", "show_media_preview",
    # Scale
    "subscribers", "created_utc",
]

COLUMNS = (
    ["subreddit_name", "language", "disease_category", "sample_group"]
    + GOVERNANCE_FIELDS
    + ["community_age_days"]
)

# Order matters: first matching category wins.
KEYWORDS = [
    ("chronic", ["cfs", "lupus", "fibro", "pots", "chron", "pain", "migraine", "diabet",
                 "crohn", "colitis", "ibs", "endo", "pcos", "hypothyroid", "ms", "ehlers"]),
    ("mental_health", ["anx", "depress", "adhd", "bipolar", "bpd", "ptsd", "ocd",
                       "schizo", "mental"]),
    ("infectious", ["covid", "hiv", "herpes", "std", "lyme", "shingles", "infect", "virus"]),
    ("surgical", ["surg", "scolio", "spine", "back", "shoulder"]),
    ("general", ["health", "medicine", "askdocs", "medical", "diagnose"]),
]


def map_language(raw):
    if not isinstance(raw, str) or not raw.strip():
        return "unknown"
    code = raw.strip().lower().replace("_", "-").split("-")[0]
    return code if code in TARGET_LANGS else "unknown"


def assign_category(name_lc):
    for category, words in KEYWORDS:
        if any(w in name_lc for w in words):
            return category
    return "general"


def assign_sample_group(language, data):
    if data.get("subreddit_type") in ("private", "archived") or data.get("quarantine") is True:
        return "governance_vacuum"
    if language == "en":
        return "english_core"
    if language in ("es", "fr", "hi", "ar"):
        return "multilingual"
    return "unclassified"  # language unknown: spec doesn't say; flagged for review


def iter_records(path):
    """Yield (line_no, record_or_None, error_or_None).

    Primary mode: JSONL (one record per line). Tolerates trailing commas and
    stray '[' / ']' lines. If the file turns out to be pretty-printed
    multi-line JSON, falls back to a streaming decoder.
    """
    text = Path(path).read_text(encoding="utf-8")
    first = next((l.strip() for l in text.splitlines() if l.strip()), "")
    jsonl = False
    if first.rstrip(",").startswith("{"):
        try:
            json.loads(first.rstrip(","))
            jsonl = True
        except json.JSONDecodeError:
            pass

    if jsonl:
        for n, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if not s:
                yield n, None, "blank line"
                continue
            if s in ("[", "]", ","):
                yield n, None, "array bracket/separator line"
                continue
            try:
                yield n, json.loads(s.rstrip(",")), None
            except json.JSONDecodeError as e:
                yield n, None, f"invalid JSON ({e.msg})"
    else:
        dec = json.JSONDecoder()
        i, n = 0, 0
        while i < len(text):
            while i < len(text) and text[i] in " \t\r\n,[]":
                i += 1
            if i >= len(text):
                break
            n += 1
            try:
                obj, i = dec.raw_decode(text, i)
                yield n, obj, None
            except json.JSONDecodeError as e:
                yield n, None, f"invalid JSON ({e.msg}) near char {i}"
                break  # cannot resync reliably


def main():
    now = time.time()
    total = parsed = 0
    skipped = []  # (line_no, reason)
    rows = {}  # lowercased name -> row dict

    for line_no, rec, err in iter_records(INPUT):
        total += 1
        if err:
            skipped.append((line_no, err))
            continue
        if not isinstance(rec, dict):
            skipped.append((line_no, "record is not a JSON object"))
            continue

        data = ((rec.get("metadata") or {}).get("data")) if isinstance(rec.get("metadata"), dict) else None
        if not isinstance(data, dict):
            skipped.append((line_no, "missing metadata.data" +
                            (f" (collection_error={rec.get('collection_error')})" if rec.get("collection_error") else "")))
            continue
        name = data.get("display_name")
        if not isinstance(name, str) or not name.strip():
            skipped.append((line_no, "missing display_name"))
            continue
        parsed += 1

        key = name.lower()
        if key in rows:
            skipped.append((line_no, f"duplicate community '{name}' (kept first occurrence)"))
            continue

        language = map_language(data.get("lang"))
        row = {
            "subreddit_name": name,
            "language": language,
            "disease_category": assign_category(key),
            "sample_group": assign_sample_group(language, data),
        }
        for f in GOVERNANCE_FIELDS:
            row[f] = data.get(f)  # None if missing

        created = data.get("created_utc")
        row["community_age_days"] = (
            int((now - created) // 86400) if isinstance(created, (int, float)) else None
        )
        rows[key] = row

    ordered = sorted(
        rows.values(),
        key=lambda r: (r["language"], r["disease_category"], r["subreddit_name"].lower()),
    )

    with open(OUTPUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in ordered:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})

    Path(LOGFILE).parent.mkdir(parents=True, exist_ok=True)
    lang_c = Counter(r["language"] for r in ordered)
    cat_c = Counter(r["disease_category"] for r in ordered)
    grp_c = Counter(r["sample_group"] for r in ordered)
    with open(LOGFILE, "w", encoding="utf-8") as lg:
        lg.write(f"Run at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}\n")
        lg.write(f"Input: {INPUT}\nOutput: {OUTPUT}\n\n")
        lg.write(f"Total lines read: {total}\n")
        lg.write(f"Lines parsed successfully: {parsed}\n")
        lg.write(f"Lines skipped: {len(skipped)}\n")
        for ln, reason in skipped:
            lg.write(f"  - line {ln}: {reason}\n")
        lg.write(f"\nUnique communities: {len(ordered)}\n")
        for title, c in (("Count per language", lang_c),
                         ("Count per disease category", cat_c),
                         ("Count per sample group", grp_c)):
            lg.write(f"\n{title}:\n")
            for k, v in sorted(c.items()):
                lg.write(f"  {k}: {v}\n")

    print(f"Wrote {len(ordered)} rows to {OUTPUT}; log at {LOGFILE}")


if __name__ == "__main__":
    main()