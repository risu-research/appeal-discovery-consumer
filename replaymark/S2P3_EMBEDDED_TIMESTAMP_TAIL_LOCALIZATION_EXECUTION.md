# Gate S2-P3E — Embedded-Timestamp Tail Localization Execution

This increment executes the frozen S2-P3 protocol exactly once.

It is source-only. It does not alter Q2, select `W*`, derive `D*`, relax the 80-ms
Q2 criterion, construct ACT2, execute a shifted target, regenerate, or fall back.

The frozen device remains byte-identical. P3 records the existing `ts_mono_ns`
field already emitted by the device and decomposes each source observation into
pre-device and post-device elapsed time after explicit Linux monotonic-clock
namespace qualification.

The first complete execution is authoritative. Its localization class may be
`POST_DEVICE_DOMINANT`, `PRE_DEVICE_DOMINANT`, `MIXED_OR_UNLOCALIZED`, or
`CLOCK_DOMAIN_INVALID`. Classification is diagnostic; scientific PASS requires
complete structurally valid source evidence and a valid cross-process clock boundary,
not any preferred localization outcome.
