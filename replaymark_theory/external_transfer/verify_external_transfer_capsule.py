#!/usr/bin/env python3
"""One-command offline verifier for the ReplayMark external-transfer capsule."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_checksum_manifest(root: Path) -> None:
    manifest = root / "07_MANIFESTS" / "CHECKSUMS.sha256"
    if not manifest.is_file():
        raise RuntimeError("missing CHECKSUMS.sha256")
    checked = 0
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        expected, rel = raw.split(None, 1)
        rel = rel.strip()
        if rel.startswith("./"):
            rel = rel[2:]
        path = root / rel
        if not path.is_file():
            raise RuntimeError(f"checksum target missing: {rel}")
        observed = digest(path)
        if observed != expected:
            raise RuntimeError(
                f"checksum mismatch for {rel}: expected={expected} observed={observed}"
            )
        checked += 1
    print(f"CHECKSUMS: PASS ({checked} files)")


def run(cmd: list[str], env: dict[str, str]) -> None:
    print("RUN:", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)


def compare_bytes(a: Path, b: Path, label: str) -> None:
    if a.read_bytes() != b.read_bytes():
        raise RuntimeError(f"byte comparison failed: {label}")
    print(f"{label}: BYTE-IDENTICAL")


def main() -> int:
    here = Path(__file__).resolve()
    root = here.parents[1]
    inputs = root / "08_REPRODUCE" / "inputs"
    frozen_auditor = root / "01_FROZEN_SCIENCE" / "audit_external_retention_transfer.py"
    hardener_v2 = root / "02_POST_RESULT_HARDENING" / "audit_external_retention_transfer_hardened_v2.py"

    for path in (inputs, frozen_auditor, hardener_v2):
        if not path.exists():
            raise RuntimeError(f"capsule component missing: {path}")

    verify_checksum_manifest(root)

    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"

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

    print("REPLAYMARK EXTERNAL TRANSFER CAPSULE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
