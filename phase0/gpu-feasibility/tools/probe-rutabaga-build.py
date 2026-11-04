#!/usr/bin/env python3
"""Request Rutabaga in a fresh pinned Windows cross-configure dependency probe.

This CPU-profile configure intentionally retains disabled Pixman from Phase 0.
It is only a library-discovery probe, never a complete graphics build/profile.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

PHASE = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--build-directory", type=Path, help="Fresh isolated configure directory for a replay")
    args = p.parse_args()
    if args.output.exists(): p.error("use a fresh output directory")
    args.output.mkdir(parents=True)
    result = {"scope": "Windows cross-profile Rutabaga dependency probe, not native library execution",
              "status": "BLOCKED", "integration": "NOT TESTED", "gpu": "NOT TESTED"}
    try:
        work = PHASE / ".work"
        cross = work / "cross-root"
        source = work / "qemu-11.1.3"
        pin = json.loads((PHASE / "versions.lock.json").read_text())["qemu"]["commit"]
        assert subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() == pin
        assert not subprocess.check_output(["git", "-C", str(source), "diff", "HEAD", "--name-only"], text=True).strip()
        build = (args.build_directory or (work / "gpu-feasibility/qemu-rutabaga-dependency-probe")).resolve()
        if build.exists(): raise ValueError("Fresh configure build directory required")
        build.mkdir(parents=True)
        env = os.environ.copy()
        env["PATH"] = str(cross / "usr/bin") + os.pathsep + str(work / "build-venv/bin") + os.pathsep + env["PATH"]
        env["PKG_CONFIG_PATH"] = str(cross / "mingw64/lib/pkgconfig")
        env["PKG_CONFIG_LIBDIR"] = env["PKG_CONFIG_PATH"]
        env["PKG_CONFIG"] = "/usr/bin/pkg-config"
        env["PIP_CACHE_DIR"] = str(work / "pip-cache")
        configure = ["sh", str(source / "configure"), "--target-list=x86_64-softmmu", "--cross-prefix=x86_64-w64-mingw32-",
                     "--without-default-features", "--enable-tcg", "--enable-whpx", "--disable-pixman", "--disable-docs",
                     "--disable-werror", "--disable-plugins", "--disable-guest-agent", "--enable-download", "--enable-rutabaga-gfx"]
        result["source_commit"] = pin
        result["configure_argv"] = configure
        run = subprocess.run(configure, cwd=build, env=env, capture_output=True, text=True, timeout=120)
        (args.output / "configure.log").write_text(run.stdout + run.stderr)
        result["configure_exit_code"] = run.returncode
        missing = 'Dependency "rutabaga_gfx_ffi" not found' in run.stdout + run.stderr
        result["missing_rutabaga_dependency_confirmed"] = missing
        result["reason"] = ("Pinned Windows target library rutabaga_gfx_ffi is unavailable" if missing else
                            "Inspect dependency configure output; no integrated build or runtime qualification")
    except (AssertionError, OSError, ValueError, subprocess.SubprocessError) as exc: result["reason"] = str(exc)
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 2


if __name__ == "__main__": sys.exit(main())
