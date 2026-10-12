import json
import html
import requests
from pathlib import Path
from bs4 import BeautifulSoup

INPUT_FILE = Path("data/reddit_health_communities_metadata.json")
OUTPUT_FILE = Path("data/reddit_health_communities_guidelines.json")

HEADERS = {
    "User-Agent": "HealthCommunityGuidelinesResearch/1.0"
}


def get_wiki_rules(subreddit_name):
    """Fetch and parse a subreddit's rules wiki page."""
    if not subreddit_name:
        return []

    url = (
        f"https://www.reddit.com/r/{subreddit_name}"
        "/wiki/index/rules/"
    )

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract the main page content when available.
        main = (
            soup.find("shreddit-subreddit-wiki")
            or soup.find("main")
            or soup.find("article")
            or soup.body
        )

        if main is None:
            return []

        rules = []
        current_rule = None

        for element in main.find_all(
            ["h1", "h2", "h3", "h4", "h5", "h6",
             "p", "li", "blockquote"]
        ):
            text = html.unescape(
                element.get_text(" ", strip=True)
            ).strip()

            if not text:
                continue

            if element.name in {
                "h1", "h2", "h3", "h4", "h5", "h6"
            }:
                if current_rule:
                    rules.append(current_rule)

                current_rule = {
                    "number": len(rules) + 1,
                    "title": text,
                    "description": "",
                    "text": text,
                    "subrules": [],
                    "source": "reddit_wiki",
                    "source_url": url,
                }

            elif current_rule:
                current_rule["description"] += (
                    ("\n" if current_rule["description"] else "")
                    + text
                )
                current_rule["text"] = (
                    current_rule["title"]
                    + "\n\n"
                    + current_rule["description"]
                )

        if current_rule:
            rules.append(current_rule)

        return rules

    except requests.RequestException as error:
        print(f"Could not fetch {subreddit_name}: {error}")
        return []


def main():
    with INPUT_FILE.open("r", encoding="utf-8") as file:
        dataset = json.load(file)

    for record in dataset:
        if not isinstance(record, dict):
            continue

        name = record.get("subreddit_name")

        if not name:
            metadata = record.get("metadata") or {}
            data = metadata.get("data") or {}
            name = data.get("display_name")

        record["wiki_rules"] = get_wiki_rules(name)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(dataset, file, ensure_ascii=False, indent=2)

    print(f"Saved results to {OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    main()