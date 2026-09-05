from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--provenance", required=True)
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, object]] = []
    for candidate in manifest["candidates"]:
        candidate_id = str(candidate["id"])
        repository = str(candidate["repository"])
        commit = str(candidate["commit"])
        path = str(candidate["path"])
        url = f"https://raw.githubusercontent.com/{repository}/{commit}/{path}"

        request = urllib.request.Request(
            url,
            headers={"User-Agent": "AgentMark-natural-controller-qualification/1"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
            status = getattr(response, "status", 200)

        if status != 200 or not payload:
            raise RuntimeError(
                f"failed to fetch {candidate_id}: status={status}, bytes={len(payload)}"
            )

        destination = out_dir / f"{candidate_id}.yaml"
        destination.write_bytes(payload)
        records.append(
            {
                "id": candidate_id,
                "repository": repository,
                "commit": commit,
                "path": path,
                "raw_url": url,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "local_file": destination.name,
            }
        )

    provenance = {
        "schema": "agentmark.natural_controller_corpus.fetch.v1",
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "sources": records,
    }
    Path(args.provenance).write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(provenance, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
