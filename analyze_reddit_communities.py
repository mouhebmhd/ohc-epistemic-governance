
import json
import re
from pathlib import Path
from collections import Counter

import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# CONFIGURATION
# ============================================================

INPUT_FILE = Path("reddit_health_communities.json")
OUTPUT_DIR = Path("reddit_analysis_report")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 1. LOAD DATA
# ============================================================

def load_json(path):
    """Load a JSON list, a single community object, or a wrapper object."""
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        communities = data
    elif isinstance(data, dict):
        # Support common wrappers containing the community list.
        communities = None
        for key in ("communities", "data", "results", "items"):
            if isinstance(data.get(key), list):
                communities = data[key]
                break

        if communities is None:
            communities = [data]
    else:
        raise ValueError("The JSON root must be a list or an object.")

    if not all(isinstance(c, dict) for c in communities):
        raise ValueError("Every community entry must be a JSON object.")

    return communities


communities = load_json(INPUT_FILE)

print("=" * 65)
print("REDDIT HEALTH COMMUNITIES — EXPLORATORY ANALYSIS")
print("=" * 65)
print(f"Input file: {INPUT_FILE}")
print(f"Communities loaded: {len(communities):,}")


# ============================================================
# 2. FLATTEN COMMUNITY-LEVEL DATA
# ============================================================

community_rows = []
rule_rows = []

for index, community in enumerate(communities):
    language = str(community.get("language") or "Unknown").strip()
    subreddit = str(community.get("subreddit") or "").strip()
    rules = community.get("rules", [])

    if not isinstance(rules, list):
        rules = []

    # Exclude no rules from the dataset, but record the issue.
    valid_rules = [r for r in rules if isinstance(r, dict)]

    titles = [
        str(r.get("title") or "").strip()
        for r in valid_rules
    ]

    descriptions = [
        str(r.get("description") or "").strip()
        for r in valid_rules
    ]

    rule_texts = [
        (title + " " + description).strip()
        for title, description in zip(titles, descriptions)
    ]

    # Exact duplicates within a community, ignoring case and spacing.
    normalized_texts = [
        re.sub(r"\s+", " ", text.lower()).strip()
        for text in rule_texts
        if text
    ]

    duplicate_count = (
        len(normalized_texts) - len(set(normalized_texts))
    )

    empty_titles = sum(not title for title in titles)
    empty_descriptions = sum(not desc for desc in descriptions)

    total_links = sum(
        len(r.get("links", []))
        for r in valid_rules
        if isinstance(r.get("links", []), list)
    )

    # Store the community-level record.
    community_rows.append({
        "community_index": index,
        "language": language,
        "subreddit": subreddit,
        "subreddit_url": community.get("subreddit_url", ""),
        "focus": community.get("focus", ""),
        "community_type": community.get("community_type", ""),
        "rules_url": community.get("rules_url", ""),
        "intro": community.get("intro", ""),
        "rules_source": community.get("rules_source", ""),
        "status": community.get("status", ""),
        "fetch_notes": " | ".join(
            str(x) for x in (community.get("fetch_notes") or [])
        ),
        "n_rules": len(valid_rules),
        "n_invalid_rule_objects": len(rules) - len(valid_rules),
        "n_empty_titles": empty_titles,
        "n_empty_descriptions": empty_descriptions,
        "n_duplicate_rules": duplicate_count,
        "n_links": total_links,
        "n_rules_with_links": sum(
            bool(r.get("links"))
            for r in valid_rules
        ),
        "n_unique_rule_texts": len(set(normalized_texts)),
        "has_rules": bool(valid_rules),
    })

    # Store one row per rule.
    for rule_index, rule in enumerate(valid_rules):
        title = str(rule.get("title") or "").strip()
        description = str(rule.get("description") or "").strip()
        links = rule.get("links", [])

        if not isinstance(links, list):
            links = []

        # Flag possible page-navigation/footer contamination.
        noise_pattern = re.compile(
            r"installed apps|privacy policy|cookie preference|"
            r"reddit, inc\.|user agreement|popular\s*-\s*news",
            re.IGNORECASE,
        )

        combined_text = f"{title} {description}"

        rule_rows.append({
            "community_index": index,
            "language": language,
            "subreddit": subreddit,
            "rule_index": rule_index,
            "number": rule.get("number"),
            "title": title,
            "description": description,
            "text": combined_text.strip(),
            "title_length_chars": len(title),
            "description_length_chars": len(description),
            "text_length_chars": len(combined_text.strip()),
            "n_links": len(links),
            "link_texts": " | ".join(
                str(link.get("text", ""))
                for link in links
                if isinstance(link, dict)
            ),
            "link_urls": " | ".join(
                str(link.get("url", ""))
                for link in links
                if isinstance(link, dict)
            ),
            "has_title": bool(title),
            "has_description": bool(description),
            "has_links": bool(links),
            "possible_navigation_noise": bool(
                noise_pattern.search(combined_text)
            ),
            "is_empty_rule": not bool(combined_text.strip()),
        })


communities_df = pd.DataFrame(community_rows)
rules_df = pd.DataFrame(rule_rows)

# Use explicit columns so empty datasets still export cleanly.
if communities_df.empty:
    communities_df = pd.DataFrame(columns=[
        "community_index", "language", "subreddit",
        "n_rules", "status"
    ])

if rules_df.empty:
    rules_df = pd.DataFrame(columns=[
        "community_index", "language", "subreddit",
        "rule_index", "number", "title", "description", "text"
    ])


# ============================================================
# 3. LANGUAGE-LEVEL SUMMARY
# ============================================================

if not communities_df.empty:
    language_summary = (
        communities_df.groupby("language", dropna=False)
        .agg(
            n_communities=("community_index", "count"),
            n_rules=("n_rules", "sum"),
            mean_rules_per_community=("n_rules", "mean"),
            median_rules_per_community=("n_rules", "median"),
            min_rules=("n_rules", "min"),
            max_rules=("n_rules", "max"),
            communities_without_rules=(
                "has_rules", lambda s: (~s).sum()
            ),
            communities_with_duplicates=(
                "n_duplicate_rules", lambda s: (s > 0).sum()
            ),
            empty_descriptions=("n_empty_descriptions", "sum"),
            duplicate_rules=("n_duplicate_rules", "sum"),
            total_links=("n_links", "sum"),
        )
        .reset_index()
        .sort_values("n_communities", ascending=False)
    )
else:
    language_summary = pd.DataFrame()

if not communities_df.empty:
    status_summary = (
        communities_df.groupby(
            ["language", "status"], dropna=False
        )
        .size()
        .reset_index(name="n_communities")
        .sort_values("n_communities", ascending=False)
    )
else:
    status_summary = pd.DataFrame()


# ============================================================
# 4. RULE-LEVEL SUMMARY
# ============================================================

if not rules_df.empty:
    rules_by_language = (
        rules_df.groupby("language", dropna=False)
        .agg(
            n_rules=("rule_index", "count"),
            mean_title_length=("title_length_chars", "mean"),
            mean_description_length=(
                "description_length_chars", "mean"
            ),
            empty_titles=("has_title", lambda s: (~s).sum()),
            empty_descriptions=(
                "has_description", lambda s: (~s).sum()
            ),
            rules_with_links=("has_links", "sum"),
            possible_navigation_noise=(
                "possible_navigation_noise", "sum"
            ),
            empty_rules=("is_empty_rule", "sum"),
        )
        .reset_index()
        .sort_values("n_rules", ascending=False)
    )

    rules_by_community = (
        rules_df.groupby(
            ["language", "subreddit"], dropna=False
        )
        .agg(
            n_rules=("rule_index", "count"),
            mean_title_length=("title_length_chars", "mean"),
            mean_description_length=(
                "description_length_chars", "mean"
            ),
            n_rules_with_links=("has_links", "sum"),
            n_possible_noise=(
                "possible_navigation_noise", "sum"
            ),
        )
        .reset_index()
        .sort_values("n_rules", ascending=False)
    )
else:
    rules_by_language = pd.DataFrame()
    rules_by_community = pd.DataFrame()


# ============================================================
# 5. DATA QUALITY AND DUPLICATE REPORTS
# ============================================================

if not communities_df.empty:
    duplicate_communities = communities_df[
        communities_df["subreddit"].str.lower().duplicated(
            keep=False
        )
        & communities_df["subreddit"].ne("")
    ].sort_values(["subreddit", "language"])

    communities_with_issues = communities_df[
        (communities_df["n_rules"] == 0)
        | (communities_df["n_duplicate_rules"] > 0)
        | (communities_df["n_empty_titles"] > 0)
        | (communities_df["n_empty_descriptions"] > 0)
        | (communities_df["n_invalid_rule_objects"] > 0)
    ].copy()
else:
    duplicate_communities = pd.DataFrame()
    communities_with_issues = pd.DataFrame()

# Duplicate rules across communities are not necessarily errors.
# This report helps identify repeated generic rules.
if not rules_df.empty:
    rule_duplicates = rules_df.copy()
    rule_duplicates["normalized_text"] = (
        rule_duplicates["text"]
        .str.lower()
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    repeated_rules = (
        rule_duplicates[
            rule_duplicates["normalized_text"].ne("")
        ]
        .groupby("normalized_text")
        .agg(
            occurrences=("subreddit", "size"),
            communities=(
                "subreddit",
                lambda s: " | ".join(sorted(set(s.dropna()))),
            ),
            languages=(
                "language",
                lambda s: " | ".join(sorted(set(s.dropna()))),
            ),
            example_title=("title", "first"),
            example_description=("description", "first"),
        )
        .reset_index()
        .query("occurrences > 1")
        .sort_values("occurrences", ascending=False)
    )
else:
    repeated_rules = pd.DataFrame()


# ============================================================
# 6. EXPORT TABLES
# ============================================================

exports = {
    "community_level.csv": communities_df,
    "rule_level.csv": rules_df,
    "language_summary.csv": language_summary,
    "status_by_language.csv": status_summary,
    "rules_by_language.csv": rules_by_language,
    "rules_by_community.csv": rules_by_community,
    "duplicate_communities.csv": duplicate_communities,
    "communities_with_issues.csv": communities_with_issues,
    "repeated_rules.csv": repeated_rules,
}

for filename, dataframe in exports.items():
    dataframe.to_csv(
        OUTPUT_DIR / filename,
        index=False,
        encoding="utf-8-sig",
    )


# ============================================================
# 7. VISUALIZATIONS
# ============================================================

def save_plot(filename):
    plt.tight_layout()
    plt.savefig(
        OUTPUT_DIR / filename,
        dpi=200,
        bbox_inches="tight",
    )
    plt.close()


# A. Number of communities per language
if not language_summary.empty:
    plt.figure(figsize=(10, 6))
    plt.bar(
        language_summary["language"].astype(str),
        language_summary["n_communities"],
    )
    plt.title("Number of Reddit Communities per Language")
    plt.xlabel("Language")
    plt.ylabel("Number of communities")
    plt.xticks(rotation=45, ha="right")
    save_plot("01_communities_per_language.png")


# B. Number of rules per language
if not rules_by_language.empty:
    plt.figure(figsize=(10, 6))
    plt.bar(
        rules_by_language["language"].astype(str),
        rules_by_language["n_rules"],
    )
    plt.title("Number of Extracted Rules per Language")
    plt.xlabel("Language")
    plt.ylabel("Number of rules")
    plt.xticks(rotation=45, ha="right")
    save_plot("02_rules_per_language.png")


# C. Distribution of rule counts across communities
if not communities_df.empty:
    plt.figure(figsize=(10, 6))
    plt.hist(
        communities_df["n_rules"],
        bins=30,
        edgecolor="black",
    )
    plt.title("Distribution of Rule Counts per Community")
    plt.xlabel("Number of rules")
    plt.ylabel("Number of communities")
    save_plot("03_rule_count_distribution.png")


# D. Mean rules per community by language
if not language_summary.empty:
    summary = language_summary.sort_values(
        "mean_rules_per_community", ascending=True
    )
    plt.figure(figsize=(10, max(5, len(summary) * 0.45)))
    plt.barh(
        summary["language"].astype(str),
        summary["mean_rules_per_community"],
    )
    plt.title("Mean Number of Rules per Community by Language")
    plt.xlabel("Mean number of rules")
    plt.ylabel("Language")
    save_plot("04_mean_rules_per_community.png")


# E. Community-level rules overview
if not communities_df.empty:
    plot_df = communities_df.sort_values(
        "n_rules", ascending=False
    ).head(30).copy()

    labels = (
        plot_df["language"].astype(str)
        + " / r/"
        + plot_df["subreddit"].astype(str)
    )

    plt.figure(figsize=(12, max(6, len(plot_df) * 0.3)))
    plt.barh(labels.iloc[::-1], plot_df["n_rules"].iloc[::-1])
    plt.title("Top 30 Communities by Number of Extracted Rules")
    plt.xlabel("Number of rules")
    plt.ylabel("Community")
    save_plot("05_top_30_communities.png")


# F. Empty descriptions by language
if not rules_by_language.empty:
    plt.figure(figsize=(10, 6))
    plt.bar(
        rules_by_language["language"].astype(str),
        rules_by_language["empty_descriptions"],
    )
    plt.title("Rules with Empty Descriptions by Language")
    plt.xlabel("Language")
    plt.ylabel("Rules with empty descriptions")
    plt.xticks(rotation=45, ha="right")
    save_plot("06_empty_descriptions_by_language.png")


# G. Rules flagged as possible navigation noise
if not rules_by_language.empty:
    plt.figure(figsize=(10, 6))
    plt.bar(
        rules_by_language["language"].astype(str),
        rules_by_language["possible_navigation_noise"],
    )
    plt.title("Potential Navigation/Footer Noise by Language")
    plt.xlabel("Language")
    plt.ylabel("Flagged rules")
    plt.xticks(rotation=45, ha="right")
    save_plot("07_possible_noise_by_language.png")


# H. Status distribution
if not status_summary.empty:
    pivot = status_summary.pivot_table(
        index="language",
        columns="status",
        values="n_communities",
        aggfunc="sum",
        fill_value=0,
    )

    ax = pivot.plot(
        kind="bar",
        stacked=True,
        figsize=(11, 6),
    )
    ax.set_title("Community Extraction Status by Language")
    ax.set_xlabel("Language")
    ax.set_ylabel("Number of communities")
    plt.xticks(rotation=45, ha="right")
    save_plot("08_status_by_language.png")


# ============================================================
# 8. GENERATE A MARKDOWN REPORT
# ============================================================

n_communities = len(communities_df)
n_rules = len(rules_df)

n_languages = (
    communities_df["language"].nunique()
    if not communities_df.empty else 0
)

n_missing_subreddit = (
    communities_df["subreddit"].eq("").sum()
    if not communities_df.empty else 0
)

n_missing_language = (
    communities_df["language"].eq("Unknown").sum()
    if not communities_df.empty else 0
)

n_empty_descriptions = (
    rules_df["has_description"].eq(False).sum()
    if not rules_df.empty else 0
)

n_empty_titles = (
    rules_df["has_title"].eq(False).sum()
    if not rules_df.empty else 0
)

n_noise = (
    rules_df["possible_navigation_noise"].sum()
    if not rules_df.empty else 0
)

n_communities_no_rules = (
    communities_df["has_rules"].eq(False).sum()
    if not communities_df.empty else 0
)

report = [
    "# Reddit Health Communities: Exploratory Report",
    "",
    f"- Input file: `{INPUT_FILE}`",
    f"- Communities: **{n_communities:,}**",
    f"- Languages: **{n_languages:,}**",
    f"- Extracted rule objects: **{n_rules:,}**",
    "",
    "## 1. Dataset-level summary",
    "",
    f"- Communities missing a subreddit name: {n_missing_subreddit}",
    f"- Communities with unknown language: {n_missing_language}",
    f"- Communities with no valid rules: {n_communities_no_rules}",
    f"- Rules with empty titles: {n_empty_titles}",
    f"- Rules with empty descriptions: {n_empty_descriptions}",
    f"- Rules flagged for possible navigation/footer noise: {n_noise}",
    "",
    "## 2. Language-level summary",
    "",
    language_summary.to_markdown(index=False)
    if not language_summary.empty else "No language summary available.",
    "",
    "## 3. Extraction status",
    "",
    status_summary.to_markdown(index=False)
    if not status_summary.empty else "No status data available.",
    "",
    "## 4. Data-quality notes",
    "",
    f"- Communities with potential data issues: {len(communities_with_issues)}",
    f"- Duplicate subreddit-name records: {len(duplicate_communities)}",
    f"- Repeated rule-text groups: {len(repeated_rules)}",
    "",
    "## 5. Interpretation cautions",
    "",
    "- An extracted rule is not necessarily a genuine moderation rule.",
    "- Empty descriptions may be legitimate, for example, title-only rules.",
    "- Repeated rules can reflect common moderation practices rather than errors.",
    "- Navigation/footer flags are heuristics and require manual validation.",
    "- Community counts and rule counts should be interpreted alongside extraction status.",
    "",
    "## 6. Generated visualizations",
    "",
]

for image_name in sorted(p.name for p in OUTPUT_DIR.glob("*.png")):
    report.append(f"- `{image_name}`")

(OUTPUT_DIR / "report.md").write_text(
    "\n".join(report),
    encoding="utf-8",
)

# Also print the key summary to the terminal.
print("\nLANGUAGE SUMMARY")
print("-" * 65)
if not language_summary.empty:
    print(language_summary.to_string(index=False))
else:
    print("No communities found.")

print("\nDATA QUALITY")
print("-" * 65)
print(f"Communities with no valid rules: {n_communities_no_rules}")
print(f"Rules with empty titles: {n_empty_titles}")
print(f"Rules with empty descriptions: {n_empty_descriptions}")
print(f"Possible navigation/footer noise: {n_noise}")

print(f"\nAnalysis complete. Results saved to: {OUTPUT_DIR.resolve()}")
