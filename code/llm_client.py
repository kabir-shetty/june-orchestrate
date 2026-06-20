import base64
import csv
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
OUTPUT_PATH = REPO_ROOT / "imageData.json"
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


dataKeywords = {
    'car': {
        'issueType': {
            'dent': ['dent', 'dented', 'dents', 'hail dents', 'bump'],
            'scratch': ['scratch', 'scratched', 'scrapes', 'scrape', 'mark', 'scrape lag gaya'],
            'crack': ['crack', 'cracked', 'cracks'],
            'glass_shatter': ['shattered', 'shatter', 'glass shatter', 'broken glass'],
            'broken_part': ['broken', 'broke', 'broken off', 'damaged', 'damage', 'break'],
            'missing_part': ['missing', 'fell off', 'came off'],
            'water_damage': ['water damage', 'wet', 'liquid damage', 'water damaged'],
            'stain': ['stain', 'stained'],
            'none': ['none', 'no damage'],
            'unknown': ['unknown']
        },
        'objectParts': [
            'front bumper',
            'rear bumper',
            'headlight',
            'taillight',
            'windshield',
            'side mirror',
            'door',
            'hood',
            'fender',
            'quarter panel',
            'body',
            'unknown',
        ],
    },
    'laptop': {
        'issueType': {
            'dent': ['dent', 'dented', 'dents'],
            'scratch': ['scratch', 'scratched', 'scrapes', 'scrape', 'mark'],
            'crack': ['crack', 'cracked', 'cracks'],
            'glass_shatter': ['shattered', 'shatter', 'glass shatter', 'broken glass'],
            'broken_part': ['broken', 'broke', 'broken off', 'damaged', 'damage', 'break'],
            'missing_part': ['missing', 'fell off', 'came off', 'keys missing', 'key missing'],
            'water_damage': ['water damage', 'wet', 'liquid damage', 'water damaged'],
            'stain': ['stain', 'stained', 'sticky'],
            'none': ['none', 'no damage'],
            'unknown': ['unknown']
        },
        'objectParts': [
            'screen',
            'keyboard',
            'hinge',
            'trackpad',
            'body',
            'lid',
            'base',
            'corner',
            'port',
            'unknown',
        ],
    },
    'package': {
        'issueType': {
            'torn_packaging': ['torn', 'torn open', 'open', 'phati', 'phata', 'opened'],
            'crushed_packaging': ['crushed', 'crush', 'dented', 'dent', 'crease', 'creased'],
            'water_damage': ['water damage', 'wet', 'water damaged', 'liquid damage'],
            'stain': ['stain', 'stained', 'oily mark', 'oily', 'unreadable'],
            'none': ['none', 'no damage'],
            'unknown': ['unknown', 'missing', 'broken']
        },
        'objectParts': [
            'box',
            'side',
            'seal',
            'label',
            'corner',
            'contents',
            'item',
            'unknown',
        ],
    },
}

def main() -> None:
    image_data = build_image_data()
    OUTPUT_PATH.write_text(
        json.dumps(image_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)} with {len(image_data)} users.")


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


@lru_cache(maxsize=1)
def load_user_history() -> dict[str, dict[str, str]]:
    history_path = DATASET_DIR / "user_history.csv"
    if not history_path.exists():
        return {}

    history_rows: dict[str, dict[str, str]] = {}
    with history_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            user_id = (row.get("user_id") or "").strip()
            if user_id:
                history_rows[user_id] = row
    return history_rows


def read_claim_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    csv_paths = []
    if (DATASET_DIR / "claims.csv").exists():
        csv_paths.append(DATASET_DIR / "claims.csv")
    else:
        csv_paths.append(DATASET_DIR / "sample_claims.csv")

    for csv_path in csv_paths:
        if not csv_path.exists():
            continue
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                row["source_csv"] = csv_path.name
                rows.append(row)
    return rows


def resolve_image_paths(image_paths: str) -> list[Path]:
    paths: list[Path] = []
    for raw_path in image_paths.split(";"):
        raw_path = raw_path.strip()
        if not raw_path:
            continue
        path = DATASET_DIR / raw_path
        if path.exists() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            paths.append(path)
            break  # only read the first valid image for each case
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
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def expand_risk_flag_values(value: Any) -> list[str]:
    values: list[str] = []
    for item in normalize_list(value):
        for flag in str(item).split(";"):
            flag = flag.strip().lower()
            if flag:
                values.append(flag)
    return values


def normalize_risk_flags(value: Any) -> list[str]:
    flags = []
    for flag in expand_risk_flag_values(value):
        if flag in RISK_FLAG_SET:
            flags.append(flag)
    return merge_risk_flags(flags)


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
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        if not items or any(item.lower() == "none" for item in items):
            return "none"
        return ";".join(items)
    s = str(value or "none").strip()
    if not s or s.lower() == "none":
        return "none"
    return s


def merge_risk_flags(*flag_groups: Any) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()

    for group in flag_groups:
        for flag in expand_risk_flag_values(group):
            if flag == "none" or flag not in RISK_FLAG_SET or flag in seen:
                continue
            seen.add(flag)
            merged.append(flag)

    if not merged:
        return ["none"]

    merged.sort(key=RISK_FLAG_ORDER.index)
    return merged


def split_history_flags(raw_flags: str) -> list[str]:
    if not raw_flags:
        return []
    return [
        flag.strip().lower()
        for flag in raw_flags.split(";")
        if flag.strip().lower() in RISK_FLAG_SET
    ]


def determine_risk_flags(user_id: str) -> list[str]:
    """Read user_history.csv and return the history-based risk flags for a user."""

    row = load_user_history().get(user_id.strip())
    if not row:
        return ["none"]

    flags = split_history_flags(row.get("history_flags", ""))
    return merge_risk_flags(flags)


def normalize_analysis(payload: dict[str, Any], claim_object: str) -> dict[str, Any]:
    return {
        "evidence_standard_met": normalize_bool(payload.get("evidence_standard_met")),
        "evidence_standard_met_reason": str(payload.get("evidence_standard_met_reason") or "").strip(),
        "issue_type": str(payload.get("issue_type") or "").strip().lower(),
        "object_part": str(payload.get("object_part") or "").strip().lower(),
        "claim_status": normalize_claim_status(payload.get("claim_status")),
        "claim_status_justification": str(payload.get("claim_status_justification") or "").strip(),
        "supporting_image_ids": normalize_supporting_image_ids(payload.get("supporting_image_ids")),
        "valid_image": normalize_bool(payload.get("valid_image")),
        "severity": normalize_severity(payload.get("severity")),
        # Keep metadata and risk flags
        "risk_flags": normalize_risk_flags(payload.get("risk_flags")),
        "image_paths": normalize_list(payload.get("image_paths")),
        "source_csv": normalize_list(payload.get("source_csv")),
        "claim_object": str(payload.get("claim_object") or claim_object),
    }


def analyze_claim_images(
    client: OpenAI, row: dict[str, str], image_paths: list[Path]
) -> dict[str, Any]:
    claim_object = row.get("claim_object", "").strip().lower()
    allowed = dataKeywords.get(claim_object, {})
    allowed_issue_types = list(allowed.get("issueType", {}).keys()) if isinstance(allowed.get("issueType"), dict) else list(allowed.get("issueType", []))
    allowed_object_parts = allowed.get("objectParts", [])

    prompt = {
        "task": "Analyze the submitted claim images and return only valid JSON matching the required schema.",
        "user_id": row.get("user_id", ""),
        "claim_object": claim_object,
        "user_claim": row.get("user_claim", ""),
        "image_ids": [path.stem for path in image_paths],
        "image_paths": [
            path.relative_to(DATASET_DIR).as_posix() for path in image_paths
        ],
        "allowed_issue_type_values": allowed_issue_types,
        "allowed_object_part_values": allowed_object_parts,
        "required_schema": {
            "evidence_standard_met": "boolean (true if the image set is sufficient to evaluate the claim; otherwise false)",
            "evidence_standard_met_reason": "string (short reason for the evidence decision)",
            "issue_type": "string (must be one of the allowed_issue_type_values or unknown)",
            "object_part": "string (must be one of the allowed_object_part_values or unknown)",
            "claim_status": "string (supported | contradicted | not_enough_information)",
            "claim_status_justification": "string (concise image-grounded explanation; mention relevant image IDs when helpful)",
            "supporting_image_ids": "string (image IDs supporting the decision, separated by semicolons; use none if no image is sufficient)",
            "valid_image": "boolean (true if the image set is usable for automated review; otherwise false)",
            "severity": "string (none | low | medium | high | unknown)",
            "risk_flags": RISK_FLAG_ORDER,
        },
        "rules": [
            "Base evidence_standard_met, evidence_standard_met_reason, issue_type, object_part, claim_status, claim_status_justification, supporting_image_ids, valid_image, and severity on the images.",
            "Choose issue_type and object_part from the allowed lists when they fit.",
            "For supporting_image_ids, separate multiple image IDs using semicolons (e.g., img_1;img_2), or use 'none' if no image is sufficient.",
            "YOU MUST output ONLY valid JSON. Do not include any explanation, safety text, markdown enclosing, or extra words. If you cannot comply, output: {'error': 'invalid'}",
        ],
    }

    content: list[dict[str, Any]] = [
        {"type": "text", "text": json.dumps(prompt, ensure_ascii=True)}
    ]
    content.extend(encode_image(path) for path in image_paths)

    completion = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": content}],
        temperature=0,
    )
    text = completion.choices[0].message.content or "{}"
    payload = extract_json(text)
    payload["image_paths"] = [
        path.relative_to(DATASET_DIR).as_posix() for path in image_paths
    ]
    payload["source_csv"] = [row.get("source_csv", "")]
    payload["claim_object"] = claim_object
    analysis = normalize_analysis(payload, claim_object)
    analysis["risk_flags"] = merge_risk_flags(
        analysis.get("risk_flags", []),
        determine_risk_flags(row.get("user_id", "")),
    )
    return analysis


def build_image_data() -> dict[str, dict[str, dict[str, Any]]]:
    client = build_client()
    image_data: dict[str, dict[str, dict[str, Any]]] = {}
    call_count = 0

    for row in read_claim_rows():
        user_id = row.get("user_id", "").strip()
        claim_object = row.get("claim_object", "").strip().lower()
        image_paths = resolve_image_paths(row.get("image_paths", ""))
        if not user_id or not claim_object or not image_paths:
            continue

        if call_count >= 49:
            print("Reached maximum limit of 49 AI calls. Stopping execution.")
            break

        analysis = analyze_claim_images(client, row, image_paths)
        call_count += 1
        user_bucket = image_data.setdefault(user_id, {})
        if claim_object in user_bucket:
            existing = user_bucket[claim_object]
            existing["risk_flags"] = merge_risk_flags(
                existing.get("risk_flags", []),
                analysis.get("risk_flags", []),
            )
            for key in ("image_paths", "source_csv"):
                existing[key] = sorted(set(existing.get(key, []) + analysis.get(key, [])))
            
            existing["evidence_standard_met"] = existing.get("evidence_standard_met", False) or analysis["evidence_standard_met"]
            existing["valid_image"] = existing.get("valid_image", False) or analysis["valid_image"]
            
            existing["evidence_standard_met_reason"] = (existing.get("evidence_standard_met_reason", "") + " | " + analysis["evidence_standard_met_reason"]).strip(" | ")
            existing["claim_status_justification"] = (existing.get("claim_status_justification", "") + " | " + analysis["claim_status_justification"]).strip(" | ")
            
            existing["issue_type"] = analysis["issue_type"] or existing.get("issue_type", "unknown")
            existing["object_part"] = analysis["object_part"] or existing.get("object_part", "unknown")
            
            existing_ids = [x.strip() for x in existing.get("supporting_image_ids", "none").split(";") if x.strip() and x.strip().lower() != "none"]
            new_ids = [x.strip() for x in analysis.get("supporting_image_ids", "none").split(";") if x.strip() and x.strip().lower() != "none"]
            combined_ids = sorted(set(existing_ids + new_ids))
            existing["supporting_image_ids"] = ";".join(combined_ids) if combined_ids else "none"
            
            status_order = ["not_enough_information", "contradicted", "supported"]
            existing["claim_status"] = max(
                existing.get("claim_status", "not_enough_information"),
                analysis["claim_status"],
                key=status_order.index
            )
            
            severities = ["none", "low", "medium", "high", "unknown"]
            existing["severity"] = max(
                existing.get("severity", "unknown"),
                analysis["severity"],
                key=severities.index,
            )
        else:
            user_bucket[claim_object] = analysis

        # Write intermediate data to JSON after each call
        try:
            OUTPUT_PATH.write_text(
                json.dumps(image_data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception as e:
            print(f"Warning: failed to write intermediate image_data to {OUTPUT_PATH.name}: {e}")

    return image_data


if __name__ == "__main__":
    main()
