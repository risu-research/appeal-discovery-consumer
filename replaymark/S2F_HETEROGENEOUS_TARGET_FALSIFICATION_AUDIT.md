# Gate S2-F — Heterogeneous-Target Falsification Audit

Status: **FROZEN POST-RESULT ADVERSARIAL AUDIT.**

S2-F does not run the target again. It attacks the immutable first-complete P6 artifact from workflow run `34168034341`, artifact `10034798750`, ZIP SHA-256 `1319c41908d511ca9e8976973801350aab593199038b82752d8e4e7c78d0ecdb`.

The audit is intentionally implemented as a second literal evaluator using only the Python standard library. It imports neither ReplayMark production code nor the original independent oracle.

## Main attacks

1. Reconstruct the frozen policy schedule independently.
2. Reconstruct the hidden target-class schedule independently.
3. Re-derive semantic safety directly from raw observation timestamps/events and exact historical ACT2 bytes.
4. Infer actual execution from the recording-client call multiset instead of trusting `row.executed`.
5. Re-check B-side effects, phase ordering, same-task binding, and historical-action invariance.
6. Scan the entire live report for hidden `REFERENCE` / `SHIFTED` labels or the target-class seed.
7. Compare all recomputed counts to the immutable P6 result seal.

## Strong class-label falsification

P6 deliberately did not treat hidden class as semantic truth. The first-complete result contained 11 oracle-unsafe `REFERENCE` tasks. Four of those were assigned to ReplayMark.

Therefore, a hidden-class-only rule:

```text
REFERENCE -> admit
SHIFTED   -> block
```

would make four unsafe executions in the ReplayMark arm. S2-F requires the literal auditor to reconstruct those reference-but-unsafe cases directly from raw evidence and confirm that ReplayMark blocked all of them.

This distinguishes semantic evidence selection from merely following the target-class partition.

## No repair surface

- no target rerun;
- no new delay or deadline;
- no task deletion;
- no alternate favorable artifact;
- no fallback or regeneration;
- no replacement of the first-complete P6 authority.

If this audit fails, P6 remains the immutable first-complete result but the stronger interpretation is not promoted until the discrepancy is explained.
