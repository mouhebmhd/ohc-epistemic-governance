
import json
from pathlib import Path

FILE = Path("data/reddit_health_communities_metadata.json")

with FILE.open("r", encoding="utf-8") as f:
    data = json.load(f)

print("Dataset type:", type(data).__name__)
print("Number of records:", len(data) if isinstance(data, list) else "N/A")


def find_descriptions(obj, path="$"):
    """Find description fields at any nesting level."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            current_path = f"{path}.{key}"

            if "description" in key.lower():
                if isinstance(value, str):
                    print(f"\nFOUND: {current_path}")
                    print("Length:", len(value))
                    print("Preview:", repr(value[:300]))
                elif value is not None:
                    print(f"\nFOUND NON-STRING: {current_path}")
                    print("Type:", type(value).__name__)

            find_descriptions(value, current_path)

    elif isinstance(obj, list):
        for i, value in enumerate(obj[:3]):
            find_descriptions(value, f"{path}[{i}]")


for i, record in enumerate(data[:3]):
    print(f"\n{'=' * 60}")
    print(f"RECORD {i + 1}")
    print("Top-level keys:", list(record.keys()))
    find_descriptions(record, f"$[{i}]")
