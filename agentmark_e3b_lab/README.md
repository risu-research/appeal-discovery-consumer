# AgentMark E3b isolated compute lab

Temporary branch-only reference-broker runner. It does not alter the carrier repository's main branch.

The decisive run records a clean source trace on Mosquitto, estimates source/target prefix feedback laws without recovery traffic, then compares:

- R0 rigid replay: semantics and source issue times frozen;
- R1 timing-feedback-only replay: semantics frozen, timing follows target completion;
- R2 semantic-feedback-preserving execution: VERIFY may be inserted when the policy decision predicate changes.

The same report includes a finite-sample Replay Safety Certificate and Mosquitto `$SYS` broker-native counters.
