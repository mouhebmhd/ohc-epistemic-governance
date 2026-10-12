import csv
import json
import os
import time
from pathlib import Path
from urllib.parse import quote

import requests

# ============================================================
# Configuration
# ============================================================

INPUT_CSV = Path("data/health_communities.csv")
OUTPUT_JSON = Path("data/reddit_health_communities_metadata.json")
ERRORS_JSONL = Path("data/reddit_metadata_errors.jsonl")

BASE_URL = "https://app.kodexisapi.com/marketplace/reddit/api/reddit"

# Set the API key in your environment:
# PowerShell:
API_KEY = "kp_live_c8aE2YR-WbHYgf5vL0dVa2Vp7bmzdFwz32zE5qE3-aE"

TIMEOUT = 15
MAX_RETRIES = 4
REQUEST_DELAY = 0.5

HEADERS = {
    "X-API-Key": API_KEY or "",
    "Accept": "application/json",
}


# ============================================================
# JSON helpers
# ============================================================

def load_existing_dataset():
    """Load previously collected records to support resuming."""
    if not OUTPUT_JSON.exists():
        return []

    try:
        with OUTPUT_JSON.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError("The output JSON must contain a list.")

        return data

    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(
            f"Cannot safely resume from {OUTPUT_JSON}: {exc}"
        ) from exc


def save_dataset(records):
    """Atomically save the dataset to avoid losing progress."""
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    temporary_file = OUTPUT_JSON.with_suffix(".json.tmp")

    with temporary_file.open("w", encoding="utf-8") as f:
        json.dump(
            records,
            f,
            ensure_ascii=False,
            indent=2,
        )

    temporary_file.replace(OUTPUT_JSON)


def log_error(error_record):
    """Append a failure to a JSONL error log."""
    ERRORS_JSONL.parent.mkdir(parents=True, exist_ok=True)

    with ERRORS_JSONL.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(error_record, ensure_ascii=False) + "\n"
        )


# ============================================================
# API request
# ============================================================

def fetch_subreddit_metadata(session, subreddit_name):
    """
    Fetch metadata for one subreddit.

    Returns:
        (metadata, None) on success
        (None, error_details) on failure
    """
    safe_name = quote(subreddit_name, safe="")
    url = f"{BASE_URL}/{safe_name}/info"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(
                url,
                headers=HEADERS,
                timeout=TIMEOUT,
            )

            if response.status_code == 200:
                try:
                    metadata = response.json()
                except ValueError:
                    return None, {
                        "status_code": 200,
                        "error": "API returned invalid JSON",
                        "response_excerpt": response.text[:1000],
                    }

                return metadata, None

            # Retry rate limits and temporary server errors.
            if (
                response.status_code == 429
                or response.status_code >= 500
            ):
                if attempt < MAX_RETRIES:
                    retry_after = response.headers.get("Retry-After")

                    try:
                        wait = float(retry_after)
                    except (TypeError, ValueError):
                        wait = min(2 ** (attempt - 1), 30)

                    time.sleep(wait)
                    continue

            # Permanent errors: do not retry.
            return None, {
                "status_code": response.status_code,
                "error": response.text[:1000],
            }

        except requests.RequestException as exc:
            if attempt == MAX_RETRIES:
                return None, {
                    "status_code": None,
                    "error": str(exc),
                }

            time.sleep(min(2 ** (attempt - 1), 30))

    return None, {
        "status_code": None,
        "error": "Maximum retries exceeded",
    }


# ============================================================
# Main collection process
# ============================================================

def main():
    if not API_KEY:
        raise SystemExit(
            "ERROR: Set the KODEXIS_REDDIT_API_KEY environment variable."
        )

    if not INPUT_CSV.exists():
        raise SystemExit(f"ERROR: CSV not found: {INPUT_CSV}")

    # Read and validate the updated CSV.
    with INPUT_CSV.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        reader = csv.DictReader(f)

        required_columns = {
            "subreddit_index",
            "subreddit_name",
            "subreddit_url",
        }

        missing = required_columns - set(reader.fieldnames or [])

        if missing:
            raise SystemExit(
                f"ERROR: Missing CSV columns: {sorted(missing)}"
            )

        communities = []
        seen = set()

        for row in reader:
            name = (row.get("subreddit_name") or "").strip()

            if not name:
                continue

            # Avoid duplicate requests for the same subreddit.
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)

            raw_index = (row.get("subreddit_index") or "").strip()

            try:
                subreddit_index = int(raw_index)
            except ValueError:
                subreddit_index = raw_index

            communities.append({
                "subreddit_index": subreddit_index,
                "subreddit_name": name,
                "subreddit_url": (
                    row.get("subreddit_url") or ""
                ).strip(),
            })

    # Load previous results for resumability.
    dataset = load_existing_dataset()

    completed = {
        record["subreddit_name"].casefold()
        for record in dataset
        if record.get("subreddit_name")
        and record.get("metadata") is not None
        and not record.get("collection_error")
    }

    pending = [
        community
        for community in communities
        if community["subreddit_name"].casefold() not in completed
    ]

    print(f"Communities in CSV: {len(communities)}")
    print(f"Already collected:  {len(completed)}")
    print(f"Remaining:          {len(pending)}")
    print(f"Output:             {OUTPUT_JSON}")
    print(f"Error log:          {ERRORS_JSONL}")
    print("-" * 60)

    successes = 0
    failures = 0

    with requests.Session() as session:
        for index, community in enumerate(pending, start=1):
            name = community["subreddit_name"]

            print(
                f"[{index}/{len(pending)}] "
                f"Collecting r/{name} ... ",
                end="",
                flush=True,
            )

            metadata, error = fetch_subreddit_metadata(
                session,
                name,
            )

            if error is None:
                record = {
                    **community,
                    "metadata": metadata,
                    "collection_error": None,
                }

                dataset.append(record)
                completed.add(name.casefold())
                successes += 1

                # Save after every successful request.
                save_dataset(dataset)
                print("OK")

            else:
                failures += 1

                log_error({
                    **community,
                    "endpoint": (
                        f"{BASE_URL}/{quote(name, safe='')}/info"
                    ),
                    **error,
                    "attempted_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ",
                        time.gmtime(),
                    ),
                })

                print(
                    f"FAILED ({error.get('status_code')}: "
                    f"{error.get('error', '')[:120]})"
                )

            time.sleep(REQUEST_DELAY)

    print("\n" + "=" * 60)
    print("COLLECTION FINISHED")
    print(f"Successful this run: {successes}")
    print(f"Failed this run:     {failures}")
    print(f"Total saved records: {len(dataset)}")
    print(f"Dataset:             {OUTPUT_JSON}")
    print(f"Failures:            {ERRORS_JSONL}")
    print("\nRun the script again to retry failed communities.")


if __name__ == "__main__":
    main()
