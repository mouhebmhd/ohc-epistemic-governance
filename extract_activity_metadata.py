
import json
import math
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

CSV_FILE = Path("data/health_communities.csv")
METADATA_FILE = Path("data/reddit_health_communities_metadata.json")
GUIDELINES_FILE = Path("data/reddit_health_communities_guidelines.json")

# Reference date for age calculations.
# Set this to the actual collection timestamp if known.
RETRIEVED_ON = datetime.now(timezone.utc).timestamp()


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_name(name):
    return str(name).strip().removeprefix("r/").lower()


def index_records(data, name_field="subreddit_name"):
    """Index records by normalized subreddit name."""
    if isinstance(data, dict):
        for key in ("communities", "subreddits", "records"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            if name_field in data:
                data = [data]
            else:
                return {
                    normalize_name(key): value
                    for key, value in data.items()
                    if isinstance(value, dict)
                }

    if isinstance(data, list):
        indexed = {}
        for record in data:
            if isinstance(record, dict) and record.get(name_field):
                indexed[normalize_name(record[name_field])] = record
        return indexed

    return {}


def to_bool_or_null(value):
    """Convert known Boolean representations while preserving unknowns."""
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)) and not pd.isna(value):
        if value == 1:
            return True
        if value == 0:
            return False

    if isinstance(value, str):
        value = value.strip().lower()
        if value in {"true", "1", "yes"}:
            return True
        if value in {"false", "0", "no"}:
            return False

    return None


def get_meta(record):
    """Extract fields from Reddit's nested metadata structure."""
    if not isinstance(record, dict):
        return {}

    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        data = metadata.get("data")
        if isinstance(data, dict):
            return data

    data = record.get("data")
    if isinstance(data, dict):
        return data

    return record


def get_rules(record):
    """Return extracted wiki rules, if available."""
    if not isinstance(record, dict):
        return []

    for key in ("wiki_rules", "rules"):
        rules = record.get(key)
        if isinstance(rules, (list, dict)):
            return rules

    return []


def valid_number(value):
    """Convert a value to a finite float or return None."""
    try:
        if value is None:
            return None

        number = float(value)

        if not math.isfinite(number):
            return None

        return number

    except (TypeError, ValueError):
        return None


def calculate_community_metrics(subscribers, created_utc, reference_time):
    """
    Calculate metadata-derived community metrics.

    audience_age_index is a descriptive proxy for audience
    accumulation relative to community age, not posting activity.
    """
    result = {
        "community_age_days": None,
        "log_subscribers": None,
        "audience_age_index": None,
    }

    subscribers = valid_number(subscribers)
    created_utc = valid_number(created_utc)

    if subscribers is not None and subscribers >= 0:
        result["log_subscribers"] = math.log1p(subscribers)

    if created_utc is None or created_utc <= 0:
        return result

    age_days = (reference_time - created_utc) / 86400

    if age_days < 0:
        return result

    result["community_age_days"] = age_days

    if subscribers is not None and subscribers >= 0:
        age_years = age_days / 365.25

        if age_years > 0:
            result["audience_age_index"] = (
                math.log1p(subscribers) / age_years
            )

    return result


# ------------------------------------------------------------
# Load datasets
# ------------------------------------------------------------

df = pd.read_csv(CSV_FILE)

if "subreddit_name" not in df.columns:
    raise KeyError(
        f"Required column 'subreddit_name' not found in {CSV_FILE}"
    )

metadata_index = index_records(load_json(METADATA_FILE))
guidelines_index = index_records(load_json(GUIDELINES_FILE))


# ------------------------------------------------------------
# Output columns
# ------------------------------------------------------------

columns = [
    "has_link_flair",
    "has_user_flair",
    "has_wiki",
    "is_quarantined",
    "subreddit_type",
    "community_age_days",
    "subscribers_at_collection",
    "log_subscribers",
    "audience_age_index",
]

# Reinitialize derived columns to avoid retaining stale values
# from previous runs of this enrichment script.
for col in columns:
    df[col] = None

matched = 0

# ------------------------------------------------------------
# Enrich communities
# ------------------------------------------------------------

for idx, row in df.iterrows():
    subreddit = normalize_name(row["subreddit_name"])
    record = metadata_index.get(subreddit)

    if not record:
        continue

    matched += 1
    meta = get_meta(record)

    # 1. Link flair enabled
    df.at[idx, "has_link_flair"] = to_bool_or_null(
        meta.get("link_flair_enabled")
    )

    # 2. User flair enabled
    # Use the explicit enabled field; do not substitute a
    # permission field with a different meaning.
    df.at[idx, "has_user_flair"] = to_bool_or_null(
        meta.get("user_flair_enabled_in_sr")
    )

    # 3. Wiki enabled
    wiki_enabled = meta.get("wiki_enabled")

    if wiki_enabled is not None:
        df.at[idx, "has_wiki"] = to_bool_or_null(wiki_enabled)
    else:
        # Extracted rules provide evidence that the wiki exists.
        # Missing rules do not prove the wiki is disabled.
        guide = guidelines_index.get(subreddit)

        if guide and get_rules(guide):
            df.at[idx, "has_wiki"] = True

    # 4. Quarantine status
    df.at[idx, "is_quarantined"] = to_bool_or_null(
        meta.get("quarantine")
    )

    # 5. Subreddit type
    df.at[idx, "subreddit_type"] = meta.get("subreddit_type")

    # 6. Subscriber count
    subscribers = valid_number(meta.get("subscribers"))

    if subscribers is not None and subscribers >= 0:
        df.at[idx, "subscribers_at_collection"] = int(subscribers)

    # 7–9. Community age and audience-derived metrics
    created_utc = meta.get("created_utc")

    if created_utc is None:
        created_utc = meta.get("created")

    metrics = calculate_community_metrics(
        subscribers=subscribers,
        created_utc=created_utc,
        reference_time=RETRIEVED_ON,
    )

    for metric, value in metrics.items():
        df.at[idx, metric] = value


# ------------------------------------------------------------
# Save enriched CSV
# ------------------------------------------------------------

df.to_csv(CSV_FILE, index=False, encoding="utf-8")


# ------------------------------------------------------------
# Summary
# ------------------------------------------------------------

print("-" * 60)
print("COMMUNITY METADATA SUMMARY")
print("-" * 60)

print(f"Communities in CSV:       {len(df)}")
print(f"Metadata records indexed: {len(metadata_index)}")
print(f"Metadata records matched: {matched}")
print(f"Metadata records missing: {len(df) - matched}")

print("\nMissing values:")
print(df[columns].isna().sum().to_string())

print("\nBoolean distributions:")

for col in [
    "has_link_flair",
    "has_user_flair",
    "has_wiki",
    "is_quarantined",
]:
    print(f"\n{col}:")
    print(df[col].value_counts(dropna=False).to_string())

print("\nNumeric statistics:")

numeric_columns = [
    "community_age_days",
    "subscribers_at_collection",
    "log_subscribers",
    "audience_age_index",
]

print(df[numeric_columns].describe().round(4).to_string())

print("\nSample:")
print(
    df[["subreddit_name"] + columns]
    .head(10)
    .to_string(index=False)
)

print(f"\nUpdated CSV: {CSV_FILE}")
