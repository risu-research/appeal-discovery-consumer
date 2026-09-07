# Post-Optimization Residual Cost Profile — Frozen Measurement Increment

## Scientific question

After verified immutable compiled-contract identity reuse reduced the E3b runtime
certificate-object path to roughly 0.45 ms/task, what actually dominates the
remaining cost?

This increment is measurement-only. It does **not** optimize, alter semantics,
change certificate schemas, change execution, or introduce selective reuse.

Parent authority:

`5d9bbdc87bf926359f83457a0c8057676a4e5b65`

## Why a second profile is required

The previous cost structure is no longer authoritative after the contract
fingerprint bottleneck was removed. Optimizing from the old profile would be
post-hoc intuition rather than measurement.

A simple collection of independent microbenchmarks is also insufficient because
nested production calls overlap. In particular, the frozen E3b bridge performs:

1. one direct `ExplicitCompiledContract.adjudicate(...)`;
2. one `ExplicitCompiledContract.certify_reuse(...)`; and
3. `certify_reuse(...)` itself performs a second adjudication before R*.

Therefore this profile uses two complementary views.

## View A — exact uninstrumented production path

The live Mosquitto corpus is materialized first and the network harness is closed
before timing. The exact optimized path is then benchmarked without tracing:

`raw observation + raw action -> correlate_e3b_runtime_pair -> certify_e3b_shadow_reuse`

The same process, same immutable contract, same 64 live negative cases, and 64
definition-derived positive cases are used. Stage order is deterministically
randomized and GC is disabled inside hot timing loops.

This view is the authoritative latency measurement.

## View B — call-traced additive decomposition

A measurement-only tracer temporarily wraps the exact production call boundaries
without replacing their semantics. It separates the optimized object path into:

- observation realization
- historical-action realization
- correlation composition remainder
- hot verified contract-identity lookup
- primary adjudication
- nested adjudication inside `certify_reuse`
- R* plus `certify_reuse` orchestration remainder
- `RuntimeReuseCertificate` construction/validation
- E3b wrapper certificate construction/validation
- bridge orchestration remainder
- outer pipeline orchestration remainder

For every traced invocation, these exclusive phases must add back to the traced
full pipeline exactly. Negative exclusive durations are forbidden.

Tracing overhead is intentionally **not hidden**. The profile reports traced vs
uninstrumented p50 inflation, so traced numbers are used for structural
attribution and phase ranking rather than substituted for production latency.

## Triangulation

Independent uninstrumented microbenchmarks cross-check the traced ranking,
including:

- correlation total
- observation/action realization
- observation/action raw parsing
- realized-value fingerprinting
- hot identity lookup
- adjudication
- `certify_reuse` total
- R* from a precomputed adjudication
- both certificate constructors

Canonical certificate serialization and certificate fingerprinting are also
measured, but explicitly labeled as **outside the ~0.45 ms certificate-object
path**. They must not be blamed for object-path latency.

## Promotion criteria

PASS requires only measurement integrity:

- exact parent authority and untouched production blobs
- Mosquitto 2.1.2
- 64 live negative + 64 definition-derived positive cases
- certificate semantic identity stable before/after profiling
- exact traced additive conservation
- no negative exclusive phase
- complete percentile/sample accounting
- bounded verified-identity cache
- prior semantic/runtime/noninterference gates remain PASS

There is deliberately no fixed latency threshold and no requirement that any
particular phase be the bottleneck.

## Frozen boundary after this increment

Still not implemented:

- execution policy
- selective-reuse intervention
- fallback/regeneration
- any new runtime optimization

The next optimization may be selected only from the sealed residual profile.
