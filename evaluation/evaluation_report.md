# Operational Analysis

## Pipeline

- One model call per claim row.
- `dataset/sample_claims.csv` is used for development/evaluation.
- `dataset/claims.csv` is used for final predictions.
- `code/main.py` writes the submission file to both `output.csv` in the repo root and `dataset/output.csv` for convenience.

## Dataset Size

- Sample rows: 20
- Test rows: 44
- Total rows processed across sample + test: 64
- Sample images referenced: 29
- Test images referenced: 82
- Total referenced images: 111

## Model Calls

- Sample processing: approximately 20 model calls
- Test processing: approximately 44 model calls
- Total: approximately 64 model calls

## Token Usage Estimate

Assumption: each row produces one vision call with a long structured prompt, image metadata, and a short JSON response.

- Input tokens per row: roughly 1,000 to 1,500
- Output tokens per row: roughly 120 to 180
- Full test set input tokens: roughly 44,000 to 66,000
- Full test set output tokens: roughly 5,280 to 7,920
- Sample + test input tokens: roughly 64,000 to 96,000
- Sample + test output tokens: roughly 7,680 to 11,520

## Cost Estimate

Assumption: nex-agi/nex-n2-pro through OpenRouter, which is entirely free

- Full test set cost: free!
- Sample + test cost: free!

## Latency / Runtime

- Expected serial runtime for the test set: roughly 2 to 6 minutes
- Expected serial runtime for sample + test: roughly 3 to 10 minutes

These ranges assume a few seconds per multimodal request plus occasional retries or network overhead.

## TPM / RPM Considerations

- The pipeline is intentionally simple and serial, so RPM is low and predictable.
- Image uploads dominate request size, so batching should be used cautiously.
- If rate limits become an issue, the natural improvements are:
  - cache repeated row signatures
  - batch by object type
  - retry transient failures with backoff
  - reuse the generated `imageData.json` during local development

## Notes

- User history contributes risk context through `risk_flags` and justifications, but it does not override clear visual evidence.
- The evaluator-facing submission artifact is CSV, not JSON.
