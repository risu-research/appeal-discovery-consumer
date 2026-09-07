# Gate S3 — First-Complete Caller-Owned Native Restoration Result Seal

Status: **FROZEN FIRST-COMPLETE PASS.**

S3 used the exact S3-P protocol, the exact frozen P6 heterogeneous target, and the inherited P6 task partition. ReplayMark production semantics and the no-fallback execution gate were unchanged.

## Authority

- S3-P protocol: `75d5d4379fdda221c0b9661f799d7779d6bba9f2`
- first-complete execution: `8333e8808d5a950effd8a4e552718be3324909d3`
- execution tree: `62d8ee856f9b7ea6064d4287c16a8b2c07a47c94`
- workflow run: `34170631467`
- workflow job: `101890108930`
- artifact: `10035602271`
- artifact ZIP SHA-256: `31bd3972787ee09e0e2c366a46d2fc8f9cc1049d5d33668bb8b253901f5af2db`
- live raw SHA-256: `077af28be4d0fc2923a4bf454a1e609b55af6e4e5b111d37d6ed372e09f23aaa`

The first complete 1,152-row report is authoritative and is not replaceable by a later favorable rerun.

## Result

| Caller policy | Oracle-safe | Oracle-unsafe | Historical reuse | Native recovery | Restored |
|---|---:|---:|---:|---:|---:|
| Always-Reuse | 191 | 193 | 384 | 0 | 384 |
| Always-Native | 191 | 193 | 0 | 384 | 384 |
| ReplayMark-Native | **192** | **192** | **192** | **192** | **384** |

ReplayMark-Native achieved exact complementarity:

```text
historical reuse set = independent-oracle safe set
caller native set     = independent-oracle unsafe set
```

and therefore:

```text
unsafe historical executions = 0
unnecessary native recoveries = 0
restored tasks                = 384 / 384
```

The two baselines demonstrate the two extremes:

```text
Always-Reuse:
  unsafe historical executions = 193

Always-Native:
  unnecessary native recoveries = 191
```

Thus the selective policy preserved all currently supportable history assigned to it while routing only the unsupported complement through caller-owned native semantics.

## Provenance closure

The application-level channels remained disjoint:

- historical application calls: 576 total;
- native query calls: 576 total;
- native fresh ACT2 calls: 576 total.

For every native task, the independent verifier established the required causal chain from same-task `QUERY_A`, through a query-caused current-state confirmation, to fresh ACT2 generation/publish and a matching B-side command effect. There were zero provenance, phase, semantic, execution, native, or B-effect failures.

## Hidden target class remains only a sanity check

Independent evaluation produced:

```text
REFERENCE: 574 safe, 2 unsafe
SHIFTED:     0 safe, 576 unsafe
```

The two unsafe REFERENCE tasks again show why the hidden target class is not semantic truth. ReplayMark's decisions are grounded in actual runtime evidence.

## Interpretation boundary

This result does **not** mean ReplayMark contains a fallback policy. ReplayMark still only certifies and admits or blocks historical reuse. The caller owns the query-confirmation and fresh-ACT2 recovery path.

No latency claim, cross-process exactly-once claim, broker-delivery exactly-once claim, or automatic retry claim is promoted by S3.

The next decision should be made at the paper level: either close one final deployment-level consequence if it materially strengthens the main claim, or stop adding system mechanisms and perform the manuscript quantum revision around the now-closed selective-retention/restoration story.
