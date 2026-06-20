import csv
import json
from pathlib import Path
from typing import Any

try:
    from llm_client import main as build_image_data_json
except ImportError:  # pragma: no cover
    build_image_data_json = None


REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = REPO_ROOT / "dataset"
IMAGE_DATA_PATH = REPO_ROOT / "imageData.json"
OUTPUT_PATH = DATASET_DIR / "output.csv"
OUTPUT_HEADERS = [
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
    "severity",
]
RISK_FLAG_ORDER = [
    "none",
    "blurry_image",
    "cropped_or_obstructed",
    "low_light_or_glare",
    "wrong_angle",
    "wrong_object",
    "wrong_object_part",
    "damage_not_visible",
    "claim_mismatch",
    "possible_manipulation",
    "non_original_image",
    "text_instruction_present",
    "user_history_risk",
    "manual_review_required",
]
SEVERITY_ORDER = ["none", "low", "medium", "high", "unknown"]
STATUS_ORDER = ["not_enough_information", "contradicted", "supported"]


def main() -> None:
    ensure_image_data()
    image_data = load_image_data()
    rows = build_output_rows(image_data)

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def ensure_image_data() -> None:
    if IMAGE_DATA_PATH.exists() and IMAGE_DATA_PATH.stat().st_size > 0:
        return
    if build_image_data_json is None:
        raise RuntimeError(
            "imageData.json is missing or empty, and llm_client.py could not be imported."
        )
    build_image_data_json()


def load_image_data() -> dict[str, Any]:
    if not IMAGE_DATA_PATH.exists():
        return {}
    with IMAGE_DATA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_output_rows(image_data: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for user_id in sorted(image_data):
        user_data = image_data.get(user_id, {})
        analyses = collect_analyses(user_data)
        rows.append(flatten_user_row(user_id, analyses))
    return rows


def collect_analyses(user_data: Any) -> list[dict[str, Any]]:
    if not isinstance(user_data, dict):
        return []

    if any(key in user_data for key in OUTPUT_HEADERS if key != "user"):
        return [user_data]

    analyses: list[dict[str, Any]] = []
    for value in user_data.values():
        if isinstance(value, dict):
            analyses.append(value)
    return analyses


def flatten_user_row(user_id: str, analyses: list[dict[str, Any]]) -> dict[str, str]:
    if not analyses:
        return {header: "" for header in OUTPUT_HEADERS}

    evidence_met = any(normalize_bool(analysis.get("evidence_standard_met")) for analysis in analyses)
    valid_image = any(normalize_bool(analysis.get("valid_image")) for analysis in analyses)

    merged_risk_flags = merge_flags(
        *(analysis.get("risk_flags") for analysis in analyses)
    )
    merged_issue_types = merge_text_values(
        *(analysis.get("issue_type") for analysis in analyses)
    )
    merged_object_parts = merge_text_values(
        *(analysis.get("object_part") for analysis in analyses)
    )
    merged_statuses = merge_text_values(
        *(analysis.get("claim_status") for analysis in analyses),
        order=STATUS_ORDER,
    )
    merged_severities = merge_text_values(
        *(analysis.get("severity") for analysis in analyses),
        order=SEVERITY_ORDER,
    )

    return {
        "user": user_id,
        "evidence_standard_met": str(evidence_met).lower(),
        "evidence_standard_met_reason": join_unique_text(
            *(analysis.get("evidence_standard_met_reason") for analysis in analyses)
        ),
        "risk_flags": ";".join(merged_risk_flags),
        "issue_type": ";".join(merged_issue_types),
        "object_part": ";".join(merged_object_parts),
        "claim_status": merged_statuses[-1] if merged_statuses else "",
        "claim_status_justification": join_unique_text(
            *(analysis.get("claim_status_justification") for analysis in analyses)
        ),
        "supporting_image_ids": merge_supporting_image_ids(
            *(analysis.get("supporting_image_ids") for analysis in analyses)
        ),
        "valid_image": str(valid_image).lower(),
        "severity": merged_severities[-1] if merged_severities else "",
    }


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


def expand_text_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            parts.extend(expand_text_values(item))
        return parts

    text = str(value).strip()
    if not text:
        return []

    return [part.strip() for part in text.split(";") if part.strip()]


def merge_text_values(*values: Any, order: list[str] | None = None) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in expand_text_values(value):
            normalized = item.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)

    if order is not None:
        return sorted(ordered, key=lambda item: order.index(item) if item in order else len(order))
    return ordered


def merge_flags(*values: Any) -> list[str]:
    merged = merge_text_values(*values, order=RISK_FLAG_ORDER)
    filtered = [flag for flag in merged if flag in RISK_FLAG_ORDER and flag != "none"]
    if not filtered:
        return ["none"]
    return filtered


def merge_supporting_image_ids(*values: Any) -> str:
    ids: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in expand_text_values(value):
            normalized = item.strip()
            if not normalized or normalized.lower() == "none" or normalized in seen:
                continue
            seen.add(normalized)
            ids.append(normalized)
    return ";".join(ids) if ids else "none"


def join_unique_text(*values: Any) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in expand_text_values(value):
            normalized = item.strip()
            key = normalized.lower()
            if not normalized or key in seen:
                continue
            seen.add(key)
            parts.append(normalized)
    return " | ".join(parts)


if __name__ == "__main__":
    main()
