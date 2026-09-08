# Gate S3-C0 — Claim-to-Queue Composition Result Seal

Status: **FROZEN PASS.**

S3-C0 closed the missing semantic-to-deployment composition edge without executing a new target or queue experiment.

## Authority

- S3-C0 protocol/proof head: `cadd8483691246853030722fecdd8fcdc4717ffc`
- protocol tree: `c37efad15de8a02aa3467fe1281ff40b617cc311`
- exact parent S3 result seal: `cf1f09398ad6148dfa1907dd2a02bdc443308ab7`
- workflow run: `34173629381`
- workflow job: `101898621916`
- artifact: `10036506766`
- artifact ZIP SHA-256: `74e4f45a47fb63b88e271efdf4156466be312b13527b08789fd00873e18e770e`

The CI independently fetched the frozen historical queue authorities rather than trusting copied text in the current branch.

## Composition result

The promoted queue endpoint counts task-local QoS-1 messages with terminal roles `command`, `query`, and `state`.

For a task whose evidence is `confirmed_by_deadline`:

```text
direct target-native: command=2 query=0 state=2 total=4
ReplayMark-Native:    command=2 query=0 state=2 total=4
```

For a task whose evidence is `not_visible_by_deadline`:

```text
direct target-native: command=2 query=1 state=3 total=6
ReplayMark-Native:    command=2 query=1 state=3 total=6
```

Thus, with `N` tasks and `U` tasks requiring the direct-native query branch,

```text
M_direct-native(N,U) = 4N + 2U
M_ReplayMark(N,U)     = 4N + 2U.
```

The verifier exhaustively checked the equality for every `0 <= N <= 512` and every `0 <= U <= N`. A second endpoint computation accepts evidence tokens only and has no policy-label or hidden-target-class input.

## Critical correction discovered by C0

S3 `ALWAYS_NATIVE` is **not** the direct target-native deployment reference. It deliberately runs the caller-owned query-confirmation path for every task as a conservative rerun-all baseline. Direct target-native execution queries only when the decision evidence requires it.

Accordingly, S3-C1 must compare ReplayMark-Native against an independent direct target-controller implementation, not against the S3 `ALWAYS_NATIVE` arm.

## The legacy 166 boundary is not inherited

The legacy documented-default experiment correctly derived `166 = floor(1000/6)` because its homogeneous changed target forced every native task onto the six-message branch.

The S3 heterogeneous workload has both four-message and six-message direct-native branches. Its aggregate work is `4N + 2U`, not `6N` in general. Therefore `166` is not a valid preselected target for the new deployment closure.

This is a strengthening, not a retreat: S3-C1 must test whether ReplayMark-Native reaches the **same deployment conclusion as independent direct target-native execution under the same workload**, rather than trying to reproduce a nostalgic number.

## Verification closure

All checks passed, including:

- exact S3 result-seal parent;
- only four protocol/proof files added;
- all seven cross-history frozen blobs exact;
- legacy endpoint roles exactly `{command, query, state}`;
- legacy documented default queue count exactly 1000;
- direct-native branch is evidence-conditional;
- legacy and P6 devices preserve the command/query -> state mechanism;
- S3 native query/fresh-ACT2 provenance and phase-A quiescence are present;
- safe task endpoint equality;
- unsafe task endpoint equality;
- aggregate equality;
- policy-label-free endpoint oracle;
- old homogeneous 166 derivation independently recomputed;
- heterogeneous workload proven not to have a fixed six-messages-per-task law;
- no live target/queue execution; and
- no experimental result file or live runner added.

## S3-C1 admission

**ADMITTED.**

The next deployment protocol must be frozen before a new queue outcome and must use:

1. an independent direct target controller as deployment truth;
2. unchanged ReplayMark certification/admission semantics;
3. the same prospectively frozen workload for direct-native and ReplayMark-Native;
4. the exact persistent QoS-1 queue endpoint above;
5. an independent raw-event endpoint oracle with no policy/hidden-class input;
6. no preselected numeric boundary from the old homogeneous workload; and
7. first-complete immutable result authority.

The target scientific claim is now sharper:

> **ReplayMark-Native should reach the same deployment conclusion as independent target-native execution while preserving every historical decision that the frozen evidence certifies safe.**

S3-C0 does not itself promote any new queue, latency, sequence-equivalence, or exactly-once result.
