#!/usr/bin/env python3
"""Check that this Linux/WSL machine can run DragonLord instances; prints one line per check and how to fix it."""
import grp
import os
import shutil
import subprocess
import sys
from pathlib import Path

P = Path(__file__).resolve().parents[1]
W = P / ".work"
CVD = W / "cuttlefish/cvd"
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


check(os.access("/dev/kvm", os.R_OK | os.W_OK), "/dev/kvm usable", "sudo usermod -aG kvm $USER, then restart WSL / log in again")
for g in ("kvm", "render", "cvdnetwork"):
    check(in_group(g), f"member of group {g}", f"sudo groupadd -f {g} && sudo usermod -aG {g} $USER, then log in again")
check(Path("/usr/lib/cuttlefish-common/bin").exists(), "/usr/lib/cuttlefish-common/bin exists (launcher needs it)",
      f"sudo mkdir -p /usr/lib/cuttlefish-common && sudo ln -s {W}/cuttlefish/root/usr/lib/cuttlefish-common/bin /usr/lib/cuttlefish-common/bin")
check((CVD / "bin/launch_cvd").exists(), "Cuttlefish host tools unpacked", "see ANDROID17-WSL-RUNBOOK.md (cvd-host_package.tar.gz)")
check(any(CVD.glob("super.img")) or any(CVD.glob("*.img")), "Android 17 image unpacked", "unzip aosp_cf_x86_64_only_phone-img-16644040.zip into .work/cuttlefish/cvd")
check((W / "qemu-build-gpu/qemu-system-x86_64").exists(), "our QEMU 11.1.3 built", "see runbook: QEMU build")
check((W / "cuttlefish/qemu-ours/qemu-system-x86_64").exists(), "QEMU wrapper installed", "tools/dl-setup.sh")
check((CVD / "bin/run_cvd.real").exists(), "run_cvd wrapper installed (guest internet)", "tools/dl-setup.sh")
check(shutil.which("adb") is not None, "adb on PATH", "sudo apt install adb (or Android platform-tools)")
shm = shutil.disk_usage("/dev/shm").total // 2**20
check(shm >= 4096, f"/dev/shm size {shm} MB (holds guest RAM; total RAM of running instances must fit)",
      "give WSL more memory in .wslconfig, or remount /dev/shm larger")
ksu = (W / "kernelsu/out/init_boot_ksu.img").exists()
print(f"[{'ok' if ksu else 'optional'}] KernelSU root profile" + ("" if ksu else " (run tools/ksu-patch.sh to enable root=ksu)"))
gpu = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True).returncode == 0 if shutil.which("nvidia-smi") else False
print(f"[{'ok' if gpu else 'info'}] host GPU {'found' if gpu else 'not detected: use --gpu software'}")
print("all required checks passed" if not fails else f"{fails} required check(s) missing")
sys.exit(1 if fails else 0)
