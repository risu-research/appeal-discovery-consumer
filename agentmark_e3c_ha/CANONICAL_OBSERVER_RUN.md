# E3c Canonical-Observer Promotion Run

Canonical observer source commit: `735b5a5df31ef89b0720442569e8be3468fcf2ba`.

This file is a docs-only trigger for a fresh replicated E3c promotion run because the canonicalization commit was pushed by `GITHUB_TOKEN`, which does not recursively trigger the E3c workflow. The trigger changes no experiment code, scientific parameter, gate, validator, or preregistration.

The run must use the unchanged preregistered protocol and the Home Assistant 2026.9.0 immutable image digest already fixed by the E3c workflow. Promotion requires both independent replicas to pass producer gates, independent host-side validation, native event conservation/Context lineage, both negative controls, and aggregate agreement.
