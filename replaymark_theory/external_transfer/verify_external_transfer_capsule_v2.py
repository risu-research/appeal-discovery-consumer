#!/usr/bin/env python3
"""Closed-world, one-command offline verifier for ReplayMark external transfer.

The checksum manifest is treated as a *complete* inventory, not merely a list
of files to hash.  Any unlisted file (except the manifest itself), duplicate
manifest entry, symlink, missing file, or checksum mismatch fails closed.
Python bytecode generation is disabled for child verifiers so running this
script does not mutate the capsule.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

MANIFEST_REL = "07_MANIFESTS/CHECKSUMS.sha256"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def normalized_inventory(root: Path) -> set[str]:
    inventory: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise RuntimeError(f"symlink forbidden in capsule: {path.relative_to(root)}")
        if path.is_file():
            inventory.add(path.relative_to(root).as_posix())
    return inventory


def parse_manifest(root: Path) -> dict[str, str]:
    manifest = root / MANIFEST_REL
    if not manifest.is_file():
        raise RuntimeError(f"missing {MANIFEST_REL}")
    entries: dict[str, str] = {}
    for lineno, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split(None, 1)
        if len(parts) != 2:
            raise RuntimeError(f"malformed checksum line {lineno}: {raw!r}")
        expected, rel = parts
        rel = rel.strip()
        if rel.startswith("./"):
            rel = rel[2:]
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            raise RuntimeError(f"unsafe manifest path on line {lineno}: {rel!r}")
        if rel == MANIFEST_REL:
            raise RuntimeError("checksum manifest must not recursively list itself")
        if rel in entries:
            raise RuntimeError(f"duplicate checksum entry: {rel}")
        if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise RuntimeError(f"invalid SHA-256 on line {lineno}: {expected!r}")
        entries[rel] = expected
    return entries


def verify_closed_manifest(root: Path) -> None:
    entries = parse_manifest(root)
    actual = normalized_inventory(root)
    expected_inventory = set(entries) | {MANIFEST_REL}
    extras = sorted(actual - expected_inventory)
    missing_inventory = sorted(expected_inventory - actual)
    if extras or missing_inventory:
        raise RuntimeError(
            "closed-world inventory mismatch: "
            f"extras={extras} missing={missing_inventory}"
        )
    for rel, expected in sorted(entries.items()):
        path = root / rel
        observed = digest(path)
        if observed != expected:
            raise RuntimeError(
                f"checksum mismatch for {rel}: expected={expected} observed={observed}"
            )
    print(f"CLOSED MANIFEST: PASS ({len(entries)} hashed files + manifest)")


def run(cmd: list[str], env: dict[str, str]) -> None:
    print("RUN:", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)


def compare_bytes(a: Path, b: Path, label: str) -> None:
    if a.read_bytes() != b.read_bytes():
        raise RuntimeError(f"byte comparison failed: {label}")
    print(f"{label}: BYTE-IDENTICAL")


def verify_authority(root: Path) -> None:
    authority = (root / "07_MANIFESTS" / "AUTHORITY.txt").read_text(encoding="utf-8")
    required = {
        "scientific_execution_head=96edce97f4b79641dcf4b1975e18218f39e37c97",
        "frozen_protocol_commit=c7e60c5e03712e7a30ac1e53bccfa2025bfb6fa1",
        "frozen_auditor_commit=920b759c660a711d94f7aa92bd8059acba8965dc",
        "original_run_id=34014534101",
        "original_artifact_id=9983484671",
        "original_artifact_sha256=44a5adf0ee21f5b4397ab0c1633bea1aeb195787058986a53b6488c3695a7969",
        "actions_checkout_commit=11d5960a326750d5838078e36cf38b85af677262",
        "actions_upload_artifact_commit=ea165f8d65b6e75b540449e92b4886f43607fa02",
    }
    present = set(authority.splitlines())
    absent = sorted(required - present)
    if absent:
        raise RuntimeError(f"authority record missing required entries: {absent}")
    original_zip = root / "03_ORIGINAL_RUN_EVIDENCE" / "ORIGINAL_GITHUB_ACTIONS_ARTIFACT.zip"
    expected_original = "44a5adf0ee21f5b4397ab0c1633bea1aeb195787058986a53b6488c3695a7969"
    observed = digest(original_zip)
    if observed != expected_original:
        raise RuntimeError(
            f"original Actions artifact digest mismatch: expected={expected_original} observed={observed}"
        )
    print("AUTHORITY CHAIN: PASS")


def main() -> int:
    here = Path(__file__).resolve()
    root = here.parents[1]
    inputs = root / "08_REPRODUCE" / "inputs"
    frozen_auditor = root / "01_FROZEN_SCIENCE" / "audit_external_retention_transfer.py"
    hardener_v2 = root / "02_POST_RESULT_HARDENING" / "audit_external_retention_transfer_hardened_v2.py"

    for path in (inputs, frozen_auditor, hardener_v2):
        if not path.exists():
            raise RuntimeError(f"capsule component missing: {path}")

    # Verify the capsule before executing any embedded code.
    verify_closed_manifest(root)
    verify_authority(root)

    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    with tempfile.TemporaryDirectory(prefix="replaymark-external-verify-") as td:
        temp = Path(td)
        original_out = temp / "original"
        hardened_out = temp / "hardened"
        original_out.mkdir()
        hardened_out.mkdir()

        run(
            [
                sys.executable,
                str(frozen_auditor),
                "--input-dir",
                str(inputs),
                "--output-dir",
                str(original_out),
            ],
            env,
        )
        compare_bytes(
            original_out / "EXTERNAL_RETENTION_TRANSFER_RESULTS.json",
            root / "03_ORIGINAL_RUN_EVIDENCE" / "EXTERNAL_RETENTION_TRANSFER_RESULTS.json",
            "ORIGINAL_RESULTS",
        )
        compare_bytes(
            original_out / "EXTERNAL_RETENTION_TRANSFER_REPORT.md",
            root / "03_ORIGINAL_RUN_EVIDENCE" / "EXTERNAL_RETENTION_TRANSFER_REPORT.md",
            "ORIGINAL_REPORT",
        )

        run(
            [
                sys.executable,
                str(hardener_v2),
                "--input-dir",
                str(inputs),
                "--output-dir",
                str(hardened_out),
            ],
            env,
        )
        compare_bytes(
            hardened_out / "HARDENED_EXTERNAL_TRANSFER_RESULTS_V2.json",
            root / "05_HARDENED_RESULTS" / "HARDENED_EXTERNAL_TRANSFER_RESULTS_V2.json",
            "HARDENED_RESULTS_V2",
        )
        compare_bytes(
            hardened_out / "HARDENED_EXTERNAL_TRANSFER_REPORT_V2.md",
            root / "05_HARDENED_RESULTS" / "HARDENED_EXTERNAL_TRANSFER_REPORT_V2.md",
            "HARDENED_REPORT_V2",
        )
        compare_bytes(
            hardened_out / "UPSTREAM_MANIFEST_V2.json",
            root / "05_HARDENED_RESULTS" / "UPSTREAM_MANIFEST_V2.json",
            "UPSTREAM_MANIFEST_V2",
        )

    # Running verification must not mutate the capsule or create unmanifested
    # __pycache__ / .pyc files.
    verify_closed_manifest(root)
    print("REPLAYMARK EXTERNAL TRANSFER CAPSULE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
