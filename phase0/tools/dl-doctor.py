#!/usr/bin/env python3
"""Check that this Linux/WSL machine can run DragonLord instances; prints one line per check and how to fix it."""
import grp
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dlpaths  # noqa: E402

TOOLS = Path(__file__).resolve().parent
CVD = dlpaths.CVD
fails = 0


def check(ok, what, fix=""):
    global fails
    print(f"[{'ok' if ok else 'MISSING'}] {what}" + ("" if ok else f"\n          fix: {fix}"))
    fails += not ok


def in_group(name):
    try:
        return grp.getgrnam(name).gr_gid in os.getgroups()
    except KeyError:
        return False


cap = Path("/usr/lib/cuttlefish-common/bin/capability_query.py")
cap_ok = cap.exists() and subprocess.run([sys.executable, str(cap), "qemu_cli", "vsock"], capture_output=True).returncode == 0
check(os.access("/dev/kvm", os.R_OK | os.W_OK), "/dev/kvm usable", "sudo usermod -aG kvm $USER, then log in again (WSL: wsl --shutdown)")
for g in ("kvm", "render", "cvdnetwork"):
    check(in_group(g), f"member of group {g}", f"sudo groupadd -f {g} && sudo usermod -aG {g} $USER, then log in again")
check(cap_ok, "Cuttlefish capability check answers qemu_cli and vsock",
      f"sudo mkdir -p {cap.parent} && sudo install -m 755 {TOOLS / 'capability_query.py'} {cap}")
check((CVD / "bin/launch_cvd").exists() and any(CVD.glob("*.img")), "Android 17 image and Cuttlefish host tools installed",
      "./dragonlord setup" if dlpaths.RELEASE else "see ANDROID17-WSL-RUNBOOK.md, then tools/dl-setup.sh")
check(dlpaths.QEMU_REAL.exists(), "QEMU 11.1.3 build present", "re-extract the release" if dlpaths.RELEASE else "see runbook: QEMU build")
check((dlpaths.QEMU_DIR / "qemu-system-x86_64").exists(), "QEMU wrapper installed",
      "re-extract the release" if dlpaths.RELEASE else "tools/dl-setup.sh")
check((CVD / "bin/run_cvd.real").exists(), "run_cvd wrapper installed (guest internet)",
      "./dragonlord setup" if dlpaths.RELEASE else "tools/dl-setup.sh")
check(shutil.which("adb") is not None or (CVD / "bin/adb").exists(), "adb available", "comes with the host tools: ./dragonlord setup")
check(shutil.which("python3") is not None, "python3 available", "install python3")
shm = shutil.disk_usage("/dev/shm").total // 2**20
check(shm >= 4096, f"/dev/shm size {shm} MB (holds guest RAM; total RAM of running instances must fit)",
      "give WSL more memory in .wslconfig, or remount /dev/shm larger")
ksu = dlpaths.KSU_INIT_BOOT.exists()
print(f"[{'ok' if ksu else 'optional'}] KernelSU root profile" + ("" if ksu else " (./dragonlord setup builds it unless --no-root)"))
gapps = dlpaths.GAPPS_BUNDLE.exists()
print(f"[{'ok' if gapps else 'optional'}] Google Play bundle" + ("" if gapps else " (./dragonlord gapps)"))
gpu = shutil.which("nvidia-smi") and subprocess.run(["nvidia-smi", "-L"], capture_output=True).returncode == 0
print(f"[{'ok' if gpu else 'info'}] host GPU {'found' if gpu else 'not detected by nvidia-smi: GPU mode may still work through Mesa, else use software'}")
print("all required checks passed" if not fails else f"{fails} required check(s) missing")
sys.exit(1 if fails else 0)
