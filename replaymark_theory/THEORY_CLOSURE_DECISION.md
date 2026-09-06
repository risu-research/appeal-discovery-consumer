# ReplayMark theory closure decision

Status: **FROZEN CANDIDATE FOR FINAL MANUSCRIPT INTEGRATION**

## Accepted theory package

The preferred theory package is now:

1. **Evidence-conditioned support envelope**
   - `S_C^-(e)` = intersection of projected supports over all admitted target worlds compatible with current evidence.
   - `S_C^+(e)` = union of those supports.
   - exact three-way adjudication: certified valid / certified invalid / unresolved.
   - evidence suffices for all actions iff `S_C^-(e)=S_C^+(e)`.
   - stronger evidence monotonically shrinks the unresolved band.

2. **Constructive corollary R***
   - reuse iff the recorded projected action lies in `S_C^-(e)`;
   - this reuse set is maximally permissive among support-sound policies that see only current evidence;
   - outside `S_C^+`, regeneration is necessary if execution is to continue with a target-supported action;
   - inside `S_C^+ \ S_C^-`, stronger evidence, regeneration, or unresolved are all admissible system choices; no cost-optimality claim is made.

3. **Stochastic-scope closure**
   - support violation mass `alpha` implies `TV >= alpha`;
   - zero support violation does not imply stochastic fidelity;
   - support validity is explicitly an admissibility floor;
   - support-level R* does not claim to preserve stochastic decision probabilities.

## Why this is the preferred form

This package closes the paper's conceptual loop without manufacturing another system contribution:

`claim -> consequential projection -> target-compatible worlds -> support envelope -> exact validity boundary -> selective reuse boundary`.

It also gives N2 and N2b a stronger role. N2 is the "too coarse" boundary: a projection/evidence class can merge consequentially different decisions. N2b is the "too fine" boundary: raw feedback can differ while the consequential decision class remains invariant.

## Claims explicitly rejected

The manuscript must not claim that R* is:

- globally cost-optimal;
- already implemented/evaluated as a production replay engine;
- universally superior to R0/R1/R2;
- a complete stochastic-fidelity mechanism; or
- guaranteed to reduce controller calls, latency, or runtime in every workload.

Those claims require a cost model and/or a new implementation study and are not needed for the current paper.

## Empirical stop rule

No new empirical experiment is required by this theory package. The promoted empirical chain, including the downstream provisioning confirmation and documented-default capacity flip, remains unchanged.

Do not reopen experiments merely to "evaluate R*" unless a later cold manuscript review identifies a concrete acceptance-critical gap that cannot be closed by exposition or existing evidence.

## Preferred manuscript footprint

Use the support-envelope proposition as the main theorem statement, immediately followed by the maximal-certified-reuse corollary and a short stochastic-scope paragraph. Keep the total theory addition near 0.3--0.45 technical page by reusing existing notation.

If page pressure becomes severe, keep the theorem and corollary, compress stochastic scope to the TV inequality plus one sentence/counterexample, and leave the full proofs in the recovery materials rather than inflating the main paper.

## Next action

The next high-ROI step is **manuscript integration and cold compression**, not another experiment or another theoretical extension. After integration, perform a reviewer-style audit of:

- novelty and contribution hierarchy;
- formal notation consistency;
- whether every empirical result serves one central thesis;
- whether the downstream/default-flip evidence is presented without redundancy;
- page budget; and
- whether any sentence overclaims beyond the frozen theory/empirical authority.
