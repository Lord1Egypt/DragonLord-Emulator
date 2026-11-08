#!/usr/bin/env python3
"""First-run setup: download and verify Google's Android 17 Cuttlefish image and host tools, install our wrappers,
optionally build the KernelSU root profile, then check the machine.

  dl-install.py [--no-root] [--gapps]

Every download is pinned by SHA-256 and refused on mismatch. Files land in the data folder (see dlpaths.py).
Steps that need root are never run here: they are printed for the user to run once.
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)  # keep our lines in order with the child processes' output
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dlpaths  # noqa: E402

TOOLS = Path(__file__).resolve().parent
CI = "https://ci.android.com/builds/submitted/16644040/aosp_cf_x86_64_only_phone-userdebug/latest/raw/"
ANDROID = {
    "aosp_cf_x86_64_only_phone-img-16644040.zip": "eccdb248e171af6cb98711a6f2fbd5e5017e9c3a6e82337580181bbd4bb2c41b",
    "cvd-host_package.tar.gz": "ec02c8e23985b37d9769732bf8bed992f10d851f40f7a835cf97128888900ecc",
}
KSU_URL = "https://github.com/tiann/KernelSU/releases/download/v3.3.1/"
KSU = {
    "KernelSU_v3.3.1_32680-release.apk": "b4a059ace71de2fa65cc7f12b1c58d55fc23ab25e057ee4230ce779742abe450",
    "ksud-x86_64-unknown-linux-musl": "29b50f946a3cc40b04aef3dd587adad227fe0f70edf9c56b02c84479f0b0e954",
    "ksuinit-x86_64": "07df433255389dcf015dcec023aabee3d61df82055fa7eb4f66240f5d2c4a9c5",
    "lkm-x86_64-android16-6.12_kernelsu.ko": "12b1efd6a6a71d9f40ddd1f40589905d95658b79206b40145409395d3778962d",
}


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while b := f.read(1 << 22):
            h.update(b)
    return h.hexdigest()


def fetch(url, dst, digest):
    """Download to dst (resuming nothing: a partial file is replaced) and verify; an existing good file is reused."""
    if dst.exists() and sha256(dst) == digest:
        print(f"  ok (cached) {dst.name}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    print(f"  downloading {dst.name} ...", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "dragonlord-setup"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total, done, last = int(r.headers.get("Content-Length") or 0), 0, -1
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            pct = done * 100 // total if total else -1
            if total and pct // 10 != last:
                last = pct // 10
                print(f"    {pct}% of {total // 2**20} MB", flush=True)
    if sha256(tmp) != digest:
        tmp.unlink()
        sys.exit(f"{dst.name}: SHA-256 mismatch, download refused")
    tmp.rename(dst)
    print(f"  ok {dst.name}")


def android():
    cvd = dlpaths.CVD
    marker = cvd / ".dragonlord-installed"
    if marker.exists():
        print("Android 17 image and host tools: already installed")
        return
    print("Android 17 (Cuttlefish build 16644040) image and host tools from ci.android.com:")
    for name, digest in ANDROID.items():
        fetch(CI + name, dlpaths.DOWNLOADS / name, digest)
    cvd.mkdir(parents=True, exist_ok=True)
    print("  unpacking ...", flush=True)
    if not hasattr(tarfile, "tar_filter"):
        sys.exit("this Python has no safe tar extraction (needs 3.8.17+, 3.9.17+, 3.10.12+, 3.11.4+ or 3.12+)")
    with tarfile.open(dlpaths.DOWNLOADS / "cvd-host_package.tar.gz") as t:
        t.extractall(cvd, filter="tar")  # 'tar' filter: no absolute paths or links escaping the folder
    with zipfile.ZipFile(dlpaths.DOWNLOADS / "aosp_cf_x86_64_only_phone-img-16644040.zip") as z:
        for m in z.infolist():
            if m.is_dir() or Path(m.filename).is_absolute() or ".." in Path(m.filename).parts:
                continue
            z.extract(m, cvd)
    run_cvd = cvd / "bin/run_cvd"
    if not (cvd / "bin/run_cvd.real").exists():
        run_cvd.rename(cvd / "bin/run_cvd.real")
    shutil.copy2(TOOLS / "run-cvd-wrapper.sh", run_cvd)
    run_cvd.chmod(0o755)
    marker.write_text("16644040\n")
    print("  installed into", cvd)


def kernelsu():
    if dlpaths.KSU_INIT_BOOT.exists():
        print("KernelSU root profile: already built")
        return
    print("KernelSU v3.3.1 (root profile) from github.com/tiann/KernelSU:")
    for name, digest in KSU.items():
        fetch(KSU_URL + name, dlpaths.KSU / name, digest)
    for name in ("ksud-x86_64-unknown-linux-musl", "ksuinit-x86_64"):
        (dlpaths.KSU / name).chmod(0o755)
    env = {**os.environ, "DL_KSU_DIR": str(dlpaths.KSU), "DL_CVD": str(dlpaths.CVD)}
    subprocess.run(["bash", str(TOOLS / "ksu-patch.sh")], env=env, check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-root", action="store_true", help="skip the KernelSU root profile")
    ap.add_argument("--gapps", action="store_true", help="also build the Google Play bundle (downloads 1.9 GB)")
    a = ap.parse_args()
    free = shutil.disk_usage(dlpaths.DATA.parent if not dlpaths.DATA.exists() else dlpaths.DATA).free // 2**30
    print(f"DragonLord setup, data folder {dlpaths.DATA} ({free} GB free)")
    if free < 12:
        sys.exit("need at least 12 GB free (Android image, downloads and one instance)")
    dlpaths.DATA.mkdir(parents=True, exist_ok=True)
    android()
    if not a.no_root:
        kernelsu()
    if a.gapps:
        subprocess.run([sys.executable, str(TOOLS / "gapps-prepare.py")], check=True)
    print()
    r = subprocess.run([sys.executable, str(TOOLS / "dl-doctor.py")])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
