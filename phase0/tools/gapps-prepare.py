#!/usr/bin/env python3
"""Build the minimal Google apps bundle (Play Services, Play Store, Services Framework) for the GApps instance option.

  gapps-prepare.py [--zip PATH]

Source: Google's Android 16 x86_64 "Google Play" emulator image from the Android SDK repository (newest x86_64
Play image; no Android 17 one exists). The zip is downloaded and SHA-1 checked if missing. The apps are proprietary
Google software: the bundle is built locally for the user and never committed or redistributed.
Output: phase0/.work/gapps/bundle/ laid out like the guest's partitions (product/..., system_ext/...).
"""
import argparse
import re
import shutil
import struct
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

PHASE = Path(__file__).resolve().parents[1]
WORK = PHASE / ".work/gapps"
URL = "https://dl.google.com/android/repository/sys-img/google_apis_playstore/x86_64-36-ext19_r01.zip"
SHA1 = "68739f41080957209a4a34e1a2e65186d449776f"  # from Google's sys-img2-1.xml index
FSCK_EROFS = PHASE / ".work/cuttlefish/cvd/bin/fsck.erofs"
APPS = {"product": ["priv-app/PrebuiltGmsCore", "priv-app/Phonesky"], "system_ext": ["priv-app/GoogleServicesFramework"]}
SYSCONFIG = ["google.xml", "google-hiddenapi-package-whitelist.xml"]


def sha1(p):
    import hashlib
    h = hashlib.sha1()
    with open(p, "rb") as f:
        while b := f.read(1 << 22):
            h.update(b)
    return h.hexdigest()


def split_super(img, names, out):
    """Copy the named logical partitions out of the image's GPT 'super' partition (linear extents only)."""
    f = open(img, "rb")
    f.seek(512)
    gpt = f.read(92)
    if gpt[:8] != b"EFI PART":
        sys.exit("system.img: no GPT")
    lba, n, size = struct.unpack_from("<QII", gpt, 72)
    f.seek(lba * 512)
    base = None
    for _ in range(n):
        e = f.read(size)
        if e[56:128].decode("utf-16-le").rstrip("\0") == "super":
            base = struct.unpack_from("<Q", e, 32)[0] * 512
    if base is None:
        sys.exit("system.img: no super partition")
    f.seek(base + 3 * 4096)  # reserved bytes, primary and backup geometry
    hdr = f.read(256)
    if struct.unpack_from("<I", hdr, 0)[0] != 0x414C5030:
        sys.exit("super: bad metadata magic")
    header_size, tables_size = struct.unpack_from("<I", hdr, 8)[0], struct.unpack_from("<I", hdr, 44)[0]
    pd, ed = struct.unpack_from("<III", hdr, 80), struct.unpack_from("<III", hdr, 92)
    f.seek(base + 3 * 4096 + header_size)
    t = f.read(tables_size)
    extents = [struct.unpack_from("<QIQI", t, ed[0] + i * ed[2]) for i in range(ed[1])]
    for i in range(pd[1]):
        raw = t[pd[0] + i * pd[2]:pd[0] + (i + 1) * pd[2]]
        name = raw[:36].rstrip(b"\0").decode()
        first, count = struct.unpack_from("<II", raw, 40)
        if name not in names:
            continue
        with open(out / f"{name}.img", "wb") as o:
            for sectors, kind, start, _ in extents[first:first + count]:
                if kind != 0:
                    sys.exit("super: non-linear extent")
                f.seek(base + start * 512)
                left = sectors * 512
                while left:
                    chunk = f.read(min(left, 1 << 22))
                    o.write(chunk)
                    left -= len(chunk)


def privapp_xml(src_dirs, packages):
    """Only the <privapp-permissions> blocks of the given packages, so nothing clashes with the platform's own lists."""
    blocks = []
    for d in src_dirs:
        for x in sorted(d.glob("privapp-permissions-*.xml")):
            for m in re.finditer(r'<privapp-permissions package="([^"]+)">.*?</privapp-permissions>', x.read_text(), re.S):
                if m.group(1) in packages:
                    blocks.append(m.group(0))
    found = {re.search(r'package="([^"]+)"', b).group(1) for b in blocks}
    if found != set(packages):
        sys.exit(f"privapp permissions missing for {set(packages) - found}")
    return '<?xml version="1.0" encoding="utf-8"?>\n<!-- DragonLord GApps option: extracted from Google\'s emulator image -->\n<permissions>\n' + \
        "\n".join(blocks) + "\n</permissions>\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zip", type=Path, default=WORK / "download/x86_64-36-ext19_r01.zip")
    a = ap.parse_args()
    if not a.zip.exists():
        a.zip.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {URL} (1.9 GB)")
        urllib.request.urlretrieve(URL, a.zip)
    if sha1(a.zip) != SHA1:
        sys.exit(f"{a.zip}: SHA-1 mismatch, refusing to use it")
    tmp = WORK / "tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    with zipfile.ZipFile(a.zip) as z:
        z.extract("x86_64/system.img", tmp)
    split_super(tmp / "x86_64/system.img", set(APPS), tmp)
    (tmp / "x86_64/system.img").unlink()
    for part in APPS:
        subprocess.run([str(FSCK_EROFS), f"--extract={tmp / part}", str(tmp / f"{part}.img")], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    bundle = WORK / "bundle"
    shutil.rmtree(bundle, ignore_errors=True)
    for part, apps in APPS.items():
        for app in apps:
            src = tmp / part / app
            dst = bundle / part / app
            dst.mkdir(parents=True)
            for apk in src.glob("*.apk"):  # no oat/: it was compiled for Android 16's runtime
                shutil.copy2(apk, dst / apk.name)
    # Android reads a privileged app's allow-list only from its own partition's etc/permissions
    srcs = [tmp / "product/etc/permissions", tmp / "system_ext/etc/permissions"]
    for part, pkgs in (("product", ("com.google.android.gms", "com.android.vending")), ("system_ext", ("com.google.android.gsf",))):
        perm = bundle / part / "etc/permissions"
        perm.mkdir(parents=True)
        (perm / "privapp-permissions-dragonlord-gapps.xml").write_text(privapp_xml(srcs, pkgs))
    sysc = bundle / "product/etc/sysconfig"
    sysc.mkdir(parents=True)
    for x in SYSCONFIG:
        shutil.copy2(tmp / "product/etc/sysconfig" / x, sysc / x)
    dp = bundle / "product/etc/default-permissions"
    dp.mkdir(parents=True)
    shutil.copy2(tmp / "product/etc/default-permissions/default-permissions.xml", dp / "default-permissions-google.xml")
    shutil.rmtree(tmp)
    files = [p for p in bundle.rglob("*") if p.is_file()]
    print(f"bundle ready: {bundle} ({len(files)} files, {sum(p.stat().st_size for p in files) // 2**20} MB)")
    for p in sorted(files):
        print("  ", p.relative_to(bundle))


if __name__ == "__main__":
    main()
