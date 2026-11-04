#!/usr/bin/env python3
"""Prepare local build tools/development headers on Ubuntu 24.04 without sudo."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

PHASE = Path(__file__).resolve().parents[1]

def main():
    lock = json.loads((PHASE / "versions.lock.json").read_text())
    release = Path("/etc/os-release").read_text()
    if 'ID=ubuntu' not in release or 'VERSION_ID="24.04"' not in release:
        raise SystemExit("BLOCKED: this optional dependency bootstrap is pinned to Ubuntu 24.04")
    work = PHASE / ".work"
    debs, sysroot, venv = [work / p for p in ("debs", "sysroot", "build-venv")]
    for p in (work, debs, sysroot):
        p.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PIP_CACHE_DIR"] = str(work / "pip-cache")
    if not (venv / "bin/python").exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    subprocess.run([str(venv / "bin/python"), "-m", "pip", "install",
                    *lock["python_build_tools"]], env=env, check=True)
    subprocess.run(["apt-get", "download", *lock["ubuntu_24_04_local_debs"]], cwd=debs, check=True)
    evidence = []
    for p in sorted(debs.glob("*.deb")):
        subprocess.run(["dpkg-deb", "-x", str(p), str(sysroot)], check=True)
        evidence.append({"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    for p in sysroot.rglob("*.pc"):
        p.write_text(p.read_text().replace("prefix=/usr", f"prefix={sysroot}/usr"))
    (work / "local-dependencies.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print("Local dependencies prepared; no system packages installed. Run build-qemu.py --host linux.")

if __name__ == "__main__":
    main()
