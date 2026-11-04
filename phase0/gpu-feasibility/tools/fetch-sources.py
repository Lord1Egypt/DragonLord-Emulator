#!/usr/bin/env python3
"""Fetch only pinned source trees; never installs native toolchains or builds guests."""
import json
from pathlib import Path
import subprocess

PACKAGE = Path(__file__).resolve().parents[1]
WORK = PACKAGE.parent / ".work"


def main():
    lock = json.loads((PACKAGE / "versions.lock.json").read_text())
    for name in ("gfxstream", "rutabaga"):
        row = lock[name]
        path = WORK / row["directory"]
        if not path.exists():
            subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", row["repository"], str(path)], check=True)
            subprocess.run(["git", "-C", str(path), "checkout", "--detach", row["commit"]], check=True)
        revision = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
        if revision != row["commit"] or subprocess.check_output(["git", "-C", str(path), "diff", "HEAD", "--name-only"], text=True).strip():
            raise SystemExit("Source revision/pristine mismatch: " + name)
        print(name + ": " + revision + " (pristine tracked source)")


if __name__ == "__main__": main()
