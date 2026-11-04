#!/usr/bin/env python3
"""Build an isolated, pinned, CPU/serial diagnostic QEMU, not a graphics engine."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

PHASE = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("linux", "windows"), required=True,
                        help="windows must be run in native MSYS2 MINGW64, not WSL")
    parser.add_argument("--jobs", type=int, default=6)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("jobs must be positive")
    work = PHASE / ".work"
    work.mkdir(exist_ok=True)
    out = work / f"qemu-build-{args.host}"
    out.mkdir(exist_ok=True)
    lock = json.loads((PHASE / "versions.lock.json").read_text())["qemu"]
    source = work / ("qemu-" + lock["version"])
    result = {"scope": "clean upstream CPU/serial build", "status": "BLOCKED",
              "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "host_profile": args.host, "source": lock, "gpu_acceleration": "NOT_TESTED"}
    env = os.environ.copy()
    if args.host == "windows" and env.get("MSYSTEM") != "MINGW64":
        result["reason"] = "Run in native Windows MSYS2 MINGW64 with WHPX SDK headers"
    else:
        if args.host == "linux":
            env["PATH"] = str(work / "build-venv/bin") + os.pathsep + env["PATH"]
            pc = work / "sysroot/usr/lib/x86_64-linux-gnu/pkgconfig"
            if pc.exists():
                env["PKG_CONFIG_PATH"] = str(pc) + (os.pathsep + env["PKG_CONFIG_PATH"] if env.get("PKG_CONFIG_PATH") else "")
                env["LD_LIBRARY_PATH"] = str(work / "sysroot/usr/lib/x86_64-linux-gnu")
        env["PIP_CACHE_DIR"] = str(work / "pip-cache")
        try:
            if not source.exists():
                subprocess.run(["git", "clone", "--depth", "1", "--branch", lock["tag"],
                                lock["repository"], str(source)], check=True)
            actual = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
            if actual != lock["commit"]:
                raise RuntimeError("Source commit does not match lock; refusing build")
            # Build only the pinned pristine source; ignored Meson subprojects are allowed.
            if subprocess.check_output(["git", "-C", str(source), "diff", "HEAD", "--name-only"], text=True).strip():
                raise RuntimeError("Upstream source has tracked modifications")
            configure = ["sh", str(source / "configure"), "--target-list=x86_64-softmmu",
                         "--without-default-features", "--enable-tcg", "--enable-pixman",
                         "--disable-docs", "--disable-werror", "--disable-plugins",
                         "--disable-guest-agent", "--enable-download"]
            configure += ["--enable-kvm"] if args.host == "linux" else ["--cross-prefix=x86_64-w64-mingw32-", "--enable-whpx"]
            result["configure_argv"] = configure
            start = time.monotonic()
            with (work / f"configure-{args.host}.log").open("w") as log:
                subprocess.run(configure, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
            # QEMU's generated Makefile resolves the configured Ninja binary.
            command = ["make", "-j" + str(args.jobs), "qemu-system-x86_64" + (".exe" if args.host == "windows" else "")]
            result["build_argv"] = command
            with (work / f"build-{args.host}.log").open("w") as log:
                subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
            binary = out / ("qemu-system-x86_64" + (".exe" if args.host == "windows" else ""))
            result.update(status="PASS", build_seconds=time.monotonic() - start,
                          binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                          version_output=subprocess.check_output([str(binary), "--version"], env=env, text=True))
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            result.update(status="FAIL", reason=str(exc))
    target = work / f"build-{args.host}.json"
    target.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return {"PASS": 0, "BLOCKED": 2, "FAIL": 1}[result["status"]]

if __name__ == "__main__":
    sys.exit(main())
