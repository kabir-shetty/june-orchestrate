import csv
import json
from pathlib import Path
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = REPO_ROOT / "dataset"

def main():
    # run helper files
    subprocess.run(['python', 'claim_extractor.py'])

    # load json data into memory
    with open(REPO_ROOT / "claimData.json", "r", encoding="utf-8") as f:
        claimData = json.load(f)

    # generate output.csv
    csv_rows = []
    headers = [
        "user",
        "evidence_standard_met",
        "evidence_standard_met_reason",
        "risk_flags",
        "issue_type",
        "object_part",
        "claim_status",
        "claim_status_justification",
        "supporting_image_ids",
        "valid_image",
        "severity"
    ]
    for user in claimData:
        csvAppend = {
            "user": user,
            "evidence_standard_met": None,
            "evidence_standard_met_reason": None,
            "risk_flags": None,
            "issue_type": None,
            "object_part": None,
            "claim_status": None,
            "claim_status_justification": None,
            "supporting_image_ids": None,
            "valid_image": None,
            "severity": None
        }

        # add all the info to csvappend

        csv_rows.append(csvAppend)

    # add csvappend to output.csv
    with open(DATASET_DIR / "output.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(csv_rows)


if __name__ == "__main__":
    main()
