# ReplayMark External Transfer — Post-Result Artifact Hardening

**Status:** post-result verifier/artifact hardening only  
**Scientific execution head:** `96edce97f4b79641dcf4b1975e18218f39e37c97`  
**Frozen protocol:** `c7e60c5e03712e7a30ac1e53bccfa2025bfb6fa1`  
**Frozen auditor:** `920b759c660a711d94f7aa92bd8059acba8965dc`  
**Original successful run:** `34014534101`  
**Original scientific decision:** `PROMOTED_SOURCE_TRANSFER`; G4/G5 not satisfied.

## Purpose

This branch does **not** change the preregistered/frozen scientific gate, its inputs, or its verdict rules. It hardens the *artifact* after the decisive result so a reviewer can reproduce and inspect the transfer result without depending on mutable branch state or undocumented assumptions.

The original frozen protocol/auditor/workflow remain byte-preserved and authoritative for the scientific result. The hardened verifier is an additional, post-result audit and may only confirm or expose weaknesses in the artifact; it may not retroactively upgrade G3 to G4/G5 or rewrite the original promotion criteria.

## Hardening additions

1. **Self-contained capsule.** The workflow stages the frozen protocol, frozen auditor, original workflow, hardening note/verifier/workflow, original and hardened result files, exact third-party source snapshots, upstream licenses, manifests, and checksums in one capsule tree.
2. **Immutable GitHub Actions pins.** Packaging workflows pin actions to exact commits rather than floating major tags. The final packaging path uses Node24-native exact revisions: `actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09` and `actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f`.
3. **Exhaustive NVIDIA pairing.** The shipped TensorRT-LLM trace is checked for complete one-to-one structural coverage: every assistant event carrying historical `tool_calls` must have the same-branch historical `tool_call` sequence before the next same-branch message; every historical tool-call event must be consumed exactly once. The report emits `matched/total`, not merely one witness.
4. **Executable AIPerf topology checks.** In addition to the original documentation markers, the hardened verifier parses the pinned AIPerf loader and branch orchestrator with Python `ast`, confirms executable construction of `PrerequisiteKind.SPAWN_JOIN`, confirms `_expand_subagent_to_child_plans` is actually invoked, and confirms the orchestrator consumes `SPAWN_JOIN` prerequisites in executable comparison/control-flow logic.
5. **Third-party provenance.** Every embedded upstream snapshot is pinned by repository commit and Git blob SHA; SHA-256 and byte length are recorded as well. Apache-license files from both upstream repositories are bundled with the snapshots.
6. **Byte-for-byte original reproduction.** The exact original GitHub Actions artifact is recovered by artifact ID and SHA-256, the frozen auditor is rerun on exact inputs, and both canonical original outputs must compare byte-for-byte with the original evidence.
7. **Deterministic hardened outputs.** Runtime-specific metadata is separated from canonical hardening JSON/report output so the canonical result can be compared byte-for-byte across environments.
8. **Closed-world capsule inventory.** The final capsule treats `CHECKSUMS.sha256` as a complete file inventory, not merely a list of hashes: missing files, unlisted extras, symlinks, duplicate entries, unsafe paths, and checksum mismatches fail closed.
9. **No verification mutation.** Python bytecode writes are disabled; verification is run before packaging and again after a fresh extraction; the capsule file inventory must remain unchanged. This closes the discovered `__pycache__`/unmanifested-file failure mode from an intermediate capsule draft.
10. **Deterministic archive construction.** The inner standalone ZIP is built twice with normalized timestamps/modes and the two byte streams must be identical before promotion.
11. **Network-free one-command reproduction.** Exact input aliases are bundled under `08_REPRODUCE/inputs`; after extraction, `python 08_REPRODUCE/verify_capsule.py` verifies the closed manifest, authority chain, original scientific outputs, and hardened outputs without network access or third-party Python packages.
12. **Explicit non-upgrade rule.** Passing the hardened checks confirms artifact robustness only. It does not establish target-native `INVALID`, prevalence, or a downstream benchmark flip.

## Wording discipline

The frozen protocol uses some historical wording such as “independently authored.” The manuscript may use the more conservative wording “separate implementations.” The frozen protocol is not rewritten post hoc; this note records the editorial refinement while preserving the historical scientific artifact.

## Expected hardened outcome

A successful hardening run should establish all of the following without adding a new scientific claim:

- original frozen audit re-runs successfully on the exact pinned inputs and canonical outputs are byte-identical to the original run evidence;
- NVIDIA shipped-trace historical-decision/tool-event matching is exhaustive (expected 23/23 on the pinned trace);
- AIPerf topology retention is supported by executable loader/orchestrator code, not only documentation strings;
- all embedded upstream snapshots match their exact Git blob identities;
- the capsule has a closed, checksum-verified inventory and verification creates no unmanifested files;
- the deterministic inner ZIP is reproducible byte-for-byte within the packaging run;
- the original G3 result remains bounded to external claim-boundary transfer, with G4/G5 still not satisfied.
