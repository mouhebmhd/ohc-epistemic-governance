
import csv
import json
from pathlib import Path
from collections import Counter

CSV_FILE = Path("data/reddit_health_communities_multilingual.csv")
METADATA_DIR = Path(r"data/filtered_metadata")

OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------
# 1. Load target communities from CSV
# --------------------------------------------------

def normalize_name(name):
    name = str(name or "").strip().lower()

    if name.startswith("/r/"):
        name = name[3:]
    elif name.startswith("r/"):
        name = name[2:]

    return name.strip("/")

with open(CSV_FILE, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)

    if not reader.fieldnames or "subreddit_name" not in reader.fieldnames:
        raise ValueError(
            "CSV must contain a 'subreddit_name' column."
        )

    communities = {}

    for row in reader:
        original_name = row.get("subreddit_name", "").strip()
        normalized = normalize_name(original_name)

        if normalized:
            communities.setdefault(normalized, original_name)

targets = set(communities)

print(f"Unique communities in CSV: {len(targets)}")

# --------------------------------------------------
# 2. Scan JSON objects incrementally
#    Handles arrays, concatenated JSON objects,
#    and JSON objects embedded in larger structures.
# --------------------------------------------------

def scan_json_objects(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        buffer = []
        depth = 0
        in_string = False
        escaped = False
        started = False

        while True:
            chunk = f.read(1024 * 1024)

            if not chunk:
                break

            for char in chunk:
                if not started:
                    if char == "{":
                        started = True
                        depth = 1
                        buffer = ["{"]
                    continue

                buffer.append(char)

                if in_string:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        in_string = False
                    continue

                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1

                    if depth == 0:
                        raw = "".join(buffer)
                        started = False
                        buffer = []

                        try:
                            obj = json.loads(raw)
                            if isinstance(obj, dict):
                                yield obj, None
                        except json.JSONDecodeError as exc:
                            yield None, str(exc)

        if started:
            yield None, "Incomplete JSON object at end of file"

# --------------------------------------------------
# 3. Search all metadata files
# --------------------------------------------------

found = Counter()
files_scanned = 0
files_with_errors = []

json_files = list(METADATA_DIR.rglob("*.json"))

print(f"JSON files found: {len(json_files)}")

for file_path in json_files:
    files_scanned += 1
    file_errors = 0

    print(
        f"\rScanning file {files_scanned}/{len(json_files)}",
        end="",
        flush=True,
    )

    try:
        for record, error in scan_json_objects(file_path):
            if error:
                file_errors += 1
                continue

            if not record:
                continue

            # Count only subreddit/community records
            if record.get("subreddit_type") == "user":
                continue

            name = normalize_name(
                record.get("display_name")
                or record.get("display_name_prefixed")
            )

            if name in targets:
                found[name] += 1

        if file_errors:
            files_with_errors.append(
                (str(file_path), file_errors)
            )

    except (OSError, UnicodeDecodeError) as exc:
        files_with_errors.append((str(file_path), str(exc)))

print("\n")

# --------------------------------------------------
# 4. Compare CSV communities with metadata
# --------------------------------------------------

with_metadata = sorted(
    name for name in targets if found[name] > 0
)

without_metadata = sorted(
    name for name in targets if found[name] == 0
)

duplicates = sorted(
    name for name in targets if found[name] > 1
)

total = len(targets)
coverage = (len(with_metadata) / total * 100) if total else 0

# --------------------------------------------------
# 5. Save results
# --------------------------------------------------

def save_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["subreddit_name", "metadata_records"])

        for name in rows:
            writer.writerow([communities[name], found[name]])

save_csv(
    OUTPUT_DIR / "communities_with_metadata.csv",
    with_metadata,
)

save_csv(
    OUTPUT_DIR / "communities_without_metadata.csv",
    without_metadata,
)

save_csv(
    OUTPUT_DIR / "communities_with_duplicate_metadata.csv",
    duplicates,
)

# --------------------------------------------------
# 6. Print summary
# --------------------------------------------------

print("=" * 50)
print("METADATA COVERAGE REPORT")
print("=" * 50)
print(f"Unique CSV communities:       {total}")
print(f"Communities WITH metadata:    {len(with_metadata)}")
print(f"Communities WITHOUT metadata: {len(without_metadata)}")
print(f"Communities with duplicates:  {len(duplicates)}")
print(f"Metadata coverage:            {coverage:.2f}%")
print(f"JSON files scanned:           {files_scanned}")
print(f"Files with parsing/read errors: {len(files_with_errors)}")

print("\nResults saved in:")
print(f"  {OUTPUT_DIR / 'communities_with_metadata.csv'}")
print(f"  {OUTPUT_DIR / 'communities_without_metadata.csv'}")
print(f"  {OUTPUT_DIR / 'communities_with_duplicate_metadata.csv'}")

if files_with_errors:
    print("\nWARNING: Some files had errors and need checking:")
    for path, error in files_with_errors:
        print(f"  {path}: {error}")
