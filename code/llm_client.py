import base64
import csv
import hashlib
import io
import json
import mimetypes
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from openai import OpenAI

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = REPO_ROOT / "dataset"
IMAGE_DATA_PATH = REPO_ROOT / "imageData.json"
DEFAULT_CLAIMS_PATH = DATASET_DIR / "claims.csv"
DEFAULT_SAMPLE_PATH = DATASET_DIR / "sample_claims.csv"
MODEL = os.getenv("OPENROUTER_MODEL", "nex-agi/nex-n2-pro:free")

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
RISK_FLAG_SET = set(RISK_FLAG_ORDER)

OUTPUT_HEADERS = [
    "user_id",
    "image_paths",
    "user_claim",
    "claim_object",
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

ISSUE_TYPES = [
    "dent",
    "scratch",
    "crack",
    "glass_shatter",
    "broken_part",
    "missing_part",
    "torn_packaging",
    "crushed_packaging",
    "water_damage",
    "stain",
    "none",
    "unknown",
]

OBJECT_PARTS = {
    "car": [
        "front_bumper",
        "rear_bumper",
        "door",
        "hood",
        "windshield",
        "side_mirror",
        "headlight",
        "taillight",
        "fender",
        "quarter_panel",
        "body",
        "unknown",
    ],
    "laptop": [
        "screen",
        "keyboard",
        "trackpad",
        "hinge",
        "lid",
        "corner",
        "port",
        "base",
        "body",
        "unknown",
    ],
    "package": [
        "box",
        "package_corner",
        "package_side",
        "seal",
        "label",
        "contents",
        "item",
        "unknown",
    ],
}

CLAIM_KEYWORDS = {
    "car": {
        "issueType": {
            "dent": ["dent", "dented", "dents", "hail dents", "bump"],
            "scratch": ["scratch", "scratched", "scrapes", "scrape", "mark"],
            "crack": ["crack", "cracked", "cracks"],
            "glass_shatter": ["shattered", "shatter", "glass shatter", "broken glass"],
            "broken_part": ["broken", "broke", "broken off", "damaged", "damage", "break"],
            "missing_part": ["missing", "fell off", "came off"],
            "water_damage": ["water damage", "wet", "liquid damage", "water damaged"],
            "stain": ["stain", "stained"],
            "none": ["none", "no damage"],
            "unknown": ["unknown"],
        },
        "objectParts": OBJECT_PARTS["car"],
    },
    "laptop": {
        "issueType": {
            "dent": ["dent", "dented", "dents"],
            "scratch": ["scratch", "scratched", "scrapes", "scrape", "mark"],
            "crack": ["crack", "cracked", "cracks"],
            "glass_shatter": ["shattered", "shatter", "glass shatter", "broken glass"],
            "broken_part": ["broken", "broke", "broken off", "damaged", "damage", "break"],
            "missing_part": ["missing", "fell off", "came off", "keys missing", "key missing"],
            "water_damage": ["water damage", "wet", "liquid damage", "water damaged"],
            "stain": ["stain", "stained", "sticky"],
            "none": ["none", "no damage"],
            "unknown": ["unknown"],
        },
        "objectParts": OBJECT_PARTS["laptop"],
    },
    "package": {
        "issueType": {
            "torn_packaging": ["torn", "torn open", "open", "phati", "phata", "opened"],
            "crushed_packaging": ["crushed", "crush", "dented", "dent", "crease", "creased"],
            "water_damage": ["water damage", "wet", "water damaged", "liquid damage"],
            "stain": ["stain", "stained", "oily mark", "oily", "unreadable"],
            "none": ["none", "no damage"],
            "unknown": ["unknown", "missing", "broken"],
        },
        "objectParts": OBJECT_PARTS["package"],
    },
}


def build_client() -> OpenAI:
    api_key = "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"
    if not api_key:
        raise RuntimeError(
            "Set OPENROUTER_API_KEY or OPENAI_API_KEY before running code/llm_client.py."
        )

    return OpenAI(
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=api_key,
    )


def read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []

    rows: list[dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(row)
    return rows


def read_claim_rows(csv_path: Path | None = None) -> list[dict[str, str]]:
    path = csv_path or DEFAULT_CLAIMS_PATH
    rows = read_csv_rows(path)
    if rows:
        return rows
    return read_csv_rows(DEFAULT_SAMPLE_PATH)


@lru_cache(maxsize=1)
def load_user_history() -> dict[str, dict[str, str]]:
    history_path = DATASET_DIR / "user_history.csv"
    rows = read_csv_rows(history_path)
    history: dict[str, dict[str, str]] = {}
    for row in rows:
        user_id = (row.get("user_id") or "").strip()
        if user_id:
            history[user_id] = row
    return history


@lru_cache(maxsize=1)
def load_evidence_requirements() -> list[dict[str, str]]:
    return read_csv_rows(DATASET_DIR / "evidence_requirements.csv")


def row_key(row: dict[str, str]) -> str:
    raw = "|".join(
        [
            (row.get("user_id") or "").strip(),
            (row.get("image_paths") or "").strip(),
            (row.get("user_claim") or "").strip(),
            (row.get("claim_object") or "").strip().lower(),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def encode_image(path: Path) -> dict[str, Any]:
    if Image is not None:
        with Image.open(path) as image:
            converted = image.convert("RGB")
            buffer = io.BytesIO()
            converted.save(buffer, format="PNG")
            mime_type = "image/png"
            data = base64.b64encode(buffer.getvalue()).decode("ascii")
    else:
        mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        data = base64.b64encode(path.read_bytes()).decode("ascii")

    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime_type};base64,{data}"},
    }


def resolve_image_paths(image_paths: str) -> list[Path]:
    paths: list[Path] = []
    for raw_path in image_paths.split(";"):
        candidate = raw_path.strip()
        if not candidate:
            continue
        path = DATASET_DIR / candidate
        if path.exists() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            paths.append(path)
    return paths


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"AI response did not contain a JSON object: {text[:200]}")
    return json.loads(text[start : end + 1])


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value] if value.strip() else []
    text = str(value).strip()
    return [text] if text else []


def expand_semicolon_values(value: Any) -> list[str]:
    values: list[str] = []
    for item in normalize_list(value):
        for token in str(item).split(";"):
            token = token.strip()
            if token:
                values.append(token)
    return values


def merge_ordered_unique(values: list[str], order: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = value.strip().lower()
        if not normalized or normalized in seen:
            continue
        if normalized not in order:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return sorted(ordered, key=lambda item: order.index(item))


def normalize_risk_flags(value: Any) -> list[str]:
    flags = []
    for item in expand_semicolon_values(value):
        normalized = item.strip().lower()
        if normalized in RISK_FLAG_SET and normalized != "none":
            flags.append(normalized)
    if not flags:
        return ["none"]
    return merge_ordered_unique(flags, RISK_FLAG_ORDER)


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


def normalize_severity(value: Any) -> str:
    severity = str(value or "unknown").strip().lower()
    return severity if severity in {"none", "low", "medium", "high", "unknown"} else "unknown"


def normalize_claim_status(value: Any) -> str:
    status = str(value or "not_enough_information").strip().lower()
    return status if status in {"supported", "contradicted", "not_enough_information"} else "not_enough_information"


def normalize_supporting_image_ids(value: Any) -> str:
    ids = [item for item in expand_semicolon_values(value) if item.lower() != "none"]
    return ";".join(ids) if ids else "none"


def normalize_object_part(value: Any, claim_object: str) -> str:
    normalized = str(value or "unknown").strip().lower()
    allowed = OBJECT_PARTS.get(claim_object, ["unknown"])
    return normalized if normalized in allowed else "unknown"


def normalize_issue_type(value: Any) -> str:
    normalized = str(value or "unknown").strip().lower()
    return normalized if normalized in ISSUE_TYPES else "unknown"


def merge_text(values: list[str]) -> str:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        ordered.append(text)
    return " | ".join(ordered)


def split_history_flags(raw_flags: str) -> list[str]:
    flags: list[str] = []
    for token in (raw_flags or "").split(";"):
        normalized = token.strip().lower()
        if normalized in RISK_FLAG_SET and normalized != "none":
            flags.append(normalized)
    if not flags:
        return ["none"]
    return merge_ordered_unique(flags, RISK_FLAG_ORDER)


def determine_risk_flags(user_id: str) -> list[str]:
    row = load_user_history().get(user_id.strip())
    if not row:
        return ["none"]
    return split_history_flags(row.get("history_flags", ""))


def build_prompt(row: dict[str, str], image_paths: list[Path]) -> str:
    claim_object = (row.get("claim_object") or "").strip().lower()
    allowed = CLAIM_KEYWORDS.get(claim_object, {})
    prompt = {
        "task": "Analyze the submitted claim images and return only valid JSON matching the required schema.",
        "user_id": row.get("user_id", ""),
        "claim_object": claim_object,
        "user_claim": row.get("user_claim", ""),
        "image_ids": [path.stem for path in image_paths],
        "image_paths": [path.relative_to(DATASET_DIR).as_posix() for path in image_paths],
        "history_flags": determine_risk_flags(row.get("user_id", "")),
        "allowed_issue_type_values": list(allowed.get("issueType", {}).keys()) if isinstance(allowed.get("issueType"), dict) else [],
        "allowed_object_part_values": OBJECT_PARTS.get(claim_object, ["unknown"]),
        "evidence_requirements": [
            requirement
            for requirement in load_evidence_requirements()
            if (requirement.get("claim_object") or "all").strip().lower() in {"all", claim_object}
        ],
        "required_schema": {
            "evidence_standard_met": "boolean",
            "evidence_standard_met_reason": "string",
            "risk_flags": RISK_FLAG_ORDER,
            "issue_type": f"one of {ISSUE_TYPES}",
            "object_part": f"one of {OBJECT_PARTS.get(claim_object, ['unknown'])}",
            "claim_status": "supported | contradicted | not_enough_information",
            "claim_status_justification": "string",
            "supporting_image_ids": "string separated by semicolons or none",
            "valid_image": "boolean",
            "severity": "none | low | medium | high | unknown",
        },
        "rules": [
            "Use the images as the primary source of truth.",
            "Use the user claim to decide what object and issue should be checked.",
            "Use user history only as risk context; do not override clear visual evidence.",
            "Return only valid JSON and no markdown.",
        ],
    }
    return json.dumps(prompt, ensure_ascii=True)


def analyze_claim_images(client: OpenAI, row: dict[str, str], image_paths: list[Path]) -> dict[str, Any]:
    claim_object = (row.get("claim_object") or "").strip().lower()
    content: list[dict[str, Any]] = [{"type": "text", "text": build_prompt(row, image_paths)}]
    content.extend(encode_image(path) for path in image_paths)

    completion = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": content}],
        temperature=0,
    )
    text = completion.choices[0].message.content or "{}"
    payload = extract_json(text)

    analysis = {
        "evidence_standard_met": normalize_bool(payload.get("evidence_standard_met")),
        "evidence_standard_met_reason": str(payload.get("evidence_standard_met_reason") or "").strip(),
        "risk_flags": normalize_risk_flags(payload.get("risk_flags")),
        "issue_type": normalize_issue_type(payload.get("issue_type")),
        "object_part": normalize_object_part(payload.get("object_part"), claim_object),
        "claim_status": normalize_claim_status(payload.get("claim_status")),
        "claim_status_justification": str(payload.get("claim_status_justification") or "").strip(),
        "supporting_image_ids": normalize_supporting_image_ids(payload.get("supporting_image_ids")),
        "valid_image": normalize_bool(payload.get("valid_image")),
        "severity": normalize_severity(payload.get("severity")),
    }

    analysis["risk_flags"] = normalize_risk_flags(
        analysis["risk_flags"] + determine_risk_flags(row.get("user_id", ""))
    )
    return analysis


def enrich_analysis(row: dict[str, str], analysis: dict[str, Any]) -> dict[str, str]:
    claim_object = (row.get("claim_object") or "").strip().lower()
    risk_flags = normalize_risk_flags(analysis.get("risk_flags"))
    if not risk_flags:
        risk_flags = ["none"]

    return {
        "user_id": row.get("user_id", "").strip(),
        "image_paths": row.get("image_paths", "").strip(),
        "user_claim": row.get("user_claim", "").strip(),
        "claim_object": claim_object,
        "evidence_standard_met": str(normalize_bool(analysis.get("evidence_standard_met"))).lower(),
        "evidence_standard_met_reason": str(analysis.get("evidence_standard_met_reason") or "").strip(),
        "risk_flags": ";".join(risk_flags),
        "issue_type": normalize_issue_type(analysis.get("issue_type")),
        "object_part": normalize_object_part(analysis.get("object_part"), claim_object),
        "claim_status": normalize_claim_status(analysis.get("claim_status")),
        "claim_status_justification": str(analysis.get("claim_status_justification") or "").strip(),
        "supporting_image_ids": normalize_supporting_image_ids(analysis.get("supporting_image_ids")),
        "valid_image": str(normalize_bool(analysis.get("valid_image"))).lower(),
        "severity": normalize_severity(analysis.get("severity")),
    }


def build_image_data(csv_path: Path | None = None) -> dict[str, dict[str, str]]:
    client = build_client()
    rows = read_claim_rows(csv_path)
    image_data: dict[str, dict[str, str]] = {}

    for row in rows:
        image_paths = resolve_image_paths(row.get("image_paths", ""))
        if not image_paths:
            continue
        analysis = analyze_claim_images(client, row, image_paths)
        key = row_key(row)
        image_data[key] = enrich_analysis(row, analysis)

    IMAGE_DATA_PATH.write_text(
        json.dumps(image_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return image_data


def build_prediction_rows(csv_path: Path | None = None) -> list[dict[str, str]]:
    rows = read_claim_rows(csv_path)
    image_data = build_image_data(csv_path)
    predictions: list[dict[str, str]] = []
    for row in rows:
        prediction = image_data.get(row_key(row))
        if prediction is None:
            prediction = enrich_analysis(
                row,
                {
                    "evidence_standard_met": False,
                    "evidence_standard_met_reason": "",
                    "risk_flags": ["none"],
                    "issue_type": "unknown",
                    "object_part": "unknown",
                    "claim_status": "not_enough_information",
                    "claim_status_justification": "",
                    "supporting_image_ids": "none",
                    "valid_image": False,
                    "severity": "unknown",
                },
            )
        predictions.append(prediction)
    return predictions


def main() -> None:
    build_image_data(DEFAULT_CLAIMS_PATH)
    print(f"Wrote {IMAGE_DATA_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
