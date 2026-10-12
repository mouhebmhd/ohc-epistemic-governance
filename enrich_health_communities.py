
import csv
import json
from pathlib import Path

# Input files
COMMUNITIES_FILE = Path("data/health_communities.csv")
METADATA_FILE = Path("data/reddit_health_communities_metadata.json")
GUIDELINES_FILE = Path("data/reddit_health_communities_guidelines.json")

# Output file
OUTPUT_FILE = Path("data/healthRedditCommunities_enriched.csv")

VALID_LANGUAGES = {"en", "es", "fr", "hi", "ar"}
VALID_COMMUNITY_TYPES = {
    "dedicated_health", "general", "professional"
}
VALID_DISEASE_CATEGORIES = {
    "chronic", "mental_health", "infectious", "surgical", "general"
}
VALID_SAMPLE_GROUPS = {
    "english_core", "multilingual", "governance_vacuum"
}

NEW_FIELDS = [
    "language",
    "community_type",
    "disease_category",
    "sample_group",
    "has_rules",
]

# Add manual classifications here when automatic inference is ambiguous.
# Keys should be subreddit names in lowercase, without "r/".
OVERRIDES = {
    # "askdocs": {
    #     "language": "en",
    #     "community_type": "professional",
    #     "disease_category": "general",
    #     "sample_group": "english_core",
    # },
}


def normalize_name(value):
    """Normalize subreddit names for matching."""
    if not value:
        return ""

    return str(value).strip().lower().removeprefix("r/")


def load_json_records(path):
    """Load a JSON list; return an empty list if the file is absent."""
    if not path.exists():
        print(f"Warning: file not found: {path}")
        return []

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, list):
        return data

    raise ValueError(f"Expected a JSON list in {path}")


def get_metadata_data(record):
    """Handle the nested metadata structure used by the collector."""
    metadata = record.get("metadata") or {}
    data = metadata.get("data") or {}

    return data if isinstance(data, dict) else {}


def build_lookup(records, name_fields):
    """Index records by subreddit name."""
    lookup = {}

    for record in records:
        if not isinstance(record, dict):
            continue

        name = None

        for field in name_fields:
            if record.get(field):
                name = record[field]
                break

        data = get_metadata_data(record)

        if not name:
            name = data.get("display_name")

        normalized = normalize_name(name)

        if normalized:
            lookup[normalized] = record

    return lookup


def infer_language(record, metadata):
    """Infer language from known metadata fields."""
    data = get_metadata_data(metadata) if metadata else {}

    candidates = [
        record.get("language"),
        record.get("lang"),
        data.get("lang"),
        data.get("language"),
    ]

    for candidate in candidates:
        if not candidate:
            continue

        language = str(candidate).strip().lower()

        aliases = {
            "english": "en",
            "spanish": "es",
            "french": "fr",
            "hindi": "hi",
            "arabic": "ar",
        }

        language = aliases.get(language, language)

        if language in VALID_LANGUAGES:
            return language

    # Do not infer a language from the subreddit name alone.
    return "mutlilingual"


def infer_community_type(name, title, description):
    """Conservative heuristic; use overrides for ambiguous cases."""
    text = f"{name} {title} {description}".lower()

    professional_terms = [
        "askdocs", "askdoctor", "medical professionals",
        "physician", "nursing", "nurses", "doctors",
        "medicalschool", "medicine",
    ]

    if any(term in text for term in professional_terms):
        return "professional"

    health_terms = [
        "health", "medical", "medicine", "disease", "illness",
        "patient", "symptom", "diagnosis", "mental health",
        "diabetes", "cancer", "asthma", "migraine",
        "depression", "anxiety", "surgery", "surgical",
        "covid", "vaccine", "infection",
    ]

    if any(term in text for term in health_terms):
        return "dedicated_health"

    return "general"


def infer_disease_category(name, title, description):
    """Infer a broad topic category from community text."""
    text = f"{name} {title} {description}".lower()

    categories = {
        "mental_health": [
            "mental health", "mentalhealth", "depression",
            "anxiety", "bipolar", "schizophrenia", "ptsd",
            "ocd", "adhd", "psychology", "psychiatry",
            "suicide", "selfharm", "eatingdisorder",
        ],
        "infectious": [
            "infectious", "infection", "covid", "coronavirus",
            "vaccine", "vaccination", "hiv", "aids",
            "tuberculosis", "malaria", "flu", "influenza",
            "sti", "std",
        ],
        "surgical": [
            "surgery", "surgical", "postop", "preop",
            "transplant", "orthopedic surgery",
        ],
        "chronic": [
            "chronic", "diabetes", "cancer", "arthritis",
            "fibromyalgia", "migraine", "asthma", "copd",
            "multiple sclerosis", "epilepsy", "heart disease",
            "kidney disease", "crohns", "ulcerative colitis",
        ],
    }

    for category in (
        "mental_health", "infectious", "surgical", "chronic"
    ):
        if any(term in text for term in categories[category]):
            return category

    return "general"


def infer_sample_group(language, has_rules):
    """
    Default operational rule:
    - English communities belong to english_core.
    - Other supported languages belong to multilingual.
    - Communities without extracted rules belong to governance_vacuum.

    Change the precedence if your research protocol defines groups
    differently. 'No extracted rules' does not prove that rules do
    not exist.
    """
    if not has_rules:
        return "governance_vacuum"

    if language == "en":
        return "english_core"

    if language in VALID_LANGUAGES:
        return "multilingual"

    return ""


def get_community_description(record, metadata):
    """Collect text useful for classification."""
    data = get_metadata_data(metadata) if metadata else {}

    title = (
        record.get("title")
        or record.get("display_name")
        or data.get("title")
        or ""
    )

    description = (
        record.get("description")
        or record.get("public_description")
        or data.get("public_description")
        or data.get("description")
        or ""
    )

    return str(title), str(description)


def main():
    with COMMUNITIES_FILE.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise ValueError("The communities CSV has no header.")

        original_fields = reader.fieldnames
        communities = list(reader)

    metadata_records = load_json_records(METADATA_FILE)
    guideline_records = load_json_records(GUIDELINES_FILE)

    metadata_lookup = build_lookup(
        metadata_records,
        ["subreddit_name", "display_name", "name"],
    )

    guideline_lookup = build_lookup(
        guideline_records,
        ["subreddit_name", "display_name", "name"],
    )

    # Preserve all original columns and append missing new fields.
    output_fields = list(original_fields)

    for field in NEW_FIELDS:
        if field not in output_fields:
            output_fields.append(field)

    for community in communities:
        name = normalize_name(
            community.get("subreddit_name")
            or community.get("subreddit")
            or community.get("name")
            or community.get("community")
        )

        metadata = metadata_lookup.get(name, {})
        guideline = guideline_lookup.get(name, {})

        title, description = get_community_description(
            community, metadata
        )

        # Determine whether rules were actually extracted.
        rules = (
            guideline.get("rules")
            or guideline.get("wiki_rules")
            or []
        )

        has_rules = bool(
            isinstance(rules, list)
            and any(
                isinstance(rule, dict)
                and (
                    rule.get("title")
                    or rule.get("description")
                    or rule.get("text")
                )
                for rule in rules
            )
        )

        language = infer_language(community, metadata)

        community_type = infer_community_type(
            name, title, description
        )

        disease_category = infer_disease_category(
            name, title, description
        )

        sample_group = infer_sample_group(language, has_rules)

        values = {
            "language": language,
            "community_type": community_type,
            "disease_category": disease_category,
            "sample_group": sample_group,
            "has_rules": str(has_rules).lower(),
        }

        # Apply manual classifications last.
        if name in OVERRIDES:
            values.update(OVERRIDES[name])

        # Validate controlled vocabularies.
        if values["language"] not in VALID_LANGUAGES:
            values["language"] = ""

        if values["community_type"] not in VALID_COMMUNITY_TYPES:
            values["community_type"] = ""

        if values["disease_category"] not in VALID_DISEASE_CATEGORIES:
            values["disease_category"] = "general"

        if values["sample_group"] not in VALID_SAMPLE_GROUPS:
            values["sample_group"] = ""

        values["has_rules"] = str(
            values["has_rules"]
        ).strip().lower()

        if values["has_rules"] not in {"true", "false"}:
            values["has_rules"] = str(has_rules).lower()

        community.update(values)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=output_fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(communities)

    print("COMMUNITY FILE ENRICHMENT")
    print("-" * 45)
    print(f"Communities processed: {len(communities)}")
    print(f"Output: {OUTPUT_FILE.resolve()}")

    for field in NEW_FIELDS:
        counts = {}

        for community in communities:
            value = community.get(field, "")
            counts[value] = counts.get(value, 0) + 1

        print(f"\n{field}:")
        for value, count in sorted(counts.items()):
            print(f"  {value or '[missing]'}: {count}")


if __name__ == "__main__":
    main()
