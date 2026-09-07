# ReplayMark semantic boundary — evidence-semantics closure freeze

**Status:** bounded `q_{C,H}`, compiler-owned evidence semantics, q evidence image,
deterministic support envelope, three-valued adjudication, and theorem-induced
maximal certified reuse `R*` are implemented with independent definition oracles.  
**R* authority:** `replaymark-rstar-maximal-certified-reuse@df1c9a5e66cb1348def885c3710530012230830b`.  
**Current branch scope:** replace production hand-authored `Omega(e)` with a
forward observation-support model whose inverse is compiler-derived and sealed.  
**Still out of scope:** concrete `CompiledContract`, runtime raw-observation
canonicalizer, target-native fallback policy, production predictive-witness
synthesis, compiler-observed full target-semantic digest, runtime E3b gate,
stochastic q compilation, BDD/bitset optimization, and new live experiments.

## 1. Executable semantic chain

The current production chain is:

`ClaimSpec -> q_{C,H} -> CompiledEvidenceSemantics -> q[Omega(e)] -> S-/S+ -> VALID/INVALID/UNRESOLVED -> R*`.

The key change in this branch is that `Omega(e)` is no longer production author
input.

## 2. Target semantics

ReplayMark uses a finite two-phase target model:

```text
decision_state
    -- current_distribution --> (current action, post-decision state)
post-decision state
    -- advance_distribution(future continuation) --> next decision_state
```

Production bounded-q compilation remains deterministic and input-enabled over the
declared continuation alphabet. Stochastic target models remain representable at
the protocol/oracle boundary but are not silently assigned production q semantics.

## 3. Bounded claim-predictive state

Production computes exactly the declared finite horizon:

`q_{C,0}(s) = current claim-projected output`

and for `h >= 1`:

`q_{C,h}(s) = (current output, q_{C,h-1}(next(s,u)) for every admitted u)`.

No hidden `H+1` lookahead is used. The definition oracle independently enumerates
continuation words and projected output-trace laws.

## 4. Evidence semantics: forward relation is authoritative

The authoring boundary is now:

`O(w) = set of canonical retained-evidence tokens possible in modeled world w`.

`ObservationSupportModel.observation_support(w)` supplies `O(w)`.
ReplayMark enumerates every target decision world and computes:

`Omega(e) = { w : e in O(w) }`.

A deterministic observation is a singleton `O(w)`. Partial/noisy/multi-mode
evidence may return several tokens.

Every modeled world must have at least one explicit evidence interpretation.
Uncertainty is represented by more possibilities, not by leaving the world
unmodeled.

## 5. Compiler guarantee versus adapter guarantee

The compiler guarantees **mechanical closure relative to the model**:

- every declared target world is queried;
- every returned `(world, token)` edge is retained;
- the inverse `Omega(e)` is derived rather than hand-authored;
- forward and inverse relations are mutually checked;
- relation and target-domain digests are compiler-derived; and
- repeated reverse-order adapter evaluation must be stable.

The adapter/model author remains responsible for **semantic adequacy to reality**.
For support-sound reuse the safe condition is conservative completeness:

`O_real(w) subseteq O_model(w)`

or equivalently `Omega_real(e) subseteq Omega_model(e)`.

Over-approximation may reduce reuse but does not create a false support
certification. Under-approximation can hide a real counterexample world and is
therefore the dangerous modeling error.

## 6. `EvidenceSpec` is low-level inverse IR

`EvidenceSpec` still represents the canonical finite inverse relation used by
mathematical definition oracles and historical verification fixtures.

Production `compile_evidence_image` no longer accepts a naked `EvidenceSpec`; it
requires a `CompiledEvidenceSemantics` artifact derived from forward semantics.
This removes the manual compatible-world list from the certification path.

Historical inverse fixtures are verification-only. A helper transforms each
expected inverse into a total forward relation, recompiles it, and checks that the
new compiler re-derives the named expected `Omega(e)` sets.

## 7. Evidence image and support envelope

For each token:

`I_{C,h}(e) = q_{C,h}[Omega(e)]`.

The evidence-image artifact is bound to the quotient, claim, compiler-derived
evidence-semantics artifact, relation fingerprint, inverse EvidenceSpec, and q
depth.

Then:

`S_C^-(e) = intersection_{w in Omega(e)} S_C(w)`

`S_C^+(e) = union_{w in Omega(e)} S_C(w)`.

Production verifies current-support constancy inside each deterministic q block;
the raw support oracle bypasses q/evidence artifacts and computes the definition
directly over raw worlds.

## 8. Three-valued adjudication

For recorded claim-projected action `z`:

- `VALID` iff `z in S_C^-(e)`;
- `INVALID` iff `z notin S_C^+(e)`;
- `UNRESOLVED` otherwise.

UNRESOLVED is semantic underdetermination, not a confidence score.

## 9. Maximal certified reuse `R*`

For fixed evidence and support validity:

`R*(e,z) = REUSE iff z in S_C^-(e)`.

Thus:

- `VALID -> REUSE`;
- `INVALID -> DO_NOT_REUSE`;
- `UNRESOLVED -> DO_NOT_REUSE`.

`DO_NOT_REUSE` is not a regeneration command. Fallback selection remains policy.
R* is pointwise maximal among fixed-evidence binary support-sound reuse rules.

## 10. Evidence closure audit examples

A Better Thermostat forward-observation model supplies two evidence modes from
every raw world:

- `hide-motion`: retain presence, night, preset;
- `hide-preset`: retain presence, motion, night.

The compiler derives the N2b hide-motion token to exactly two worlds without a
manual pair list. It also derives the hide-preset token at
presence=true/motion=false/night=false to four worlds, one for every current
preset. This demonstrates the purpose of closure: a minimal separating witness is
not automatically a complete epistemic class.

A deliberate omission trap uses a forward relation in which evidence `e` is
possible in three worlds. A manually written inverse could omit the third world;
production rejects that inverse, derives all three, and preserves the resulting
UNRESOLVED classification.

## 11. Verification independence and TCB

The new evidence-closure oracle does not import the production evidence compiler.
It independently takes the literal inverse of the forward relation. It necessarily
shares the target state domain and observation-support semantics: those are the
intentional semantic TCB for this stage.

Accordingly, future prose should say **algorithmically independent definition
oracle above a shared semantic-contract TCB**, not imply that the source model
itself is independently proven by the oracle.

## 12. Admitted verification

This branch is closed only if:

- all prior q/support/adjudication/R* semantic gates remain green after migration
to compiler-derived evidence;
- all `7^3 = 343` total nonempty relations from three worlds to nonempty subsets
of three tokens invert exactly against an independent oracle;
- every relation edge is verified in both directions;
- Better Thermostat forward evidence derives the expected complete epistemic sets
and preserves downstream semantic outcomes;
- a deliberate manual compatible-world omission is impossible on the production
path;
- conservative observation over-approximation widens `Omega` as intended;
- uncovered worlds, duplicate tokens, mutable/noncanonical return shapes, and
stateful/order-dependent adapters fail closed; and
- production evidence-image compilation rejects raw `EvidenceSpec` input.

## 13. Next boundary

Do not instantiate the final `CompiledContract` yet.

Remaining pre-packaging hardening is intentionally separate:

1. split predictive continuation witnesses from reuse counterexample worlds and
implement production predictive-witness synthesis;
2. derive a compiler-observed digest of full target semantics rather than relying
only on a provider fingerprint; and
3. re-freeze the `CompiledContract` API around the semantics actually established.

Runtime raw-observation tokenization and live E3b intervention come after that.
