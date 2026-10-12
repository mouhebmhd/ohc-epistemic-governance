
from pathlib import Path
import hashlib
import json
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

DATA_DIR = Path("data")

SEED_FILE = DATA_DIR / "healthRedditCommunities_enriched.csv"
METADATA_FILE = DATA_DIR / "health_communities.csv"

OUTPUT_DIR = DATA_DIR / "processed"
OUTPUT_FILE = OUTPUT_DIR / "communities.csv"
MANIFEST_FILE = OUTPUT_DIR / "communities.manifest.json"

CLASSIFICATION_COLUMNS = [
    "language",
    "community_type",
    "disease_category",
    "sample_group",
    "has_rules",
]

METADATA_COLUMNS = [
    "has_link_flair",
    "has_user_flair",
    "has_wiki",
    "is_quarantined",
    "subreddit_type",
    "community_age_days",
    "subscribers_at_collection",
    "activity_ratio",
    "log_subscribers",
    "audience_age_index",
]

# Candidate corrections based on community names.
# VERIFY against community URLs, descriptions, or rules before publication.
LANGUAGE_FIXES = {
    "hypochondria": "English",
    "sclerosis": "English",
    "huntington": "English",
    "skin_cancer": "English",
    "pregnancy": "English",
    "sti": "English",
    "aids": "English",
    "vision": "English",
    "healthit": "English",
    "pilaris": "English",
    "suppurativa": "English",
    "menshealthover30": "English",
    "menopause_support": "English",
    "doctissimo": "French",
    "depressionfr": "French",
    "tdah": "French",
    "autisme": "French",
    "endométriose": "French",
    "salute": "Italian",
    "medizin": "German",
    "psychologie": "German",
    "saude": "Portuguese",
    "healthprofessionals": "English",
    "fertility": "English",
}

# Missing sample groups are marked explicitly rather than guessed.
UNASSIGNED_GROUP = "Unassigned"

# Set True only if you have reviewed the mappings above.
# When False, the script still runs but records that the language
# corrections have not yet been verified.
LANGUAGE_FIXES_VERIFIED = False


# ============================================================
# HELPERS
# ============================================================

def normalize_name(series):
    """Normalize subreddit names for reliable joining."""
    return (
        series.astype("string")
        .str.strip()
        .str.replace(r"(?i)^r/", "", regex=True)
        .str.casefold()
    )


def is_missing(series):
    """Identify null, empty, and whitespace-only values."""
    text = series.astype("string").str.strip()
    return series.isna() | text.eq("").fillna(True)


def sha256_file(path):
    """Calculate a file's SHA-256 checksum."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def check_unique_names(frame, label):
    """Stop if normalized subreddit names are duplicated."""
    duplicated = frame["_join_name"].duplicated(keep=False)

    if duplicated.any():
        names = (
            frame.loc[duplicated, "subreddit_name"]
            .astype(str)
            .tolist()
        )

        raise ValueError(
            f"Duplicate subreddit names in {label}: {names[:30]}"
        )


def apply_language_fixes(frame):
    """
    Fill only missing language values.
    Existing language labels are never overwritten.
    """
    frame["language"] = frame["language"].astype("string").str.strip()

    applied = []
    unresolved = []

    for name, language in LANGUAGE_FIXES.items():
        normalized = name.strip().removeprefix("r/").casefold()

        mask = (
            frame["_join_name"].eq(normalized)
            & is_missing(frame["language"])
        )

        if mask.any():
            frame.loc[mask, "language"] = language
            applied.append({
                "subreddit_name": name,
                "language_assigned": language,
                "verified": LANGUAGE_FIXES_VERIFIED,
            })

    missing = is_missing(frame["language"])

    if missing.any():
        unresolved = (
            frame.loc[missing, "subreddit_name"]
            .astype(str)
            .tolist()
        )

    return applied, unresolved


def normalize_boolean_column(series, column_name):
    """Convert recognized Boolean representations to True/False."""
    mapping = {
        "true": True,
        "false": False,
        "1": True,
        "0": False,
        "yes": True,
        "no": False,
    }

    text = series.astype("string").str.strip().str.lower()
    missing = is_missing(series)
    invalid = ~text.isin(mapping) & ~missing

    if invalid.any():
        raise ValueError(
            f"Invalid values in '{column_name}': "
            f"{series[invalid].astype(str).unique().tolist()}"
        )

    # Preserve unknown values as nullable Boolean rather than
    # silently treating them as False.
    result = text.map(mapping).astype("boolean")
    result[missing] = pd.NA

    return result


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 65)
    print("FREEZING REDDIT HEALTH COMMUNITY SAMPLE")
    print("=" * 65)

    # --------------------------------------------------------
    # 1. Check input files
    # --------------------------------------------------------
    for path in (SEED_FILE, METADATA_FILE):
        if not path.exists():
            raise FileNotFoundError(
                f"Input file not found: {path.resolve()}"
            )

    seed = pd.read_csv(SEED_FILE, low_memory=False)
    metadata = pd.read_csv(METADATA_FILE, low_memory=False)

    print(f"\nEnriched sample rows: {len(seed)}")
    print(f"Metadata rows:        {len(metadata)}")

    # --------------------------------------------------------
    # 2. Validate schemas
    # --------------------------------------------------------
    required_seed = {
        "subreddit_name",
        "subreddit_url",
        *CLASSIFICATION_COLUMNS,
    }

    required_metadata = {
        "subreddit_name",
        *METADATA_COLUMNS,
    }

    missing_seed_columns = required_seed - set(seed.columns)
    missing_metadata_columns = required_metadata - set(metadata.columns)

    if missing_seed_columns:
        raise ValueError(
            "Missing columns in enriched file: "
            f"{sorted(missing_seed_columns)}"
        )

    if missing_metadata_columns:
        raise ValueError(
            "Missing columns in metadata file: "
            f"{sorted(missing_metadata_columns)}"
        )

    # --------------------------------------------------------
    # 3. Normalize community names
    # --------------------------------------------------------
    seed["_join_name"] = normalize_name(seed["subreddit_name"])
    metadata["_join_name"] = normalize_name(metadata["subreddit_name"])

    if (
        seed["_join_name"].isna().any()
        or seed["_join_name"].eq("").any()
    ):
        raise ValueError(
            "The enriched file contains empty subreddit names."
        )

    if (
        metadata["_join_name"].isna().any()
        or metadata["_join_name"].eq("").any()
    ):
        raise ValueError(
            "The metadata file contains empty subreddit names."
        )

    check_unique_names(seed, "enriched file")
    check_unique_names(metadata, "metadata file")

    # --------------------------------------------------------
    # 4. Correct missing language labels
    # --------------------------------------------------------
    language_fixes_applied, unresolved_languages = apply_language_fixes(
        seed
    )

    print("\nLanguage corrections applied:")
    print(f"  {len(language_fixes_applied)}")

    if language_fixes_applied:
        for item in language_fixes_applied:
            verification = (
                "verified" if item["verified"] else "UNVERIFIED CANDIDATE"
            )
            print(
                f"  {item['subreddit_name']}: "
                f"{item['language_assigned']} [{verification}]"
            )

    if unresolved_languages:
        print("\nCommunities still missing a language:")
        for name in unresolved_languages:
            print(f"  - {name}")

        raise ValueError(
            f"{len(unresolved_languages)} communities still lack language "
            "labels. Review their URLs/descriptions and add verified "
            "corrections to LANGUAGE_FIXES."
        )

    # --------------------------------------------------------
    # 5. Handle missing sample_group values
    # --------------------------------------------------------
    seed["sample_group"] = seed["sample_group"].astype("string").str.strip()

    missing_groups = is_missing(seed["sample_group"])
    missing_group_names = (
        seed.loc[missing_groups, "subreddit_name"]
        .astype(str)
        .tolist()
    )

    if missing_groups.any():
        seed.loc[missing_groups, "sample_group"] = UNASSIGNED_GROUP

        print(
            f"\nWARNING: {len(missing_group_names)} communities lack "
            f"a sample_group. They are marked '{UNASSIGNED_GROUP}'."
        )

        for name in missing_group_names:
            print(f"  - {name}")

    # --------------------------------------------------------
    # 6. Validate remaining classifications
    # --------------------------------------------------------
    errors = []

    for column in CLASSIFICATION_COLUMNS:
        if column == "sample_group":
            continue

        missing = is_missing(seed[column])

        if missing.any():
            names = (
                seed.loc[missing, "subreddit_name"]
                .astype(str)
                .tolist()
            )
            errors.append((column, names))

    if errors:
        print("\nMissing or blank classification labels:")

        for column, names in errors:
            print(f"\n{column} ({len(names)} communities):")
            for name in names[:100]:
                print(f"  - {name}")

        raise ValueError(
            "Required classification labels are incomplete. "
            "Correct them in the enriched CSV before freezing."
        )

    # has_rules must represent an explicit classification.
    seed["has_rules"] = normalize_boolean_column(
        seed["has_rules"], "has_rules"
    )

    # --------------------------------------------------------
    # 7. Merge metadata onto the existing sample
    # --------------------------------------------------------
    metadata_subset = metadata[["_join_name"] + METADATA_COLUMNS]

    final = seed.merge(
        metadata_subset,
        on="_join_name",
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    final["metadata_match"] = final["_merge"].eq("both")

    unmatched_metadata = (
        final.loc[~final["metadata_match"], "subreddit_name"]
        .astype(str)
        .tolist()
    )

    final = final.drop(columns=["_join_name", "_merge"])

    # Normalize metadata Boolean columns while preserving unknowns.
    for column in [
        "has_link_flair",
        "has_user_flair",
        "has_wiki",
        "is_quarantined",
    ]:
        final[column] = normalize_boolean_column(final[column], column)

    # --------------------------------------------------------
    # 8. Sort deterministically
    # --------------------------------------------------------
    final = final.sort_values(
        ["language", "disease_category", "subreddit_name"],
        key=lambda col: col.astype("string").str.casefold(),
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)

    # Retain the original sample-defining fields first.
    ordered_columns = [
        "subreddit_index",
        "subreddit_name",
        "subreddit_url",
        "language",
        "community_type",
        "disease_category",
        "sample_group",
        "has_rules",
        *METADATA_COLUMNS,
        "metadata_match",
    ]

    # Handle an optional subreddit_index column safely.
    ordered_columns = [
        col for col in ordered_columns if col in final.columns
    ]
    final = final[ordered_columns]

    # --------------------------------------------------------
    # 9. Create output directory and protect existing sample
    # --------------------------------------------------------
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if OUTPUT_FILE.exists():
        raise FileExistsError(
            f"\nFrozen sample already exists: {OUTPUT_FILE}\n"
            "It has not been overwritten. Archive the old version and "
            "document the reason before deliberately rebuilding it."
        )

    # --------------------------------------------------------
    # 10. Save final CSV
    # --------------------------------------------------------
    final.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8",
    )

    output_hash = sha256_file(OUTPUT_FILE)

    # --------------------------------------------------------
    # 11. Save reproducibility manifest
    # --------------------------------------------------------
    manifest = {
        "output_file": str(OUTPUT_FILE),
        "rows": int(len(final)),
        "columns": final.columns.tolist(),
        "sha256": output_hash,
        "seed_file": str(SEED_FILE),
        "seed_sha256": sha256_file(SEED_FILE),
        "metadata_file": str(METADATA_FILE),
        "metadata_sha256": sha256_file(METADATA_FILE),
        "metadata_matched": int(final["metadata_match"].sum()),
        "metadata_unmatched": int((~final["metadata_match"]).sum()),
        "unmatched_communities": unmatched_metadata,
        "sort_order": [
            "language",
            "disease_category",
            "subreddit_name",
        ],
        "language_fixes": language_fixes_applied,
        "language_fixes_verified": LANGUAGE_FIXES_VERIFIED,
        "unresolved_language_labels": unresolved_languages,
        "unassigned_sample_group_count": len(missing_group_names),
        "unassigned_sample_group_communities": missing_group_names,
        "note": (
            "Sample membership and existing classifications originate from "
            "the enriched CSV. Metadata was left-joined by normalized "
            "subreddit name. Unassigned sample groups require review. "
            "Language candidates must be verified before publication."
        ),
    }

    MANIFEST_FILE.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # 12. Report summary
    # --------------------------------------------------------
    print("\n" + "=" * 65)
    print("COMMUNITY SAMPLE FROZEN")
    print("=" * 65)

    print(f"Total communities:        {len(final)}")
    print(f"Metadata matched:         {manifest['metadata_matched']}")
    print(f"Metadata unmatched:       {manifest['metadata_unmatched']}")
    print(f"Language corrections:     {len(language_fixes_applied)}")
    print(f"Unassigned sample groups: {len(missing_group_names)}")

    print(f"\nCSV:      {OUTPUT_FILE.resolve()}")
    print(f"Manifest: {MANIFEST_FILE.resolve()}")
    print(f"SHA-256:  {output_hash}")

    print("\nCommunities by language:")
    print(final["language"].value_counts(dropna=False).to_string())

    print("\nCommunities by sample group:")
    print(final["sample_group"].value_counts(dropna=False).to_string())

    if unmatched_metadata:
        print("\nCommunities without matching metadata:")
        for name in unmatched_metadata:
            print(f"  - {name}")

    print("\nReview the manifest before using this sample in an analysis.")


if __name__ == "__main__":
    main()
