#!/usr/bin/env python3
"""Fetch exact source pins required by the callback tests; install nothing."""
from pathlib import Path
import subprocess
import argparse

PHASE = Path(__file__).resolve().parents[2]
SOURCES = [
    ("qemu-11.1.3", "https://gitlab.com/qemu-project/qemu.git", "005c61c0ef6f6ae615283440b4bb7be51b2c6ddd"),
    ("rutabaga-gpu-feasibility", "https://github.com/magma-gpu/rutabaga_gfx.git", "4f2bcaf71a6497583362ed664d9fe21cc5043049"),
]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native', action='store_true', help='Also fetch pinned Gfxstream and GoogleTest')
    a = p.parse_args()
    sources = list(SOURCES)
    if a.native:
        sources += [
            ('gfxstream-gpu-feasibility', 'https://github.com/google/gfxstream.git', '94240f814c0097a63027ae680ea4bec7b0cb25f7'),
            ('gpu-recovery/googletest', 'https://github.com/google/googletest.git', '52eb8108c5bdec04579160ae17225d66034bd723'),
        ]
    for directory, url, pin in sources:
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
