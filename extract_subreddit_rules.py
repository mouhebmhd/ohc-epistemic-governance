
import json
import re
import html
from pathlib import Path
from bs4 import BeautifulSoup

INPUT_FILE = Path("data/reddit_health_communities_metadata.json")
OUTPUT_FILE = Path("data/reddit_health_communities_with_rules_v2.json")


RULE_HINTS = re.compile(
    r"\brules?\b|"
    r"\bmust not\b|\bmust\b|\bprohibited\b|"
    r"\bnot allowed\b|\bdo not\b|\bdon't\b|"
    r"\bposting guidelines\b|\bguidelines\b|"
    r"\bmoderation\b|\brespect\b|\bspam\b",
    re.IGNORECASE,
)

NUMBERED_RULE = re.compile(
    r"^\s*(\d{1,2})\s*[.)]\s*(.+?)\s*$"
)

NUMBERED_SUBRULE = re.compile(
    r"^\s*(\d{1,2}[a-zA-Z])\s*[.)]\s*(.+?)\s*$"
)


def decode_html(text, max_passes=6):
    for _ in range(max_passes):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    return text


def normalize(text):
    return re.sub(r"\s+", " ", text).strip()


def walk_strings(obj, path="$"):
    """Yield every string field recursively with its JSON path."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from walk_strings(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from walk_strings(value, f"{path}[{i}]")
    elif isinstance(obj, str) and obj.strip():
        yield path, obj


def text_blocks(raw_text):
    """Convert HTML or Markdown/plain text into ordered text blocks."""
    decoded = decode_html(raw_text)

    if re.search(r"<(?:h[1-6]|li|p|div|ul|ol)\b", decoded, re.I):
        soup = BeautifulSoup(decoded, "html.parser")
        blocks = []

        for element in soup.find_all(
            ["h1", "h2", "h3", "h4", "li", "p"]
        ):
            text = normalize(element.get_text(" ", strip=True))
            if text:
                blocks.append((element.name, text))

        if blocks:
            return blocks

    blocks = []

    for line in decoded.splitlines():
        line = line.strip()
        if not line:
            continue

        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"^\d+[\.)]\s*", lambda m: m.group(0), line)
        blocks.append(("text", normalize(line)))

    return blocks


def score_candidate(path, value):
    """Rank fields likely to contain community rules."""
    decoded = decode_html(value)
    lower_path = path.lower()

    score = 0

    if "rule" in lower_path or "guideline" in lower_path:
        score += 10

    if "description" in lower_path:
        score += 3

    if RULE_HINTS.search(decoded):
        score += 3

    if re.search(r"<li\b|<h[1-6]\b|^\s*#{1,6}\s", decoded, re.I | re.M):
        score += 2

    if re.search(r"(?m)^\s*\d{1,2}\s*[.)]\s+\S", decoded):
        score += 4

    # Ignore very short values and obvious non-prose values.
    if len(decoded.strip()) < 40:
        score -= 5

    return score


def extract_rules_from_blocks(blocks):
    rules = []
    current_rule = None

    for tag, text in blocks:
        main = NUMBERED_RULE.match(text)

        if main and tag in {"h1", "h2", "h3", "h4", "text"}:
            number, title = main.groups()

            # Avoid treating numbered subrules as main rules.
            if re.match(r"^\d+[a-zA-Z]\s*[.)]", text):
                continue

            current_rule = {
                "number": number,
                "title": title.strip(),
                "items": [],
            }
            rules.append(current_rule)
            continue

        sub = NUMBERED_SUBRULE.match(text)

        if sub and current_rule is not None:
            item_number, title = sub.groups()

            if item_number[:-1] == current_rule["number"]:
                current_rule["items"].append({
                    "number": item_number,
                    "title": title.strip(),
                })

    return rules


def main():
    with INPUT_FILE.open("r", encoding="utf-8") as f:
        dataset = json.load(f)

    if not isinstance(dataset, list):
        raise ValueError("Expected a JSON list.")

    processed = 0
    communities_with_rules = 0
    total_main_rules = 0
    total_subrules = 0

    for record in dataset:
        if not isinstance(record, dict):
            continue

        candidates = []

        # Search every nested string field, regardless of its name.
        for path, value in walk_strings(record):
            score = score_candidate(path, value)

            if score > 0:
                blocks = text_blocks(value)
                rules = extract_rules_from_blocks(blocks)

                candidates.append({
                    "path": path,
                    "score": score,
                    "rules": rules,
                })

        # Prefer fields with actual extracted rules, then higher scores.
        candidates.sort(
            key=lambda item: (
                bool(item["rules"]),
                len(item["rules"]),
                item["score"],
            ),
            reverse=True,
        )

        # Merge rules from candidate fields, deduplicating by number/title.
        merged_rules = []
        main_index = {}

        for candidate in candidates:
            for rule in candidate["rules"]:
                key = (rule["number"], rule["title"].casefold())

                if key not in main_index:
                    copied = {
                        "number": rule["number"],
                        "title": rule["title"],
                        "items": [],
                    }
                    main_index[key] = copied
                    merged_rules.append(copied)

                existing = main_index[key]
                known_items = {
                    (item["number"], item["title"].casefold())
                    for item in existing["items"]
                }

                for item in rule["items"]:
                    item_key = (
                        item["number"],
                        item["title"].casefold(),
                    )
                    if item_key not in known_items:
                        existing["items"].append(item)
                        known_items.add(item_key)

        record["rules"] = merged_rules
        record["rules_extraction"] = {
            "candidate_fields_checked": len(candidates),
            "source_paths_with_rules": [
                c["path"] for c in candidates if c["rules"]
            ],
            "main_rule_count": len(merged_rules),
            "subrule_count": sum(
                len(rule["items"]) for rule in merged_rules
            ),
        }

        processed += 1

        if merged_rules:
            communities_with_rules += 1
            total_main_rules += len(merged_rules)
            total_subrules += sum(
                len(rule["items"]) for rule in merged_rules
            )

    temp = OUTPUT_FILE.with_suffix(".json.tmp")

    with temp.open("w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    temp.replace(OUTPUT_FILE)

    print("RECURSIVE RULE EXTRACTION")
    print("-" * 45)
    print(f"Records processed:       {processed}")
    print(f"Communities with rules:  {communities_with_rules}")
    print(f"Communities without rules: {processed - communities_with_rules}")
    print(f"Main rules extracted:    {total_main_rules}")
    print(f"Subrules extracted:      {total_subrules}")
    print(f"Output: {OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    main()
