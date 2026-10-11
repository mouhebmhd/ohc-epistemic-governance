#!/usr/bin/env python3
"""
Reproducible cleaning pipeline for reddit_health_communities.json.

Outputs:
  cleaned_communities.json
  atomic_rules.jsonl
  atomic_rules.csv
  governance_vacuum_communities.json
  cleaning_log.csv
  cleaning_summary.json
  summary_by_language.csv
  summary_by_community.csv
  manual_review.csv

Important:
- The raw input is never modified.
- Heuristic splits and navigation classification should be manually reviewed.
- Community-level governance-vacuum records are preserved separately, not deleted.
"""

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


# ----------------------------- Configuration -----------------------------

SYSTEM_TITLE_PATTERNS = [
    re.compile(r'^["“\']?rules["”\']?\s+does\s+not\s+exist$', re.I),
    re.compile(r'^this\s+wiki\s+has\s+been\s+disabled\.?$', re.I),
    re.compile(r'^this\s+page\s+has\s+been\s+disabled\.?$', re.I),
    re.compile(r'^(?:r/)?[\w.-]+\s+is\s+banned$', re.I),
]

HEADER_TITLES = {
    "rules", "policies", "community bookmarks",
    "community rules", "community guidelines",
}

NAV_TITLES = {
    "related subreddits", "related subs", "related communities",
    "subreddits amis", "similar communities", "sibling subreddits",
    "other communities", "friendly communities", "other subreddits",
    "subs d'utilité publique", "intervilles", "communauté",
    "installed apps", "apply to be a moderator",
    "want to join the mod team?", "filter by", "filter posts by flair",
    "search by post flair", "community tags", "post flairs", "flairs",
    "flair filters", "quicklinks", "quick links", "quick info",
    "helpful links", "useful links!", "interesting posts",
    "popular discussions", "resources", "info", "announcements",
    "message", "welcome", "colophon", "faq", "faqs & quick links",
    "reddit mental health network", "news from rmhn", "sister sub",
    "top art of the week", "art of the week", "community cloud",
    "crisis?", "prescription assistance", "stigma smashing discords",
    "stigma smashing communities", "this sub is lgbtq+ friendly",
    "twox helplines", "twox resources", "r/bangalore wiki",
    "discord!", "discord", "join us on discord", "sultanate of oman",
    "glimpses of oman", "subscriber info", "helpful external links",
    "redesign information", "community information",
    "reddit's disclaimers", "communities", "related subreddits",
    "campaigns",
}

# The exact footer start from the protocol, plus a conservative fallback
# for common Reddit footer text. Truncate from the earliest match.
FOOTER_PATTERNS = [
    re.compile(
        r'Home\s*-\s*Popular\s*-\s*News\s*-\s*Explore\s*-\s*'
        r'Best of Reddit\s*-\s*Best of Reddit in Portuguese\s*-\s*'
        r'Best of Reddit in German\s*-\s*Reddit Rules\s*-\s*Privacy Policy\s*-\s*'
        r'User Agreement\s*-\s*Accessibility\s*-\s*Reddit,\s*Inc\.\s*©\s*202\d',
        re.I | re.S,
    ),
    re.compile(r'\bReddit uses cookies and similar technologies to:', re.I),
]

VACUUM_STATUS = {"no_rules_found", "banned", "http_404", "404", "wiki_disabled"}

LIST_MARKER = re.compile(
    r'(?m)^\s*(?:[-*•▪◦‣]|\d{1,3}[.)]|[A-Za-z][.)])\s+'
)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_title(value):
    value = str(value or "").lower()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def clean_text(value):
    if value is None:
        return ""
    return str(value).replace("\u00a0", " ").strip()


def load_communities(path):
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = next(
            (data[k] for k in ("communities", "data", "results", "items")
             if isinstance(data.get(k), list)),
            None,
        )
        if items is None:
            items = [data]
    else:
        raise ValueError("JSON root must be a list or object.")
    if not all(isinstance(x, dict) for x in items):
        raise ValueError("Every community record must be an object.")
    return items


def log_event(log, stage, community, rule_id, action, reason, notes=""):
    log.append({
        "timestamp": now_iso(),
        "stage": stage,
        "language": clean_text(community.get("language")) or "Unknown",
        "subreddit": clean_text(community.get("subreddit")),
        "rule_id": rule_id,
        "action": action,
        "reason": reason,
        "notes": notes,
    })


def is_system_rule(rule, subreddit):
    title = clean_text(rule.get("title"))
    for pattern in SYSTEM_TITLE_PATTERNS:
        if pattern.fullmatch(title):
            return True
    # The protocol's "[subreddit] is banned" condition.
    if subreddit:
        title_norm = normalize_title(title)
        sub_norm = normalize_title(subreddit.replace("r/", ""))
        if title_norm == f"{sub_norm} is banned":
            return True
    return False


def description_is_link_only(description, links):
    desc = clean_text(description)
    if not desc:
        return True
    # Empty after removing markdown links and bare URLs means link-only.
    no_links = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', desc)
    no_links = re.sub(r'https?://\S+', '', no_links)
    no_links = re.sub(r'(?m)^\s*[-*•]?\s*$', '', no_links)
    # If it consists only of listed link labels or is explicitly represented
    # by the structured links array, treat as link-only.
    if not no_links.strip() and links:
        return True
    if links and normalize_title(no_links) in {
        normalize_title(x.get("text", "")) for x in links if isinstance(x, dict)
    }:
        return True
    return False


def is_header(rule):
    title = normalize_title(rule.get("title"))
    return title in {normalize_title(x) for x in HEADER_TITLES}


def is_navigation(rule):
    title = normalize_title(rule.get("title"))
    if title in {normalize_title(x) for x in NAV_TITLES}:
        return True
    # Allow punctuation/case variations but not arbitrary substring matches.
    return False


def truncate_footer(text):
    original = clean_text(text)
    cut_at = None
    for pattern in FOOTER_PATTERNS:
        match = pattern.search(original)
        if match and (cut_at is None or match.start() < cut_at):
            cut_at = match.start()
    if cut_at is None:
        return original, False
    return original[:cut_at].rstrip(), True


def split_compound_text(text):
    """
    Conservative splitting:
    - Split on explicit line-based bullets/numbered items.
    - Otherwise retain a sentence as a unit.
    - Do not automatically split on every sentence; that risks breaking
      multi-clause rules. Such cases can be reviewed manually.
    """
    text = clean_text(text)
    if not text:
        return []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1 and any(LIST_MARKER.match(line) for line in lines):
        pieces = []
        current = []
        for line in lines:
            if LIST_MARKER.match(line):
                if current:
                    pieces.append(" ".join(current).strip())
                line = LIST_MARKER.sub("", line, count=1).strip()
                current = [line] if line else []
            elif current:
                current.append(line)
            else:
                # Introductory text is retained as its own piece for review.
                current = [line]
        if current:
            pieces.append(" ".join(current).strip())
        return [p for p in pieces if p]

    # Inline bullet lists are split only where there is a clear bullet marker.
    inline = re.split(r'\s+(?:[-•▪◦])\s+', text)
    if len(inline) > 1:
        return [p.strip() for p in inline if p.strip()]

    # Numbered inline lists: "1. ... 2. ..." when clearly repeated.
    numbered = re.split(r'\s+(?=\d{1,2}[.)]\s+)', text)
    if len(numbered) > 1:
        numbered = [re.sub(r'^\d{1,2}[.)]\s+', '', p).strip() for p in numbered]
        return [p for p in numbered if p]

    return [text]


def community_is_vacuum(community):
    status = clean_text(community.get("status")).lower().replace(" ", "_")
    source = clean_text(community.get("rules_source")).lower()
    notes = " ".join(str(x) for x in (community.get("fetch_notes") or [])).lower()
    raw_text = clean_text(community.get("raw_text")).lower()
    signals = " ".join([status, source, notes, raw_text])
    if status in VACUUM_STATUS:
        return True, f"status:{status}"
    if re.search(r'\b(banned|http\s*404|404 not found|wiki (?:has been )?disabled|page has been disabled)\b', signals):
        return True, "inaccessible_or_banned_signal"
    return False, ""


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Clean Reddit community rules and write audit trail.")
    parser.add_argument("--input", default="reddit_health_communities.json")
    parser.add_argument("--output-dir", default="reddit_cleaning_output")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_communities = load_communities(input_path)
    log = []
    cleaned_communities = []
    vacuum_communities = []
    atomic_rules = []
    manual_review = []

    counters = Counter()
    per_language = defaultdict(Counter)
    community_seen = defaultdict(dict)

    for ci, raw_community in enumerate(raw_communities):
        community = deepcopy(raw_community)
        language = clean_text(community.get("language")) or "Unknown"
        subreddit = clean_text(community.get("subreddit"))
        rules = community.get("rules", [])
        if not isinstance(rules, list):
            rules = []
            community["rules"] = []

        # Stage 7: keep inaccessible-governance communities in a separate file.
        vacuum, vacuum_reason = community_is_vacuum(community)
        if vacuum:
            vacuum_communities.append({
                **community,
                "governance_vacuum_reason": vacuum_reason,
                "excluded_from_rule_analysis": True,
            })
            log_event(log, 7, community, "", "excluded", "EXC", vacuum_reason)
            counters["stage7_communities_moved"] += 1
            per_language[language]["stage7_communities_moved"] += 1
            # Do not treat inaccessible records as an analytic rule corpus.
            continue

        kept_rules = []
        for ri, original_rule in enumerate(rules):
            if not isinstance(original_rule, dict):
                log_event(log, 0, community, f"{subreddit}:{ri}", "removed", "INVALID", "Rule entry is not an object.")
                counters["invalid_rule_objects"] += 1
                per_language[language]["invalid_rule_objects"] += 1
                continue

            rule = deepcopy(original_rule)
            rule_id = f"{subreddit}:{ri}"
            title = clean_text(rule.get("title"))
            description = clean_text(rule.get("description"))
            links = rule.get("links", [])
            if not isinstance(links, list):
                links = []
                rule["links"] = []

            # Stage 1: platform/system status.
            if is_system_rule(rule, subreddit):
                log_event(log, 1, community, rule_id, "removed", "SYS", f"System-status title: {title}")
                counters["stage1_removed"] += 1
                per_language[language]["stage1_removed"] += 1
                continue

            # Stage 2: structural headers only when empty/link-only.
            if is_header(rule) and description_is_link_only(description, links):
                log_event(log, 2, community, rule_id, "removed", "HDR", f"Header with empty/link-only description: {title}")
                counters["stage2_removed"] += 1
                per_language[language]["stage2_removed"] += 1
                continue
            elif is_header(rule) and description:
                log_event(log, 2, community, rule_id, "retained", "HDR_REVIEW", "Header-like title has content; retained and sent for review/splitting.")
                manual_review.append({
                    "language": language, "subreddit": subreddit, "rule_id": rule_id,
                    "reason": "header_title_with_content", "title": title,
                    "description": description,
                })

            # Stage 3: navigation/directory entries.
            if is_navigation(rule):
                log_event(log, 3, community, rule_id, "removed", "NAV", f"Navigation/directory title: {title}")
                counters["stage3_removed"] += 1
                per_language[language]["stage3_removed"] += 1
                continue

            # Stage 4: truncate boilerplate in description.
            truncated_description, was_truncated = truncate_footer(description)
            if was_truncated:
                rule["description"] = truncated_description
                description = truncated_description
                log_event(log, 4, community, rule_id, "truncated", "BOIL", "Truncated platform footer from description.")
                counters["stage4_descriptions_truncated"] += 1
                per_language[language]["stage4_descriptions_truncated"] += 1
                if not description and not title:
                    log_event(log, 4, community, rule_id, "removed", "BOIL_EMPTY", "No content remained after footer truncation.")
                    continue

            # Stage 5: split descriptions that clearly contain list items.
            combined = description if description else title
            pieces = split_compound_text(combined)
            # If title is meaningful and description has text, preserve title as
            # parent category and split description into atomic children.
            split_source = description if description else title
            children = split_compound_text(split_source)
            if len(children) > 1:
                counters["stage5_parent_entries_split"] += 1
                counters["stage5_atomic_records_created"] += len(children)
                per_language[language]["stage5_parent_entries_split"] += 1
                per_language[language]["stage5_atomic_records_created"] += len(children)
                log_event(log, 5, community, rule_id, "split", "SPLIT", f"Created {len(children)} child entries.")
            else:
                children = [split_source] if split_source else [""]
                log_event(log, 5, community, rule_id, "retained", "KEEP", "No clear list boundary detected; retained as one entry.")

            for child_i, child in enumerate(children, start=1):
                # If the original description was split, use each child as
                # atomic description and retain original title as category.
                atomic_title = title if description else (child if child else title)
                atomic_description = child if description else ""
                if len(children) > 1 and description:
                    # Give each child its own text-based title so Stage 6
                    # does not collapse distinct bullets sharing a parent heading.
                    # The original heading remains in parent_title.
                    atomic_title = child
                    atomic_description = ""

                atom = {
                    "atomic_rule_id": f"{subreddit}_{ri+1}_{child_i}",
                    "language": language,
                    "subreddit": subreddit,
                    "subreddit_url": community.get("subreddit_url", ""),
                    "focus": community.get("focus", ""),
                    "community_type": community.get("community_type", ""),
                    "rules_url": community.get("rules_url", ""),
                    "rules_source": community.get("rules_source", ""),
                    "parent_rule_index": ri,
                    "parent_rule_number": rule.get("number"),
                    "parent_title": title,
                    "atomic_index": child_i,
                    "title": atomic_title,
                    "description": atomic_description,
                    "text": (atomic_title + " " + atomic_description).strip(),
                    "links": links if child_i == 1 else [],
                    "cleaning_flags": [],
                }
                if len(children) > 1:
                    atom["cleaning_flags"].append("split_from_compound_entry")
                if is_header(rule) and description:
                    atom["cleaning_flags"].append("header_like_parent_review")
                if not atomic_description.strip() and not atomic_title.strip():
                    atom["cleaning_flags"].append("empty_atomic_text")
                    manual_review.append({
                        "language": language, "subreddit": subreddit,
                        "rule_id": atom["atomic_rule_id"], "reason": "empty_atomic_text",
                        "title": atomic_title, "description": atomic_description,
                    })
                atomic_rules.append(atom)
                kept_rules.append({
                    **rule,
                    "title": atomic_title,
                    "description": atomic_description,
                    "atomic_rule_id": atom["atomic_rule_id"],
                    "parent_rule_index": ri,
                    "atomic_index": child_i,
                })
                counters["stage5_records_emitted"] += 1
                per_language[language]["stage5_records_emitted"] += 1

        # Stage 6: deduplicate by (subreddit, normalized title), keeping richer description.
        best_by_key = {}
        for rule in kept_rules:
            key = (subreddit.lower(), normalize_title(rule.get("title")))
            if not key[1]:
                key = (subreddit.lower(), f"__empty_title_{rule.get('atomic_rule_id', '')}")
            existing = best_by_key.get(key)
            if existing is None:
                best_by_key[key] = rule
            else:
                old_desc = clean_text(existing.get("description"))
                new_desc = clean_text(rule.get("description"))
                if len(new_desc) > len(old_desc):
                    discarded = existing
                    best_by_key[key] = rule
                else:
                    discarded = rule
                log_event(log, 6, community, discarded.get("atomic_rule_id", ""), "removed", "DUP",
                          f"Duplicate normalized title; retained richer description for key={key[1]!r}.")
                counters["stage6_duplicates_removed"] += 1
                per_language[language]["stage6_duplicates_removed"] += 1

        final_rules = list(best_by_key.values())
        community["rules"] = final_rules
        community["cleaning_metadata"] = {
            "raw_rule_entries": len(rules),
            "cleaned_rule_entries": len(final_rules),
            "excluded_from_rule_analysis": False,
        }
        cleaned_communities.append(community)

    # Dedup atomic list against the same community/title key. Rebuild from final community rules
    # so the rule-level corpus and community JSON remain consistent.
    atomic_rules = []
    for community in cleaned_communities:
        language = clean_text(community.get("language")) or "Unknown"
        subreddit = clean_text(community.get("subreddit"))
        for ri, rule in enumerate(community.get("rules", [])):
            atomic_rules.append({
                "atomic_rule_id": rule.get("atomic_rule_id", f"{subreddit}_{ri+1}_1"),
                "language": language,
                "subreddit": subreddit,
                "subreddit_url": community.get("subreddit_url", ""),
                "focus": community.get("focus", ""),
                "community_type": community.get("community_type", ""),
                "rules_url": community.get("rules_url", ""),
                "rules_source": community.get("rules_source", ""),
                "parent_rule_index": rule.get("parent_rule_index", ri),
                "parent_rule_number": rule.get("number"),
                "parent_title": rule.get("title", ""),
                "atomic_index": rule.get("atomic_index", 1),
                "title": rule.get("title", ""),
                "description": rule.get("description", ""),
                "text": (clean_text(rule.get("title")) + " " + clean_text(rule.get("description"))).strip(),
                "links": rule.get("links", []),
                "cleaning_flags": rule.get("cleaning_flags", []),
            })

    # Final corpus rows that still look like platform/navigation content are flagged, not auto-deleted.
    for atom in atomic_rules:
        title_norm = normalize_title(atom["title"])
        text = atom["text"]
        if title_norm in {"installed apps", "community bookmarks", "quick info"}:
            manual_review.append({
                "language": atom["language"], "subreddit": atom["subreddit"],
                "rule_id": atom["atomic_rule_id"], "reason": "possible_navigation_residual",
                "title": atom["title"], "description": atom["description"],
            })
        if re.search(r"\b(?:no|must|do not|don\'t|禁止|يمنع|لا)\b", text, re.I) is False:
            # Not all legitimate rules contain these words, so this is only a review cue.
            if len(text) < 12:
                manual_review.append({
                    "language": atom["language"], "subreddit": atom["subreddit"],
                    "rule_id": atom["atomic_rule_id"], "reason": "very_short_text_review",
                    "title": atom["title"], "description": atom["description"],
                })

    # Write outputs.
    write_json(output_dir / "cleaned_communities.json", cleaned_communities)
    write_json(output_dir / "governance_vacuum_communities.json", vacuum_communities)

    with (output_dir / "atomic_rules.jsonl").open("w", encoding="utf-8") as f:
        for atom in atomic_rules:
            f.write(json.dumps(atom, ensure_ascii=False) + "\n")

    flat_atoms = []
    for atom in atomic_rules:
        flat_atoms.append({
            **{k: v for k, v in atom.items() if k not in {"links", "cleaning_flags"}},
            "links_json": json.dumps(atom.get("links", []), ensure_ascii=False),
            "cleaning_flags": "|".join(atom.get("cleaning_flags", [])),
        })
    atom_fields = list(flat_atoms[0].keys()) if flat_atoms else [
        "atomic_rule_id", "language", "subreddit", "title", "description", "text"
    ]
    with (output_dir / "atomic_rules.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=atom_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flat_atoms)

    log_fields = ["timestamp", "stage", "language", "subreddit", "rule_id", "action", "reason", "notes"]
    with (output_dir / "cleaning_log.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=log_fields)
        writer.writeheader()
        writer.writerows(log)

    review_fields = ["language", "subreddit", "rule_id", "reason", "title", "description"]
    with (output_dir / "manual_review.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=review_fields)
        writer.writeheader()
        writer.writerows(manual_review)

    # Counts from audit events; stage 5 is reported as both split parents and emitted records.
    stage_counts = {}
    for row in log:
        stage = str(row["stage"])
        key = f"stage_{stage}_{row['action']}_{row['reason']}"
        stage_counts[key] = stage_counts.get(key, 0) + 1

    by_language_rows = []
    for lang in sorted(set([clean_text(c.get("language")) or "Unknown" for c in raw_communities])):
        raw_n = sum(1 for c in raw_communities if (clean_text(c.get("language")) or "Unknown") == lang)
        cleaned_n = sum(1 for c in cleaned_communities if (clean_text(c.get("language")) or "Unknown") == lang)
        vacuum_n = sum(1 for c in vacuum_communities if (clean_text(c.get("language")) or "Unknown") == lang)
        raw_rules = sum(len(c.get("rules", [])) for c in raw_communities
                        if (clean_text(c.get("language")) or "Unknown") == lang
                        and isinstance(c.get("rules", []), list))
        final_rules = sum(1 for a in atomic_rules if a["language"] == lang)
        lang_counter = per_language[lang]
        by_language_rows.append({
            "language": lang, "raw_communities": raw_n,
            "cleaned_communities": cleaned_n, "governance_vacuum_communities": vacuum_n,
            "raw_rule_entries": raw_rules, "final_rule_records": final_rules,
            **dict(lang_counter),
        })

    def write_rows(path, rows):
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        fields = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    write_rows(output_dir / "summary_by_language.csv", by_language_rows)

    community_summary = []
    for c in cleaned_communities:
        community_summary.append({
            "language": c.get("language", "Unknown"),
            "subreddit": c.get("subreddit", ""),
            "status": c.get("status", ""),
            "rules_source": c.get("rules_source", ""),
            "raw_rule_entries": c.get("cleaning_metadata", {}).get("raw_rule_entries", 0),
            "cleaned_rule_entries": c.get("cleaning_metadata", {}).get("cleaned_rule_entries", 0),
        })
    write_rows(output_dir / "summary_by_community.csv", community_summary)

    summary = {
        "input_file": str(input_path),
        "generated_at": now_iso(),
        "raw_communities": len(raw_communities),
        "cleaned_communities": len(cleaned_communities),
        "governance_vacuum_communities": len(vacuum_communities),
        "raw_rule_entries": sum(
            len(c.get("rules", [])) for c in raw_communities
            if isinstance(c.get("rules", []), list)
        ),
        "final_atomic_rule_records": len(atomic_rules),
        "manual_review_items": len(manual_review),
        "stage_event_counts": stage_counts,
        "counters": dict(counters),
        "important_note": (
            "Counts are computed from this input. Stage 5 uses conservative list-boundary splitting; "
            "sentence-level splitting is not automatic. Inspect manual_review.csv and validate rules "
            "before using the corpus for inferential or substantive analysis."
        ),
    }
    write_json(output_dir / "cleaning_summary.json", summary)

    print("=" * 68)
    print("CLEANING FINISHED")
    print("=" * 68)
    print(f"Raw communities:                {summary['raw_communities']}")
    print(f"Communities retained:           {summary['cleaned_communities']}")
    print(f"Governance-vacuum communities:   {summary['governance_vacuum_communities']}")
    print(f"Raw rule entries:               {summary['raw_rule_entries']}")
    print(f"Final atomic rule records:      {summary['final_atomic_rule_records']}")
    print(f"Manual-review items:            {summary['manual_review_items']}")
    print(f"Output directory:               {output_dir.resolve()}")
    print("\nReview cleaning_summary.json, summary_by_language.csv, cleaning_log.csv,")
    print("and manual_review.csv before treating the cleaned corpus as final.")


if __name__ == "__main__":
    main()
