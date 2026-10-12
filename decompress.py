
import zstandard as zstd
from pathlib import Path

files = [
    Path("subreddits_2024-01.zst"),
    Path("subreddits_meta_only_2024-01.zst"),
]

for file in files:
    if not file.exists():
        print(f"File not found: {file}")
        continue

    output = file.with_suffix("")
    print(f"Decompressing {file.name}...")

    with file.open("rb") as source:
        with output.open("wb") as destination:
            zstd.ZstdDecompressor().copy_stream(
                source, destination
            )

    print(f"Completed: {output.name}")

print("All files processed.")
