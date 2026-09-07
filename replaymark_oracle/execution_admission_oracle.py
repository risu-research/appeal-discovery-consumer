from __future__ import annotations

"""Independent literal oracle for Gate S1 execution admission.

This module imports no ReplayMark production code. It describes only the
declared admission relation after certificate-chain validation.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LiteralAdmissionExpectation:
    certificate_exact: bool
    verdict: str
    reuse_disposition: str
    outcome: str


def expected_execution_admission(
    *,
    certificate_exact: bool,
    verdict: str,
    reuse_disposition: str,
) -> LiteralAdmissionExpectation:
    if not certificate_exact:
        outcome = "REJECT_CERTIFICATE"
    elif verdict == "VALID" and reuse_disposition == "REUSE":
        outcome = "ADMIT_REUSE"
    elif verdict in {"INVALID", "UNRESOLVED"} and reuse_disposition == "DO_NOT_REUSE":
        outcome = "BLOCK_REUSE"
    else:
        outcome = "REJECT_CERTIFICATE"
    return LiteralAdmissionExpectation(
        certificate_exact=certificate_exact,
        verdict=verdict,
        reuse_disposition=reuse_disposition,
        outcome=outcome,
    )


__all__ = ("LiteralAdmissionExpectation", "expected_execution_admission")
