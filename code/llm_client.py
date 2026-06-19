import base64
import csv
import io
import json
import mimetypes
import os
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
MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")


dataKeywords = {
    "car": {
        "issueType": [
            "damaged",
            "damage",
            "broken",
            "broke",
            "cracked",
            "crack",
            "crushed",
            "dented",
            "dent",
            "scratched",
            "scratch",
            "shattered",
            "missing",
            "broken off",
            "hail dents",
            "water damage",
        ],
        "objectParts": [
            "bumper",
            "front bumper",
            "rear bumper",
            "headlight",
            "taillight",
            "windshield",
            "side mirror",
            "door",
            "hood",
            "car body",
            "body panel",
            "mirror",
            "glass",
        ],
    },
    "laptop": {
        "issueType": [
            "cracked",
            "crack",
            "broken",
            "broke",
            "missing",
            "damaged",
            "damage",
            "liquid damage",
            "stained",
            "stain",
            "came off",
            "keys missing",
        ],
        "objectParts": [
            "screen",
            "keyboard",
            "key",
            "keycap",
            "hinge",
            "trackpad",
            "body",
            "lid",
            "outer body",
            "corner",
            "palm-rest",
            "palm rest",
        ],
    },
    "package": {
        "issueType": [
            "crushed",
            "crush",
            "torn",
            "torn open",
            "open",
            "wet",
            "water damaged",
            "water damage",
            "damaged",
            "damage",
            "stain",
            "oily mark",
            "unreadable",
            "missing",
            "broken",
        ],
        "objectParts": [
            "package",
            "box",
            "delivery box",
            "cardboard box",
            "seal",
            "label",
            "corner",
            "contents",
            "item inside",
            "item",
            "wrapping",
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


def read_claim_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for csv_path in (DATASET_DIR / "sample_claims.csv", DATASET_DIR / "claims.csv"):
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


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


def normalize_severity(value: Any) -> str:
    severity = str(value or "none").strip().lower()
    return severity if severity in {"none", "low", "medium", "high"} else "none"


def normalize_analysis(payload: dict[str, Any], claim_object: str) -> dict[str, Any]:
    return {
        "issueType": normalize_list(payload.get("issueType")),
        "objectParts": normalize_list(payload.get("objectParts")),
        "risk_flags": normalize_list(payload.get("risk_flags")),
        "valid_image": normalize_bool(payload.get("valid_image")),
        "severity": normalize_severity(payload.get("severity")),
        "damage_visible": normalize_bool(payload.get("damage_visible")),
        "supporting_image_ids": normalize_list(payload.get("supporting_image_ids")),
        "image_paths": normalize_list(payload.get("image_paths")),
        "source_csv": normalize_list(payload.get("source_csv")),
        "claim_object": str(payload.get("claim_object") or claim_object),
    }


def analyze_claim_images(
    client: OpenAI, row: dict[str, str], image_paths: list[Path]
) -> dict[str, Any]:
    claim_object = row.get("claim_object", "").strip().lower()
    allowed = dataKeywords.get(claim_object, {})
    prompt = {
        "task": "Analyze the submitted claim images and return only valid JSON.",
        "user_id": row.get("user_id", ""),
        "claim_object": claim_object,
        "user_claim": row.get("user_claim", ""),
        "image_ids": [path.stem for path in image_paths],
        "image_paths": [
            path.relative_to(DATASET_DIR).as_posix() for path in image_paths
        ],
        "allowed_issueType_values": allowed.get("issueType", []),
        "allowed_objectParts_values": allowed.get("objectParts", []),
        "required_schema": {
            "issueType": ["string"],
            "objectParts": ["string"],
            "risk_flags": ["string"],
            "valid_image": "boolean",
            "severity": "none | low | medium | high",
            "damage_visible": "boolean",
            "supporting_image_ids": ["string"],
        },
        "rules": [
            "Base issueType, objectParts, valid_image, severity, and damage_visible on the images.",
            "Use risk_flags for concerns such as unrelated_image, low_quality, mismatch, missing_required_view, duplicate_or_reused, or none.",
            "Prefer issueType and objectParts values from the allowed lists when they fit.",
            "Set valid_image false if the image set is unreadable, unrelated, missing, or cannot verify the claim object.",
            "Set severity to none only when no damage is visible.",
            "YOU MUST output ONLY valid JSON. Do not include any explanation, safety text, or extra words. If you cannot comply, output: {'error': 'invalid'}",
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
    return normalize_analysis(payload, claim_object)


def build_image_data() -> dict[str, dict[str, dict[str, Any]]]:
    client = build_client()
    image_data: dict[str, dict[str, dict[str, Any]]] = {}

    for row in read_claim_rows():
        user_id = row.get("user_id", "").strip()
        claim_object = row.get("claim_object", "").strip().lower()
        image_paths = resolve_image_paths(row.get("image_paths", ""))
        if not user_id or not claim_object or not image_paths:
            continue

        analysis = analyze_claim_images(client, row, image_paths)
        user_bucket = image_data.setdefault(user_id, {})
        if claim_object in user_bucket:
            existing = user_bucket[claim_object]
            for key in ("issueType", "objectParts", "risk_flags", "supporting_image_ids", "image_paths", "source_csv"):
                existing[key] = sorted(set(existing.get(key, []) + analysis.get(key, [])))
            existing["valid_image"] = existing.get("valid_image", False) or analysis["valid_image"]
            existing["damage_visible"] = (
                existing.get("damage_visible", False) or analysis["damage_visible"]
            )
            severities = ["none", "low", "medium", "high"]
            existing["severity"] = max(
                existing.get("severity", "none"),
                analysis["severity"],
                key=severities.index,
            )
        else:
            user_bucket[claim_object] = analysis

    return image_data


if __name__ == "__main__":
    main()
