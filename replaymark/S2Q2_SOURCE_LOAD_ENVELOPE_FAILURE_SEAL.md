# Gate S2-Q2 — Complete Source Load-Envelope Scientific Failure Seal

Status: **FROZEN COMPLETE SCIENTIFIC FAILURE.**

This document does not repair, reinterpret, or supersede the first complete Q2
execution. It seals that execution exactly as observed.

## Authoritative execution

- Q2 execution commit: `79577a00e78aa61a5d92c6d608a9f64601bdb1d9`
- Q2 execution tree: `96cbeb1e54399cd397c55128b30675e7c416d4e9`
- frozen P2 parent: `22ec2da2e62c1fa7e9d1a5e02ff676188d90ab5e`
- workflow run: `34158327040`
- workflow job: `101854698171`
- artifact: `10031766440`
- artifact ZIP SHA-256: `159abbf5e99ecd8ec4e051824cfb63fd59918ac539009821447d89e616377cdd`
- artifact size: `120966` bytes

The run completed the exact prospective boundary check, all three source screening
rounds, independent all-candidate recomputation and W* selection, final verification,
artifact sealing, upload, and cleanup. The workflow's final enforcement step failed
because the **scientific verdict was FAIL**. This was not an infrastructure failure.

## Frozen preflight facts

Before source execution, the Q2 verifier established:

- exact P2 parent;
- only the four declared Q2 execution files were added;
- eight P2/Q1 authority files remained unchanged;
- 37/37 S0 frozen blobs matched;
- runtime micro-optimization remained `FROZEN`;
- live runner imported zero ReplayMark semantic/oracle modules;
- shifted-target code path was absent;
- holdout did not expose a caller-supplied W*;
- each of the three screening rounds had an independent broker/device restart path.

These facts remain part of the Q2 failure authority.

## Complete screening result

All nine screening cells were structurally valid and all candidate task namespaces
were fresh. Exactly 1,728 source-only rows were evaluated under the frozen P2
qualification.

| Wave | Rows | Visible by 100 ms | Replicate p99 ms | Pooled median ms | Pooled p99 ms | Qualification |
|---:|---:|---:|---|---:|---:|---|
| 16 | 576 | 576/576 | 85.06435479, 84.26182307, 48.05237987 | 7.2338205 | 84.45775575 | FAIL |
| 8 | 576 | 566/576 | 123.68336576, 123.97112310, 82.79958565 | 3.4840475 | 123.66788775 | FAIL |
| 4 | 576 | 576/576 | 46.34545762, 82.56370927, 82.96324296 | 41.0700530 | 82.66091325 | FAIL |

Wave 16 failed the frozen per-replicate and pooled p99 bounds. Wave 8 failed both
100-ms visibility and p99 requirements. Wave 4 failed the frozen per-replicate and
pooled p99 bounds.

No predeclared candidate in `{16,8,4}` satisfied every P2 criterion.

Therefore the only legal source-selection result is:

```text
W_star_screen = null
```

The raw screening result digests are:

```text
round 0  cb438749c599080b280768d48172d8fe57e86b4b8013779e42ac1150dfea838f
round 1  044f36d956b56e72ab5a2233e9ed7826f94bf65e56cdd429b2b6014e75562964
round 2  2c7c6264714af8b4f4c90f3eea22b006f1470155b71e89195f9592dad94e5d51
```

The independent screening-selection seal SHA-256 is:

`2d10d33be500a7a1c744767b57213c37b14b4e45c870ab517c2cba00c55d53a5`

## Holdout and D* were correctly not admitted

Because `W_star_screen` is null, the workflow skipped all three holdout replicates.
That is the protocol-defined behavior, not missing evidence.

Consequently:

```text
holdout_admitted                         = false
holdout_rows                             = 0
D_star_ms                                = null
screening_rows_used_in_D_star_estimate   = 0
shifted_target_executed                  = false
ACT2_candidate_constructed               = false
fallback                                 = ABSENT
regeneration                             = ABSENT
```

No target outcome existed when Q2 failed.

## Descriptive diagnostic — not a new qualification rule

A descriptive audit of the frozen raw rows provides one important strategic signal,
but it does **not** alter the Q2 verdict or create a new threshold.

Observed scheduler start-lateness p99 was below roughly 1.32 ms in every screening
cell, while completion tails repeatedly appeared around roughly 82–85 ms and, for
some wave-8 cells, around 123–124 ms. Wave 4 also had a substantially larger pooled
median (~41 ms) than wave 8 (~3.48 ms) and wave 16 (~7.23 ms).

Thus the first complete Q2 evidence does not support a monotonic claim that lowering
the offered burst wave necessarily removes the frozen source tail. The pattern is
consistent with there being timing structure outside simple offer-scheduler
lateness, but **no causal mechanism is established here**. In particular, this seal
does not claim a TCP, MQTT, kernel, scheduler, or broker cause.

## Anti-repair lock

The following are forbidden for this Q2 protocol generation:

- rerunning Q2 until a favorable promotion result appears;
- inserting wave 2, wave 1, or any other candidate into the completed Q2 generation;
- falling back to a smaller wave after this complete failure;
- relaxing or retuning the frozen 80-ms p99 criterion;
- computing D* from failed screening evidence;
- probing the shifted target after source qualification failed;
- treating a later exact repeat as anything other than replication evidence.

Any scientifically legitimate continuation must be a **new protocol generation**
that cites this Q2 failure as immutable prior evidence.

## Strategic implication

The next defensible question is no longer "which smaller wave should we try?".
The stronger question is:

> What source-side transport/runtime timing structure produces the non-monotonic
> completion tail under the frozen workload, and which observable boundary can be
> prospectively qualified without target-informed tuning?

That question should be answered by a new, source-only, prospectively frozen
transport-tail characterization protocol before any new mixed-target attempt.

This seal makes no change to ReplayMark semantics, R*, runtime realization,
execution admission, the inherited S2 target policy schedule, fallback policy, or
regeneration policy.
