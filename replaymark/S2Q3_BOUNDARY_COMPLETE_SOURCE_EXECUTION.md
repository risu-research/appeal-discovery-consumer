# Gate S2-Q3 — Boundary-Complete Source Screening, Holdout, and D* Seal

Q3 is the first execution of the frozen P5 protocol. It reuses the exact Q2 source-only runner blob; no new traffic generator or observation implementation is introduced.

The screening stage runs all three inherited source loads `{16,8,4}` under the same three-round cyclic order. The independent Q3 verifier ignores the old `p99 <= 80 ms` slack as a promotion rule and qualifies a candidate only if all expected source observations are structurally valid, complete by timeout, and visible by the inherited 100-ms evidence boundary with no exclusions. All latency percentiles remain sealed as descriptive measurements.

If screening selects W*, three fresh holdout replicates run using the exact machine-generated selection seal. The holdout applies the same boundary-completeness requirement. If it passes, D* is computed exactly once from the 576 fresh holdout completion offsets using the frozen formula. If either screening or holdout fails, target execution remains forbidden and the first complete Q3 result is preserved as failure.

Q3 does not execute the shifted target, construct ACT2, alter ReplayMark semantics, add fallback/regeneration, or modify the source runner.
