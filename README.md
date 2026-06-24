# Damage Claim Agent
## Video Demo: https://youtu.be/oViHxd2KnC8
## Description:

### High-level overview:
   - Damage Claim Agent is a service that automates intake and triage of property damage claims. It accepts claim inputs (images, forms, metadata), validates and extracts key information, classifies severity, and routes cases to automated workflows or human reviewers. Outputs structured claim records and processing status so downstream systems can handle payouts, repairs, or investigations. Built for teams that need to scale claim handling, speed decisions, and keep auditable processing logs.

### Pipeline overview:
   - intake
   - preprocess
   - analyze via LLM
   - normalize/enrich
   - persist outputs

### High-level pipeline flow:

   - Intake: dataset/claims.csv or dataset/sample_claims.csv contains rows. Each row: user_id, image_paths (semicolon-separated relative paths under dataset/images), user_claim (text), claim_object (car/laptop/package).
   - Preprocess: main.py and llm_client.read_claim_rows load CSV rows. resolve_image_paths verifies image files exist and filters allowed extensions.
   - Analyze: llm_client.build_prompt assembles JSON prompt with claim text, image IDs, evidence rules, allowed enums, user history context. encode_image embeds images as base64 data parts. analyze_claim_images calls OpenAI/OpenRouter chat.completions with model set by OPENROUTER_MODEL and API key from env. LLM must return strict JSON; extract_json enforces and parses it.
   - Normalize/enrich: analysis fields normalized (booleans, severity, risk_flags, enums, supporting_image_ids). determine_risk_flags merges user history risk context. enrich_analysis combines original row + normalized analysis into final record.
   - Persist: build_image_data writes dataset/imageData.json mapping stable row_key -> enriched analysis. build_prediction_rows returns list of CSV-ready rows matching OUTPUT_HEADERS. main.py writes output.csv at repo root (and prints path).
   - Consumers: output.csv and dataset/output.csv provide tabular exports for downstream systems. imageData.json provides raw analysis structure keyed by row fingerprint.

### File-by-file (what each file is for)

   ##### code/main.py
   - Orchestrator script. Entrypoint for CLI run. Calls build_prediction_rows(DEFAULT_CLAIMS_PATH) then writes output CSV. Minimal logic: write_output_csv uses OUTPUT_HEADERS to guarantee column order. One-shot script for creating predictions CSV from claims dataset.
   - code/llm_client.py
   - Core runtime logic + LLM integration. Responsibilities: - Constants & config: REPO_ROOT, DATASET_DIR, IMAGE_DATA_PATH, DEFAULT_CLAIMS_PATH, MODEL env fallback.
   - Allowed enums: RISK_FLAG_ORDER, ISSUE_TYPES, OBJECT_PARTS for claim_object types. These drive validation and ordering in outputs.
   - Keyword maps (CLAIM_KEYWORDS) used for prompt constraints and allowed values.
   - Client builder: build_client() reads OPENROUTER_API_KEY or OPENAI_API_KEY and constructs OpenAI client wrapper (base_url from OPENROUTER_BASE_URL). Raises if no key.
   - CSV helpers: read_csv_rows, read_claim_rows (falls back to sample file if claims.csv missing).
   - Caching loaders: load_user_history(), load_evidence_requirements(). These read CSVs once and cache results via lru_cache.
   - row_key(): deterministic SHA1 fingerprint for each row based on user_id|image_paths|user_claim|claim_object. Purpose: stable key for imageData.json and dedupe between build_image_data and build_prediction_rows.
   - Image handling: resolve_image_paths transforms semicolon list into Path objects under dataset dir; encode_image converts images to PNG via Pillow (if present) or reads raw bytes and base64 encodes; returns small structured object compatible with the LLM content format used by chat API.
   - Prompt builder: build_prompt(row, image_paths) constructs JSON payload including: - task description, user_id, claim_object, user_claim, image_ids, image_paths (relative), history_flags, allowed enum values, evidence_requirements filtered by claim_object, required_schema, and rules (use images as primary truth, return only JSON).
   - LLM call & JSON extraction: analyze_claim_images sends messages = [{"role":"user","content": content}] where content is list with text JSON prompt then encoded images. Temperature set to 0 for deterministic behavior. Response parsed with extract_json(text) that strips fences and finds first {...} JSON object. If missing, raises.
   - Normalizers & merge helpers: normalize_bool, normalize_severity, normalize_claim_status, normalize_risk_flags (orders by RISK_FLAG_ORDER and collapses duplicates), normalize_object_part (ensures part exists in OBJECT_PARTS for claim_object), normalize_issue_type, expand_semicolon_values, merge_text, merge_ordered_unique.
   - Enrichment: enrich_analysis(row, analysis) converts booleans to "true"/"false" lower-case strings, composes risk_flags as semicolon-separated string, returns a flat dict matching OUTPUT_HEADERS.
   - Build phases: build_image_data iterates rows, resolves images, calls analyze_claim_images, writes dataset/imageData.json mapping row_key->enriched analysis. build_prediction_rows uses image_data mapping to produce final list of rows for CSV output; if analysis missing, populates conservative defaults (not_enough_information, unknowns, valid_image False).
   - Utilities: extract_json robustly parses common LLM formatting variants (code fences, "json" labels) â important because model may output extra text.
   - Key outputs: IMAGE_DATA_PATH JSON and final CSV rows.
   #### code/claim_extractor.py
   - Offline utility for deriving claimData.json by scanning claims.csv against a built-in dictionary of keywords and objectParts. Responsibilities: - Defines claimData mapping (car/laptop/package) similar to CLAIM_KEYWORDS in llm_client.
   - Reads dataset/claims.csv, collects per-user claim text and object type.
   - find_present_keywords(text, keywords) returns matched set of issueType keys or objectParts present in user_claim using regex word-boundary matching; used to populate claimDataByUser[user_id].
   - Writes dataset/claimData.json used for quick inspection or indexing outside LLM pipeline.
   - Purpose: precompute which issueType/objectPart keywords are present in user claims for analytics/labeling.
   #### dataset/ directory and files
   - claims.csv: primary input CSV. Expected columns at minimum: user_id, image_paths, user_claim, claim_object. Each row one claim submission. image_paths are relative to dataset/images and use semicolon separators for multiple images.
   - sample_claims.csv: fallback small sample used when claims.csv absent.
   - user_history.csv: per-user historic metadata including history_flags column. determine_risk_flags reads this to add contextual risk flags to prompt and final risk_flags output.
   - evidence_requirements.csv: list of evidence rules filtered by claim_object; loaded into prompt required_schema/evidence_requirements to guide LLM decisions.
   - claimData.json: authored by claim_extractor.py; per-user present keywords for issueType/objectParts. Useful for offline analysis and allowed-values guidance.
   - imageData.json: written by llm_client.build_image_data. Primary machine-readable output: mapping row_key -> enriched analysis (fields same as OUTPUT_HEADERS but types preserved). Useful for debug, audits, and replays.
   - output.csv & dataset/output.csv: tabular CSV exports matching OUTPUT_HEADERS for downstream ingestion by payout/repair/investigation systems.
   - dataset/images/*: sample and test image folders. Images referenced by claims.csv. encode_image reads these to embed for LLM. Paths in prompt are relative POSIX-style (DATASET_DIR relative).
   - misc
   - .vscode/extensions.json: editor recommendations, irrelevant to runtime.
   - code/pycache/*: compiled bytecode, ignore.

##### Key invariants, failure modes, and reading tips

   - LLM must return strict JSON object. extract_json enforces; if LLM returns prose before/after JSON, code strips non-JSON but will error if no braces found.
   - API keys: set OPENROUTER_API_KEY or OPENAI_API_KEY env var. MODEL can be overridden with OPENROUTER_MODEL.
   - Images: Pillow optional. If Pillow absent, code guesses mimetype and base64-encodes raw bytes. Converted PNG when Pillow present.
   - row_key ensures stable mapping between build_image_data and build_prediction_rows; duplicates keyed by identical raw fields collapse.
   - Risk flags ordering enforced by RISK_FLAG_ORDER so outputs consistent for downstream ranking.
   - OUTPUT_HEADERS defines final CSV column order; enrich_analysis ensures CSV-ready string types.