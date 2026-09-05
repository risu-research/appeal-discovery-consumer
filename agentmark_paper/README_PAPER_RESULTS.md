# Canonical paper-results layer

This directory turns sealed AgentMark experimental artifacts into a deterministic,
fail-closed interface for manuscript numbers.

Canonical flow:

`evidence capsules -> extract_paper_results.py -> PAPER_RESULTS_MANIFEST.json -> generated paper views`

Rules:

- Never transcribe headline numbers from prose, chat, or memory.
- Canonical run/artifact identities are hard-locked in `paper_results_lib.py`; self-consistent provenance repointing fails validation.
- Exact structural metrics and measured timing metrics are different types.
- E3b/E3c workload ratios are derived from integer native-work counts.
- N1 runner timings remain separate.
- N2b v1 is noncanonical.
- Generic empirical expansion is stopped unless adversarial paper review exposes a specific evidence gap.

Run:

```bash
python3 agentmark_paper/scripts/validate_paper_results.py
python3 agentmark_paper/scripts/extract_paper_results.py --check
python3 agentmark_paper/scripts/generate_paper_views.py --check
python3 agentmark_paper/scripts/independent_paper_audit.py
python3 -m unittest discover -s agentmark_paper/tests -p 'test_*.py' -v
```
