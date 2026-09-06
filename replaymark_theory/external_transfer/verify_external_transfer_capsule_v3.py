#!/usr/bin/env python3
"""Final closed-world capsule verifier with Node24-native workflow authority."""

from __future__ import annotations

from pathlib import Path

import verify_external_transfer_capsule_v2 as core


def verify_authority_final(root: Path) -> None:
    authority = (root / "07_MANIFESTS" / "AUTHORITY.txt").read_text(encoding="utf-8")
    required = {
        "scientific_execution_head=96edce97f4b79641dcf4b1975e18218f39e37c97",
        "frozen_protocol_commit=c7e60c5e03712e7a30ac1e53bccfa2025bfb6fa1",
        "frozen_auditor_commit=920b759c660a711d94f7aa92bd8059acba8965dc",
        "original_run_id=34014534101",
        "original_artifact_id=9983484671",
        "original_artifact_sha256=44a5adf0ee21f5b4397ab0c1633bea1aeb195787058986a53b6488c3695a7969",
        "actions_checkout_commit=fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09",
        "actions_checkout_runtime=node24",
        "actions_upload_artifact_commit=b7c566a772e6b6bfb58ed0dc250532a479d7789f",
        "actions_upload_artifact_runtime=node24",
    }
    present = set(authority.splitlines())
    absent = sorted(required - present)
    if absent:
        raise RuntimeError(f"authority record missing required entries: {absent}")

    original_zip = root / "03_ORIGINAL_RUN_EVIDENCE" / "ORIGINAL_GITHUB_ACTIONS_ARTIFACT.zip"
    expected_original = "44a5adf0ee21f5b4397ab0c1633bea1aeb195787058986a53b6488c3695a7969"
    observed = core.digest(original_zip)
    if observed != expected_original:
        raise RuntimeError(
            f"original Actions artifact digest mismatch: expected={expected_original} observed={observed}"
        )
    print("AUTHORITY CHAIN: PASS")


if __name__ == "__main__":
    core.verify_authority = verify_authority_final
    raise SystemExit(core.main())
