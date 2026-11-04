#!/usr/bin/env python3
"""Isolated Ubuntu->Windows CPU diagnostic build. No installed Windows tools changed."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request

PHASE = Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=6)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("jobs must be positive")
    import zstandard
    lock = json.loads((PHASE / "versions.lock.json").read_text())
    deps = json.loads((PHASE / "windows-cross.lock.json").read_text())
    work = PHASE / ".work"
    root, debs, msys, build = [work / n for n in ("cross-root", "cross-debs", "msys-packages", "qemu-build-cross")]
    for p in (root, debs, msys, build):
        p.mkdir(parents=True, exist_ok=True)
    result = {"scope": "Windows CPU diagnostic cross-build, not a GPU build", "status": "FAIL",
              "source": lock["qemu"], "gpu": "NOT_TESTED"}
    start = time.monotonic()
    try:
        for row in deps["ubuntu_packages"]:
            file = debs / row["filename"]
            if not file.exists():
                subprocess.run(["apt-get", "download", row["package"] + "=" + row["version"]], cwd=debs, check=True)
            if sha(file) != row["sha256"]:
                raise ValueError("Debian archive hash mismatch: " + file.name)
            subprocess.run(["dpkg-deb", "-x", str(file), str(root)], check=True)
        for row in deps["msys_packages"]:
            file = msys / row["filename"]
            if not file.exists():
                part = file.with_suffix(file.suffix + ".part")
                with urllib.request.urlopen(row["url"], timeout=60) as src, part.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                if sha(part) != row["sha256"]:
                    raise ValueError("MSYS2 archive hash mismatch: " + part.name)
                part.replace(file)
            if sha(file) != row["sha256"]:
                raise ValueError("MSYS2 archive hash mismatch: " + file.name)
            with file.open("rb") as source, zstandard.ZstdDecompressor().stream_reader(source) as reader:
                with tarfile.open(fileobj=reader, mode="r|") as archive:
                    archive.extractall(root, filter="data")
        for pc in (root / "mingw64").rglob("*.pc"):
            # Rewrite the package prefix once; repeated runs must be idempotent.
            text = pc.read_text()
            text = text.replace("prefix=/mingw64", "prefix=" + str(root / "mingw64"))
            pc.write_text(text)
        overlay = deps["whpx_header_overlay"]
        header = urllib.request.urlopen(overlay["url"], timeout=60).read()
        if hashlib.sha256(header).hexdigest() != overlay["sha256"]:
            raise ValueError("WHPX header overlay checksum mismatch")
        (root / overlay["relative_destination"]).write_bytes(header)
        gcc = root / "usr/bin/x86_64-w64-mingw32-gcc"
        if not gcc.exists():
            gcc.symlink_to("x86_64-w64-mingw32-gcc-posix")
        source = work / ("qemu-" + lock["qemu"]["version"])
        if not source.exists():
            subprocess.run(["git", "clone", "--depth", "1", "--branch", lock["qemu"]["tag"],
                            lock["qemu"]["repository"], str(source)], check=True)
        actual = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
        if actual != lock["qemu"]["commit"] or subprocess.check_output(["git", "-C", str(source), "diff", "HEAD", "--name-only"], text=True).strip():
            raise ValueError("Expected pristine pinned QEMU source")
        env = os.environ.copy()
        env["PATH"] = str(root / "usr/bin") + os.pathsep + str(work / "build-venv/bin") + os.pathsep + env["PATH"]
        env["PKG_CONFIG_PATH"] = str(root / "mingw64/lib/pkgconfig")
        env["PKG_CONFIG_LIBDIR"] = env["PKG_CONFIG_PATH"]
        env["PKG_CONFIG"] = "/usr/bin/pkg-config"
        env["PIP_CACHE_DIR"] = str(work / "pip-cache")
        configure = ["sh", str(source / "configure"), "--target-list=x86_64-softmmu",
                     "--cross-prefix=x86_64-w64-mingw32-", "--without-default-features",
                     "--enable-tcg", "--enable-whpx", "--disable-pixman", "--disable-docs",
                     "--disable-werror", "--disable-plugins", "--disable-guest-agent", "--enable-download"]
        result["configure_argv"] = configure
        with (work / "configure-cross.log").open("w") as log:
            subprocess.run(configure, cwd=build, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        with (work / "build-cross.log").open("w") as log:
            subprocess.run([str(work / "build-venv/bin/ninja"), "-j" + str(args.jobs), "qemu-system-x86_64.exe"],
                           cwd=build, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        # Collect runtime DLLs beside the executable for a portable diagnostic directory.
        dlls = []
        for dll in (root / "mingw64/bin").glob("*.dll"):
            shutil.copy2(dll, build / dll.name)
            dlls.append({"name": dll.name, "sha256": sha(dll)})
        result.update(status="PASS", binary_sha256=sha(build / "qemu-system-x86_64.exe"),
                      duration_seconds=time.monotonic() - start, dlls=dlls)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        result["reason"] = str(exc)
    (work / "build-cross.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
