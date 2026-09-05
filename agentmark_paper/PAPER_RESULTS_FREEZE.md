# AgentMark Paper-Results Freeze

Status: **FROZEN_CANONICAL**

This directory is the canonical interface between sealed experiments and manuscript prose.

## Freeze contract

1. `evidence/*/primary.json` contains exact copies of canonical aggregate JSONs from successful GitHub Actions artifacts.
2. Each `PROVENANCE.json` pins workflow run, execution commit, artifact ID, archive digest, source schema, and primary-file digest; those identities are independently hard-locked in `paper_results_lib.py`.
3. `scripts/extract_paper_results.py` is the only supported path from evidence to `PAPER_RESULTS_MANIFEST.json`; provenance cannot be repointed merely by rehashing a replacement capsule.
4. `scripts/validate_paper_results.py` fails closed on provenance drift, content-hash drift, schema drift, result drift, exclusion drift, or exact/measured type confusion.
5. `scripts/generate_paper_views.py` generates manuscript-facing tables, CSV, figure data, and summary from the manifest.
6. N1 runner timings remain separate; no canonical cross-runner average is admitted.
7. E3b/E3c workload ratios are derived from exact integer work counts and canonically represented as **3/2**, never imported from a timing statistic or floating-point narrative.
8. N2b v1 run `33972326066` remains explicitly noncanonical. E3b safety-boundary evidence remains non-headline.
9. The empirical stop rule is active.

## Cryptographic lock

Evidence tree SHA-256: `d95859dbfb6a415f354b96e51981e3621aae758f2de139383f1512c8d14db210`  
Canonical provenance-lock SHA-256: `4e9381bc21e0b6e6a225bd0ede2f69b7b05178aad49a686fd9ed5c8b0b0049f0`  
Manifest SHA-256: `47d3f6cb356c6f7b33d74daf13414024bdf90c913c170e21ea67ed9ea4412fb6`

The Git commit containing this freeze is an additional content-addressed audit boundary. Narrative text is downstream of this layer, never an authority over it.
