#!/usr/bin/env python3
"""Verify evidence bytes and tracked membership, without promoting runtime gates."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def verify_index(package, require_tracked=True):
    rows = json.loads((package / "evidence/index.json").read_text())["files"]
    seen = set()
    for row in rows:
        relative = row["path"]
        file = (package / relative).resolve()
        if not file.is_relative_to(package.resolve()) or relative in seen:
            raise ValueError("Escaping/duplicate evidence path: " + relative)
        seen.add(relative)
        blob = file.read_bytes()
        if len(blob) != row["bytes"] or hashlib.sha256(blob).hexdigest() != row["sha256"]:
            raise ValueError("Evidence bytes differ: " + str(file))
        if require_tracked:
            subprocess.run(["git", "ls-files", "--error-unmatch", "--", file.relative_to(ROOT).as_posix()],
                           cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    return len(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--include-recovery", action="store_true")
    args = p.parse_args()
    packages = [ROOT / "phase0", ROOT / "phase0/gpu-feasibility"]
    if args.include_recovery:
        packages.append(ROOT / "phase0/gpu-recovery")
    for package in packages:
        print(str(package.relative_to(ROOT)) + ": PASS " + str(verify_index(package)) + " artifacts (integrity only)")


if __name__ == "__main__":
    main()
