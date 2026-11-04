#!/usr/bin/env python3
"""Fetch exact source pins required by the callback tests; install nothing."""
from pathlib import Path
import subprocess

PHASE = Path(__file__).resolve().parents[2]
SOURCES = [
    ("qemu-11.1.3", "https://gitlab.com/qemu-project/qemu.git", "005c61c0ef6f6ae615283440b4bb7be51b2c6ddd"),
    ("rutabaga-gpu-feasibility", "https://github.com/magma-gpu/rutabaga_gfx.git", "4f2bcaf71a6497583362ed664d9fe21cc5043049"),
]


def main():
    for directory, url, pin in SOURCES:
        path = PHASE / ".work" / directory
        if not path.exists():
            path.mkdir(parents=True)
            subprocess.run(["git", "init", str(path)], check=True)
            subprocess.run(["git", "-C", str(path), "remote", "add", "origin", url], check=True)
            subprocess.run(["git", "-C", str(path), "fetch", "--depth", "1", "origin", pin], check=True)
            subprocess.run(["git", "-C", str(path), "checkout", "--detach", pin], check=True)
        revision = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
        if revision != pin or subprocess.check_output(["git", "-C", str(path), "diff", "HEAD", "--name-only"], text=True).strip():
            raise SystemExit("Source pin/pristine mismatch: " + directory)
        print(directory + ": " + revision)


if __name__ == "__main__":
    main()
