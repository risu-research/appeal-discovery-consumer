# ReplayMark semantic boundary — q evidence-image freeze

**Status:** bounded `q_{C,H}` compilation is frozen and the next evidence-image arrow is implemented.  
**Original seed authority:** `replaymark-compiler-contract-seed@6da24cce48d1c2f6fe4bfabf4e01047e79b7e6eb`.  
**Bounded-q authority:** `replaymark-bounded-q-compiler@b2b357ce009d26e56e4422a3d61aade57ca6064a`.  
**Scientific ancestry:** the exact `q_{C,H}` research gate remains frozen prior authority; this package does not reinterpret its outcomes.  
**Current scope:** public semantic types, two-phase target semantics, bounded deterministic `q_{C,H}` compilation, independent q definition oracle, and the extensional image `q_{C,H}[Omega(e)]` of retained evidence.  
**Still out of scope:** `S^- / S^+` support envelopes, three-valued adjudication, `CompiledContract` realization, maximal reuse guards, runtime gate insertion, replay/regeneration policy integration, BDD/bitset optimization, stochastic q compilation, and new live experiments.

## 1. Public boundary remains deliberately small

The package root exports exactly six semantic types:

1. `ClaimSpec`
2. `TargetModel`
3. `EvidenceSpec`
4. `ProjectedAction`
5. `CompiledContract`
6. `Verdict`

Compiler stages, storage backends, runtime gates, substrate adapters, and verification
oracles remain explicit submodules rather than public semantic types.

The Replay-Sufficiency Factorization remains:

`claim -> projected actions -> q_{C,H} -> evidence image -> support envelope -> maximal certified reuse`.

The present branch closes only through **evidence image**.

## 2. Claim and action boundaries

`ClaimSpec` is normative. It fixes stable claim identity, exact consequential action
dimensions, a non-negative claim-bound consequence horizon, and the consequence
endpoint. The target cannot silently refine or weaken it. Projection onto a
dimension not established by an adapter fails closed.

`ProjectedAction` remains a substrate-neutral immutable tuple of canonical named
scalar dimensions. Missing coordinates are never guessed. In particular, the
legacy AgentMark adapter knows target class but does not invent exact target
identity.

## 3. Two-phase `TargetModel`

ReplayMark's predictive object is a target decision condition/history immediately
before the current controller decision:

```text
decision_state
    -- current_distribution --> (current action, post-decision state)
post-decision state
    -- advance_distribution(future continuation) --> next decision_state
```

The separation is required because E3b includes current feedback in the current
decision condition, while the Better Thermostat state already contains the
current feedback variables. A future continuation must never be consumed as if
it were current evidence.

The protocol exposes exact rational mass over those two phases. Compiler v1
accepts only deterministic point masses and fails closed on stochastic branching.

## 4. `q_{C,H}` boundary

The production compiler applies exactly the declared claim projection and computes:

`q_{C,0}(s) = current claim-projected output`

and, for `h >= 1`,

`q_{C,h}(s) = (current output, q_{C,h-1}(next(s,u)) for every admitted continuation u)`.

Only layers `0..H` are computed. No hidden `H+1` lookahead is allowed merely to
claim convergence. A fixed point is reported only when equality of adjacent
already-computed partition relations is observed.

`agentmark.minimize.quotient()` remains algorithmic precedent only. It is not
renamed or wrapped as ReplayMark `q_{C,H}`.

## 5. Independent q definition oracle

The production compiler and the definition oracle remain separate.

- `replaymark/q_compiler.py`: bounded Moore-style refinement.
- `replaymark_oracle/definition_q_oracle.py`: direct enumeration of continuation
  words and exact projected output-trace laws.

The oracle does not import the production compiler. Production code does not
import the oracle. The exhaustive three-state differential gate remains the
implementation-fidelity authority for the bounded q stage.

## 6. `EvidenceSpec` means `Omega(e)`

Each evidence token denotes exactly the finite nonempty set `Omega(e)` of target
decision states/histories still compatible with retained evidence.

Tokens may overlap. Unknown observations fail closed. Evidence may be coarser
than raw target state and is not required to identify a unique decision history.

This extensional representation is intentionally small. A future symbolic
evidence backend may implement the same set semantics without changing the
public contract.

## 7. New stage: evidence image through `q_{C,H}`

For claim `C`, layer `h`, and evidence token `e`, define

`I_{C,h}(e) := q_{C,h}[Omega(e)] = { q_{C,h}(w) : w in Omega(e) }`.

`replaymark/evidence_image.py` implements exactly this set image over an
already-compiled `BoundedQuotient`.

The artifact records:

- the quotient fingerprint;
- the claim fingerprint;
- the evidence fingerprint;
- the exact already-computed q depth used; and
- for each evidence token, the compatible raw decision states and canonical q
  blocks touched by those states.

Evidence outside the compiled target domain fails closed. A request for a
deeper, uncompiled q layer fails rather than triggering hidden refinement.

No support, verdict, or reuse semantics are attached to the image.

## 8. Independent evidence-image oracle

`replaymark_oracle/evidence_image_oracle.py` is definition-level verification
code. It does not import `replaymark.evidence_image` or `replaymark.q_compiler`.

It obtains the q relation from the existing continuation-word/output-trace
definition oracle and then computes the literal set image of `Omega(e)`.
Verification compares complete semantic block-member sets rather than production
block IDs.

This prevents a block-label convention from masquerading as semantic agreement.

## 9. Admitted verification for this branch

The evidence-image gate requires:

- production-vs-definition agreement for Better Thermostat evidence fixtures at
  depths 0, 1, and 2;
- exact N2b evidence-image refinement `1 -> 2 -> 2`;
- compression of three overwritten non-target preset identities to one stable
  predictive class;
- restoration of two classes when an at-target world is included;
- subset monotonicity under stronger extensional evidence;
- canonical invariance to evidence token/state input order;
- fail-closed behavior for target states outside the compiled domain;
- no hidden deeper q layer; and
- exhaustive H=0 set-image agreement over all 27 assignments of three output
  labels to three states and all seven nonempty evidence subsets, exercising all
  five set partitions of a three-element domain.

The earlier q compiler/oracle gate must also remain green.

## 10. Next boundary, deliberately not crossed here

Only after this evidence-image stage is frozen may the next branch implement:

`evidence image / target projected supports -> S_C^-(e), S_C^+(e)`.

That support-envelope stage must have its own independent definition oracle.

`VALID / INVALID / UNRESOLVED`, `CompiledContract`, and the maximally permissive
reuse guard remain later increments. No runtime E3b intervention is admitted
before those semantic layers are independently closed.
