import json



from pathlib import Path

# --------------------------------------------------
# Configuration
# --------------------------------------------------

# Path to the decompressed source file (no extension).
input_file = Path("F:\subreddits\subreddits_2024-01")

# Directory where the output JSON files will be stored.
output_dir = Path("data")

# Maximum number of records per output file.
records_per_file = 100_000

# Create the output directory if it does not exist.
output_dir.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------
# Split the source into JSON files
# --------------------------------------------------

file_index = 1
record_count = 0
total_records = 0
output_file = None

try:
    with input_file.open("r", encoding="utf-8") as source:

        for line_number, line in enumerate(source, start=1):
            line = line.strip()

            # Ignore empty lines.
            if not line:
                continue

            # Parse and validate each line as a JSON record.
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                print(
                    f"[WARNING] Invalid JSON at line {line_number}: "
                    f"{error.msg}. Line skipped."
                )
                continue

            # Start a new output file every 100,000 records.
            if record_count % records_per_file == 0:
                if output_file is not None:
                    output_file.close()

                output_path = output_dir / (
                    f"subreddits_part_{file_index:03d}.json"
                )

                output_file = output_path.open(
                    "w", encoding="utf-8"
                )

                # Each output file contains a valid JSON array.
                output_file.write("[\n")

                if record_count > 0:
                    file_index += 1

                print(f"[START] Writing {output_path}")

            # Separate records with commas to form a JSON array.
            if record_count % records_per_file != 0:
                output_file.write(",\n")

            json.dump(record, output_file, ensure_ascii=False)

            record_count += 1
            total_records += 1

            # Close the current JSON array at each file boundary.
            if record_count % records_per_file == 0:
                output_file.write("\n]\n")
                output_file.close()
                output_file = None

    # Close the final file if it contains fewer than 100,000 records.
    if output_file is not None:
        output_file.write("\n]\n")
        output_file.close()
        output_file = None

    print("\n[DONE] Splitting completed.")
    print(f"Total valid records: {total_records:,}")
    print(f"Output files created: {file_index}")
    print(f"Output directory: {output_dir.resolve()}")

finally:
    # Ensure an open file is closed if an unexpected error occurs.
    if output_file is not None and not output_file.closed:
        output_file.close()
