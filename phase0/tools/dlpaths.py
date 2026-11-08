"""Where DragonLord keeps its files.

Release layout (a folder containing a RELEASE file; portable, everything stays inside the folder):
  dragonlord            launcher
  qemu/bin, qemu/lib    our QEMU build and its bundled libraries; qemu/wrapper is what Cuttlefish launches
  tools/                these scripts and the web panel
  data/                 created on first run: android/ (Google's image + host tools), instances/, kernelsu/, gapps/,
                        ui-token. DL_HOME overrides the data folder.
Development layout (the repository): phase0/.work/... and ~/DragonLord/instances, as before.
"""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
RELEASE = (BASE / "RELEASE").exists()

if RELEASE:
    DATA = Path(os.environ.get("DL_HOME") or BASE / "data")
    CVD = DATA / "android"
    QEMU_DIR = BASE / "qemu/wrapper"
    QEMU_REAL = BASE / "qemu/bin/qemu-system-x86_64"
    KSU = DATA / "kernelsu"
    GAPPS = DATA / "gapps"
    INSTANCES = DATA / "instances"
    TOKEN = DATA / "ui-token"
    DOWNLOADS = DATA / "downloads"
else:
    WORK = BASE / ".work"
    DATA = Path.home() / "DragonLord"
    CVD = WORK / "cuttlefish/cvd"
    QEMU_DIR = WORK / "cuttlefish/qemu-ours"
    QEMU_REAL = WORK / "qemu-build-gpu/qemu-system-x86_64"
    KSU = WORK / "kernelsu"
    GAPPS = WORK / "gapps"
    INSTANCES = DATA / "instances"
    TOKEN = DATA / "ui-token"
    DOWNLOADS = WORK / "downloads"

KSU_INIT_BOOT = KSU / "out/init_boot_ksu.img"
KSU_APK = KSU / "KernelSU_v3.3.1_32680-release.apk"
GAPPS_BUNDLE = GAPPS / "bundle"
