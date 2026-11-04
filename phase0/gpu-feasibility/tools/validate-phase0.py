#!/usr/bin/env python3
"""Validate retained Phase 0 evidence without replacing its results or rerunning a VM."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

PACKAGE = Path(__file__).resolve().parents[1]
PHASE = PACKAGE.parent
ROOT = PHASE.parent
BASE = "d74a521f7933baeeb771f412cb9261c3311ded62"


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""): value.update(block)
    return value.hexdigest()


def validate_index(phase):
    rows = json.loads((phase / "evidence/index.json").read_text())["files"]
    for row in rows:
        file = (phase / row["path"]).resolve()
        if not file.is_relative_to(phase.resolve()): raise ValueError("Index path escapes Phase 0")
        if digest(file) != row["sha256"] or file.stat().st_size != row["bytes"]:
            raise ValueError("Evidence bytes changed: " + row["path"])
    return len(rows)


def validate_boot(folder, accelerator):
    result = json.loads((folder / "result.json").read_text(encoding="utf-8-sig"))
    if result["status"] != "PASS" or result["accelerator"] != accelerator:
        raise ValueError("No passing diagnostic for " + accelerator)
    argv = result["argv"]
    selections = [argv[i + 1] for i, x in enumerate(argv[:-1]) if x == "-accel"]
    if selections != [accelerator]: raise ValueError("Acceleration fallback or mismatch")
    console = (folder / "serial.log").read_text(encoding="utf-8-sig")
    if "Linux version " not in console or not re.search(r"(?m)^PHASE0_READY_(?:[0-9a-f]{16}|[0-9a-f]{32})\r?\nx86_64\r?\n", console):
        raise ValueError("No returned nonce plus architecture; a command echo is insufficient")
    return {"status": "PASS", "scope": "Retained Linux diagnostic evidence; not a new boot",
            "binary_sha256": result["qemu_sha256"], "gpu": "NOT TESTED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): parser.error("use a fresh output directory")
    args.output.mkdir(parents=True)
    result = {"scope": "Phase 0 artifact revalidation, not a new VM/GPU test", "status": "FAIL",
              "phase0_commit": BASE, "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        committed_index = subprocess.check_output(["git", "show", BASE + ":phase0/evidence/index.json"], cwd=ROOT)
        if committed_index != (PHASE / "evidence/index.json").read_bytes(): raise ValueError("Phase 0 index differs from published revision")
        result["retained_artifacts_checked"] = validate_index(PHASE)
        result["tcg"] = validate_boot(PHASE / "evidence/tcg-boot", "tcg")
        result["whpx"] = validate_boot(PHASE / "evidence/windows-whpx-boot", "whpx")
        checks = []
        for file, record in ((PHASE / ".work/qemu-build-linux/qemu-system-x86_64", PHASE / "evidence/build-linux.json"),
                             (PHASE / ".work/qemu-build-cross/qemu-system-x86_64.exe", PHASE / "evidence/build-windows-cross.json"),
                             (PHASE / ".work/windows-diagnostic/qemu-system-x86_64.exe", PHASE / "evidence/windows-diagnostic-binary.json")):
            expected = json.loads(record.read_text()).get("binary_sha256")
            # Linux build evidence uses qemu_sha256 in some profiles.
            if not expected: expected = json.loads(record.read_text()).get("qemu_sha256")
            if not file.exists(): checks.append({"path": str(file.relative_to(ROOT)), "status": "NOT TESTED", "reason": "Local binary not present; retained record only"}); continue
            if digest(file) != expected: raise ValueError("Local binary differs from recorded hash: " + str(file))
            checks.append({"path": str(file.relative_to(ROOT)), "status": "PASS", "sha256": expected})
        result["binary_checks"] = checks
        tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "phase0/tests", "-v"],
                               cwd=ROOT, capture_output=True, text=True, timeout=60)
        (args.output / "phase0-tests.log").write_text(tests.stdout + tests.stderr)
        result["harness_exit_code"] = tests.returncode
        if tests.returncode: raise ValueError("Phase 0 harness regression")
        result["status"] = "PASS"
        result["reason"] = "Retained published bytes/boot responses and local binary hashes agree; original harness passes"
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc: result["reason"] = str(exc)
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__": sys.exit(main())
