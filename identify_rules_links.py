
import json
import re
import html
from pathlib import Path
from urllib.parse import urljoin

INPUT_FILE = Path("data/reddit_health_communities_metadata.json")
OUTPUT_FILE = Path("data/reddit_communities_rules_urls.json")

RULES_URL = re.compile(
    r'https?://(?:www\.|old\.)?reddit\.com/r/[^/\s"<>]+/about/rules/?'
    r'|/r/[^/\s"<>]+/about/rules/?',
    re.IGNORECASE,
)


def decode_text(value):
    # Decode HTML entities repeatedly, including escaped markup.
    for _ in range(5):
        decoded = html.unescape(value)
        if decoded == value:
            break
        value = decoded
    return value


def main():
    with INPUT_FILE.open("r", encoding="utf-8") as f:
        communities = json.load(f)

    results = []
    with_url = 0

    for record in communities:
        data = record.get("metadata", {}).get("data", {})

        # Inspect description fields and posting instructions.
        sources = {
            key: data.get(key, "")
            for key in (
                "description",
                "description_html",
                "submit_text",
                "submit_text_html",
                "public_description",
                "public_description_html",
            )
        }

        found = set()

        for value in sources.values():
            if not isinstance(value, str):
                continue

            decoded = decode_text(value)

            for match in RULES_URL.finditer(decoded):
                url = urljoin(
                    "https://www.reddit.com",
                    match.group(0).replace("\\/", "/"),
                )
                found.add(url.rstrip("/") + "/")

        urls = sorted(found)

        results.append({
            "subreddit_name": record.get("subreddit_name"),
            "language": record.get("language"),
            "rules_urls": urls,
            "rules_url_found": bool(urls),
            "retrieval_status": (
                "rules_url_found" if urls
                else "no_rules_url_found_in_metadata"
            ),
        })

        if urls:
            with_url += 1

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Communities inspected: {len(results)}")
    print(f"Communities with rules URLs: {with_url}")
    print(f"No rules URL found in metadata: {len(results) - with_url}")
    print(f"Saved to: {OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    main()
