# Runtime Contract Identity Cache Optimization — Frozen Increment

Status: **non-semantic runtime optimization only**.

The preceding Runtime Cost Characterization showed repeated `ExplicitCompiledContract.fingerprint()` computation dominating the per-task shadow cost. The compiled contract is already immutable, provider-free, and content-addressed after packaging, but the bridge recomputed the same canonical contract bytes and SHA-256 twice for every certificate.

This increment removes only that repeated identity work.

## Unchanged science

The following do not change: `ExplicitCompiledContract`, claim/evidence/support semantics, adjudication, R*, observation realization, historical-action realization, same-task correlation, E3b certificate schemas, bridge semantic rule record/digest, public `certify_e3b_shadow_reuse(contract, pair)` API, R1 execution, and fallback/regeneration policy.

For the same contract and correlated pair, optimized certificate canonical bytes must be exactly identical to the pre-optimization bridge output.

## Cache design

`verified_runtime_contract_identity(contract)` owns the optimization.

A hit requires both the same integer `id(contract)` and `entry.contract is contract`. Each cache entry holds a strong reference to the contract, preventing Python object-id reuse while the entry is live. The cache is an LRU bounded to 16 contracts, so retention cannot grow without bound.

On a cold miss, under a re-entrant lock, the cache derives `contract.fingerprint()` and `contract.claim_fingerprint` directly from the exact `ExplicitCompiledContract`. No caller can inject an identity into the bridge. Keeping the lock across cold computation intentionally ensures concurrent first use performs one fingerprint computation rather than racing several equivalent computations.

The optimization consumes the already-gated immutability of the packaged contract; it does not introduce a new mutability assumption. Byte-identical but independently instantiated contracts are not cache hits and receive separate cold verification.

## Promotion requirements

Promotion requires: previous bridge semantic digest unchanged; exact legacy-vs-optimized canonical certificate bytes for VALID/INVALID/UNRESOLVED; 32 sequential bridge calls on one contract with exactly one underlying contract fingerprint; 32 concurrent cold-start callers with exactly one fingerprint; distinct byte-identical objects receiving separate cold verification; bounded eviction; ordinary compiled-contract mutation rejected; all prior semantic/runtime gates re-passing; real-Mosquitto R1 non-interference re-passing; Integrated Frozen Runtime Conformance re-passing; and exact legacy-vs-optimized bytes across a 128-case live-negative plus definition-derived-positive corpus.

There is deliberately no speed threshold in the correctness promotion rule.

## Paired A/B measurement

A real Mosquitto 2.1.2 run acquires 64 live delayed-feedback negative cases. The Harness is closed before timing. A definition-valid positive case is derived from each live record exactly as in the preceding cost study and is explicitly not presented as a second live empirical outcome.

The benchmark compares in one process, on one contract and one raw corpus, with deterministic randomized interleaving:

1. the exact pre-optimization orchestration that recomputes the contract fingerprint twice; and
2. the optimized bridge using the verified identity cache.

Cold verified-identity acquisition and hot cache lookup are also reported separately.

## Still excluded

Duplicate-adjudication optimization, bitset/Roaring/BDD changes, execution policy, fallback/regeneration, selective-reuse intervention, and claims that hosted-runner timings generalize to all hardware remain outside this increment. Any next optimization must be justified by the post-optimization profile.
