import csv
import json
from pathlib import Path

CSV_FILE = Path("data/reddit_health_communities_multilingual.csv")
INPUT_DIR = Path(r"F:\file Two")
OUTPUT_DIR = Path("data/filtered_metadata")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load community names
with open(CSV_FILE, encoding="utf-8-sig", newline="") as f:
    targets = {
        row["subreddit_name"].strip().lower().removeprefix("r/")
        for row in csv.DictReader(f)
        if row.get("subreddit_name", "").strip()
    }

print(f"Target communities: {len(targets)}")


def scan_json_objects(path):
    """
    Scan a large file incrementally, extracting brace-delimited objects.
    Does not load the entire file into memory.
    """
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


def normalized_name(record):
    name = (
        record.get("display_name")
        or record.get("display_name_prefixed")
        or ""
    )
    name = str(name).strip().lower()

    if name.startswith("/r/"):
        name = name[3:]
    elif name.startswith("r/"):
        name = name[2:]

    return name.strip("/")


total = 0
matched = 0
deleted = 0
files_with_errors = 0

for source in INPUT_DIR.rglob("*.json"):
    print(f"\nProcessing: {source}")

    relative = source.relative_to(INPUT_DIR)
    destination = OUTPUT_DIR / relative
    destination.parent.mkdir(parents=True, exist_ok=True)

    temp = destination.with_suffix(destination.suffix + ".tmp")
    file_matches = 0
    file_errors = 0
    file_records = 0

    try:
        with open(temp, "w", encoding="utf-8") as out:
            out.write("[\n")
            first = True

            for record, error in scan_json_objects(source):
                if error:
                    file_errors += 1
                    continue

                # Ignore nested objects such as _meta
                if not record or not record.get("display_name"):
                    continue

                file_records += 1
                total += 1

                if record.get("subreddit_type") == "user":
                    continue

                name = normalized_name(record)

                if name not in targets:
                    continue

                if not first:
                    out.write(",\n")

                json.dump(record, out, ensure_ascii=False)
                first = False
                file_matches += 1

            out.write("\n]\n")

        if file_matches:
            temp.replace(destination)
            matched += file_matches
            print(f"  Matches saved: {file_matches}")
        else:
            temp.unlink(missing_ok=True)
            print("  No matches")

        if file_errors:
            files_with_errors += 1
            print(f"  {file_errors} malformed object(s); source preserved")

        elif file_records > 0:
            # Delete only after successful, error-free scanning
            source.unlink()
            deleted += 1
            print("  Source deleted after successful processing")

        else:
            print("  No community records recognized; source preserved")

    except (OSError, UnicodeDecodeError) as exc:
        files_with_errors += 1
        temp.unlink(missing_ok=True)
        print(f"  ERROR — source preserved: {exc}")

print("\n========== SUMMARY ==========")
print(f"Community records examined: {total}")
print(f"Matching records saved: {matched}")
print(f"Source files deleted: {deleted}")
print(f"Files with errors: {files_with_errors}")
print(f"Output directory: {OUTPUT_DIR}")
