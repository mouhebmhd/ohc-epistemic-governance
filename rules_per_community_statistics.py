
import json
import csv
import statistics
from collections import Counter
from pathlib import Path

INPUT_FILE = Path("data/reddit_health_communities_guidelines.json")
OUTPUT_DIR = Path("data/rule_statistics")


def get_rule_text(rule, field):
    value = rule.get(field, "")
    return value.strip() if isinstance(value, str) else ""


def main():
    with INPUT_FILE.open("r", encoding="utf-8") as file:
        dataset = json.load(file)

    if not isinstance(dataset, list):
        raise ValueError("Expected a JSON list of communities.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    community_stats = []
    all_rules = []

    rules_source_counts = Counter()
    rule_counts = []
    communities_with_rules = 0
    communities_without_rules = 0
    total_subrules = 0
    communities_with_subrules = 0
    empty_titles = 0
    empty_descriptions = 0
    empty_texts = 0
    missing_source_urls = 0

    for record in dataset:
        if not isinstance(record, dict):
            continue

        name = (
            record.get("subreddit_name")
            or record.get("display_name")
            or "unknown"
        )

        # Support both the earlier metadata structure and the
        # output structure of the wiki extraction script.
        rules = record.get("rules") or record.get("wiki_rules") or []

        if not isinstance(rules, list):
            rules = []

        subrule_count = sum(
            len(rule.get("subrules", []))
            for rule in rules
            if isinstance(rule, dict)
            and isinstance(rule.get("subrules", []), list)
        )

        rule_count = len(rules)
        rule_counts.append(rule_count)

        if rule_count:
            communities_with_rules += 1
        else:
            communities_without_rules += 1

        if subrule_count:
            communities_with_subrules += 1

        total_subrules += subrule_count

        title_lengths = []
        description_lengths = []
        text_lengths = []
        seen = set()
        duplicate_count = 0

        for rule in rules:
            if not isinstance(rule, dict):
                continue

            title = get_rule_text(rule, "title")
            description = get_rule_text(rule, "description")
            text = get_rule_text(rule, "text")

            title_lengths.append(len(title))
            description_lengths.append(len(description))
            text_lengths.append(len(text))

            if not title:
                empty_titles += 1

            if not description:
                empty_descriptions += 1

            if not text:
                empty_texts += 1

            source = rule.get("source", "unknown")
            rules_source_counts[source] += 1

            if not rule.get("source_url"):
                missing_source_urls += 1

            # Detect duplicates within each community using normalized
            # title and description.
            key = (title.casefold(), description.casefold())

            if key in seen:
                duplicate_count += 1
            else:
                seen.add(key)

            all_rules.append({
                "subreddit_name": name,
                "number": rule.get("number", ""),
                "title": title,
                "description": description,
                "text": text,
                "source": source,
                "source_url": rule.get("source_url", ""),
                "subrules_count": len(rule.get("subrules", []))
                if isinstance(rule.get("subrules", []), list)
                else 0,
            })

        community_stats.append({
            "subreddit_name": name,
            "subreddit_url": record.get("subreddit_url", ""),
            "rules_count": rule_count,
            "subrules_count": subrule_count,
            "average_title_characters": (
                round(statistics.mean(title_lengths), 2)
                if title_lengths else 0
            ),
            "average_description_characters": (
                round(statistics.mean(description_lengths), 2)
                if description_lengths else 0
            ),
            "average_rule_text_characters": (
                round(statistics.mean(text_lengths), 2)
                if text_lengths else 0
            ),
            "duplicate_rules_count": duplicate_count,
        })

    valid_communities = len(community_stats)

    def describe(values):
        if not values:
            return {
                "mean": 0,
                "median": 0,
                "min": 0,
                "max": 0,
                "stdev": 0,
            }

        return {
            "mean": round(statistics.mean(values), 2),
            "median": round(statistics.median(values), 2),
            "min": min(values),
            "max": max(values),
            "stdev": round(statistics.pstdev(values), 2),
        }

    distribution = describe(rule_counts)

    report = {
        "dataset": {
            "input_file": str(INPUT_FILE),
            "communities_processed": valid_communities,
        },
        "coverage": {
            "communities_with_rules": communities_with_rules,
            "communities_without_rules": communities_without_rules,
            "percentage_with_rules": round(
                communities_with_rules / valid_communities * 100, 2
            ) if valid_communities else 0,
            "percentage_without_rules": round(
                communities_without_rules / valid_communities * 100, 2
            ) if valid_communities else 0,
        },
        "rule_distribution_per_community": distribution,
        "totals": {
            "total_rules": len(all_rules),
            "total_subrules": total_subrules,
            "communities_with_subrules": communities_with_subrules,
            "average_rules_per_community_with_rules": round(
                len(all_rules) / communities_with_rules, 2
            ) if communities_with_rules else 0,
        },
        "data_quality": {
            "rules_without_title": empty_titles,
            "rules_without_description": empty_descriptions,
            "rules_without_text": empty_texts,
            "rules_without_source_url": missing_source_urls,
            "duplicate_rules_within_community": sum(
                row["duplicate_rules_count"]
                for row in community_stats
            ),
        },
        "rules_by_source": dict(rules_source_counts),
        "top_20_communities_by_rule_count": sorted(
            community_stats,
            key=lambda row: row["rules_count"],
            reverse=True,
        )[:20],
    }

    # Save the complete statistics report.
    report_path = OUTPUT_DIR / "rules_summary.json"

    with report_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    # Save per-community statistics.
    community_csv = OUTPUT_DIR / "rules_per_community.csv"

    with community_csv.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(community_stats[0].keys())
            if community_stats else [
                "subreddit_name", "subreddit_url", "rules_count",
                "subrules_count", "average_title_characters",
                "average_description_characters",
                "average_rule_text_characters",
                "duplicate_rules_count",
            ],
        )
        writer.writeheader()
        writer.writerows(community_stats)

    # Save one row per rule for subsequent content analysis.
    rules_csv = OUTPUT_DIR / "all_extracted_rules.csv"

    with rules_csv.open("w", encoding="utf-8-sig", newline="") as file:
        fields = [
            "subreddit_name", "number", "title", "description",
            "text", "source", "source_url", "subrules_count",
        ]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rules)

    # Print the key results.
    print("=" * 55)
    print("REDDIT COMMUNITY RULES STATISTICS")
    print("=" * 55)
    print(f"Communities processed:          {valid_communities}")
    print(f"Communities with rules:         {communities_with_rules}")
    print(f"Communities without rules:      {communities_without_rules}")
    print(f"Coverage (%):                   {report['coverage']['percentage_with_rules']}")
    print(f"Total rules:                    {len(all_rules)}")
    print(f"Total subrules:                 {total_subrules}")
    print(f"Rules per community — mean:     {distribution['mean']}")
    print(f"Rules per community — median:   {distribution['median']}")
    print(f"Rules per community — maximum:  {distribution['max']}")
    print(f"Duplicate rules:                {report['data_quality']['duplicate_rules_within_community']}")
    print()
    print("Top 10 communities by rule count:")

    for index, row in enumerate(
        report["top_20_communities_by_rule_count"][:10],
        start=1,
    ):
        print(f"{index:2}. r/{row['subreddit_name']}: {row['rules_count']} rules")

    print()
    print(f"Summary JSON:       {report_path}")
    print(f"Community CSV:      {community_csv}")
    print(f"All rules CSV:      {rules_csv}")


if __name__ == "__main__":
    main()
