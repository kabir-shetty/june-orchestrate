import csv
from pathlib import Path

from llm_client import OUTPUT_HEADERS, DEFAULT_CLAIMS_PATH, build_prediction_rows


REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = REPO_ROOT / "dataset"
ROOT_OUTPUT_PATH = REPO_ROOT / "output.csv"
DATASET_OUTPUT_PATH = DATASET_DIR / "output.csv"


def write_output_csv(rows: list[dict[str, str]]) -> None:
    for output_path in (ROOT_OUTPUT_PATH, DATASET_OUTPUT_PATH):
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_HEADERS)
            writer.writeheader()
            writer.writerows(rows)


def main() -> None:
    rows = build_prediction_rows(DEFAULT_CLAIMS_PATH)
    write_output_csv(rows)
    print(f"Wrote {ROOT_OUTPUT_PATH.name} and {DATASET_OUTPUT_PATH.relative_to(REPO_ROOT)} with {len(rows)} rows.")


if __name__ == "__main__":
    main()
