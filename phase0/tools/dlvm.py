#!/usr/bin/env python3
"""DragonLord instance manager prototype (Linux/WSL test bench; the Windows port needs its own supervisor).

  dlvm.py create NAME [--ram MB] [--cpus N] [--disk MB] [--gpu gfxstream|software] [--root off|ksu]
                      [--serial S] [--dpi N] [--res WxH]
  dlvm.py start NAME | stop NAME | status [NAME] | list | delete NAME | logs NAME

Each instance lives in ~/DragonLord/instances/NAME/ (instance.json, HOME of its Cuttlefish run, logs/).
Shared read-only inputs: phase0/.work/cuttlefish/cvd (host tools + Android image), qemu-ours (QEMU wrapper),
phase0/.work/kernelsu/out/init_boot_ksu.img (root profile). Stop is graceful: sync, then stop_cvd.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PHASE = Path(__file__).resolve().parents[1]
CVD = PHASE / ".work/cuttlefish/cvd"
QEMU_DIR = PHASE / ".work/cuttlefish/qemu-ours"
KSU_INIT_BOOT = PHASE / ".work/kernelsu/out/init_boot_ksu.img"
ROOT = Path.home() / "DragonLord" / "instances"
DEFAULTS = {"ram": 4096, "cpus": 4, "disk": 8192, "gpu": "gfxstream", "root": "off",
            "serial": None, "dpi": 320, "res": "720x1280"}


def inst_dir(name):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", name):
        sys.exit("instance name: 1-32 letters, digits, - or _")
    return ROOT / name


def load(name):
    p = inst_dir(name) / "instance.json"
    if not p.exists():
        sys.exit(f"no such instance: {name}")
    return json.loads(p.read_text())


def save(cfg):
    (inst_dir(cfg["name"]) / "instance.json").write_text(json.dumps(cfg, indent=2) + "\n")


def next_number():
    used = {json.loads(p.read_text()).get("number") for p in ROOT.glob("*/instance.json")}
    return next(n for n in range(1, 100) if n not in used)


def adb_serial(cfg):
    return f"127.0.0.1:{6520 + cfg['number'] - 1}"


def mem_path(cfg):
    return f"/dev/shm/dl-{cfg['name']}.mem"


def running(cfg):
    pid = cfg.get("pid")
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def cmd_create(a):
    d = inst_dir(a.name)
    if d.exists():
        sys.exit(f"instance exists: {a.name}")
    if a.ram < 1024 or a.ram > 16384 or a.cpus < 1 or a.cpus > 16 or a.disk < 2048:
        sys.exit("limits: ram 1024-16384 MB, cpus 1-16, disk >= 2048 MB")
    if not re.fullmatch(r"\d{3,5}x\d{3,5}", a.res):
        sys.exit("res must look like 720x1280")
    if any(not re.fullmatch(r"-[A-Za-z0-9_]+(=[A-Za-z0-9_./:,@-]*)?", f) for f in (a.extra or [])):
        sys.exit("--extra must look like -flag or -flag=value (letters, digits and _ . / : , @ - only)")
    if a.root == "ksu" and not KSU_INIT_BOOT.exists():
        sys.exit(f"missing {KSU_INIT_BOOT}; run phase0/tools/ksu-patch.sh")
    ROOT.mkdir(parents=True, exist_ok=True)
    (d / "logs").mkdir(parents=True)
    cfg = {"name": a.name, "number": next_number(), "ram": a.ram, "cpus": a.cpus, "disk": a.disk,
           "gpu": a.gpu, "root": a.root, "serial": a.serial, "dpi": a.dpi, "res": a.res, "pid": None, "data_created": False, "extra": a.extra or []}
    save(cfg)
    print(f"created {a.name} (instance number {cfg['number']}, adb {adb_serial(cfg)})")


def build_cmd(cfg):
    w, h = cfg["res"].split("x")
    cmd = [str(CVD / "bin/launch_cvd"), "-vm_manager=qemu_cli", f"-qemu_binary_dir={QEMU_DIR}",
           f"-system_image_dir={CVD}", f"-base_instance_num={cfg['number']}",
           f"-gpu_mode={'gfxstream' if cfg['gpu'] == 'gfxstream' else 'guest_swiftshader'}",
           f"-memory_mb={cfg['ram']}", f"-cpus={cfg['cpus']}", f"-blank_data_image_mb={cfg['disk']}",
           f"-dpi={cfg['dpi']}", f"-x_res={w}", f"-y_res={h}", "-start_webrtc=false", "-daemon=false",
           "-report_anonymous_usage_stats=n", "-use_allocd=false", "-console=true"]
    # first start creates the data disk at the requested size; later starts keep the existing disk
    cmd.append("-data_policy=" + ("use_existing" if cfg.get("data_created", True) else "always_create"))
    if cfg.get("serial"):
        cmd.append(f"-serial_number={cfg['serial']}")
    if cfg["root"] == "ksu":
        cmd.append(f"-init_boot_image={KSU_INIT_BOOT}")
    cmd += cfg.get("extra", [])  # advanced launch_cvd flags, e.g. -device_external_network=slirp
    return cmd


def cmd_start(a):
    cfg = load(a.name)
    if running(cfg):
        sys.exit("already running")
    d = inst_dir(a.name)
    env = {**os.environ, "HOME": str(d), "ANDROID_HOST_OUT": str(CVD), "DL_MEM_PATH": mem_path(cfg),
           "DL_NET": "user"}  # user-mode networking: no root-created TAP devices
    if cfg["gpu"] == "gfxstream":
        env["GALLIUM_DRIVER"] = "d3d12"
    log = d / "logs/launch.stderr"
    p = subprocess.Popen(build_cmd(cfg), cwd=d, env=env, stdout=open(d / "logs/launch.stdout", "w"),
                         stderr=open(log, "w"), start_new_session=True)
    cfg["pid"] = p.pid
    save(cfg)
    end = time.time() + a.timeout
    while time.time() < end:
        if p.poll() is not None:
            cfg["pid"] = None
            save(cfg)
            sys.exit(f"launcher exited early (code {p.returncode}); see {log}")
        if "VIRTUAL_DEVICE_BOOT_COMPLETED" in log.read_text(errors="replace"):
            subprocess.run(["adb", "connect", adb_serial(cfg)], capture_output=True)
            cfg["data_created"] = True
            save(cfg)
            print(f"{a.name}: boot completed in {time.time() - (end - a.timeout):.0f}s, adb {adb_serial(cfg)}")
            return
        time.sleep(3)
    sys.exit("boot timeout")


def cmd_stop(a):
    cfg = load(a.name)
    d = inst_dir(a.name)
    ser = adb_serial(cfg)
    if running(cfg):
        subprocess.run(["adb", "-s", ser, "shell", "sync; sleep 2; sync"], capture_output=True, timeout=60)
    env = {**os.environ, "HOME": str(d), "ANDROID_HOST_OUT": str(CVD)}
    subprocess.run([str(CVD / "bin/stop_cvd")], cwd=d, env=env,
                   capture_output=True, timeout=120)
    subprocess.run(["adb", "disconnect", ser], capture_output=True)
    Path(mem_path(cfg)).unlink(missing_ok=True)
    for _ in range(30):  # stop_cvd sends SIGKILL; wait until nothing of this instance is left
        left = subprocess.run(["pgrep", "-f", f"{d}/|--instance_dir={d}|qemu_cvd_home={d}"], capture_output=True, text=True).stdout.split()
        left = [p for p in left if int(p) != os.getpid()]
        if not left and not running(cfg):
            break
        time.sleep(1)
    cfg["pid"] = None
    save(cfg)
    print(f"{a.name}: stopped")


def cmd_status(a):
    names = [a.name] if a.name else sorted(p.parent.name for p in ROOT.glob("*/instance.json"))
    for n in names:
        c = load(n)
        print(f"{n:16} #{c['number']}  {'RUNNING' if running(c) else 'stopped':8} ram={c['ram']} cpus={c['cpus']} "
              f"disk={c['disk']} gpu={c['gpu']} root={c['root']} res={c['res']}@{c['dpi']} adb={adb_serial(c)}")


def cmd_delete(a):
    cfg = load(a.name)
    if running(cfg):
        cmd_stop(a)
    shutil.rmtree(inst_dir(a.name))
    print(f"{a.name}: deleted")


def cmd_logs(a):
    print(inst_dir(a.name) / "logs")
    for p in sorted((inst_dir(a.name) / "logs").glob("*")):
        print(" ", p.name, p.stat().st_size)
    for p in (inst_dir(a.name) / "cuttlefish/instances").glob("cvd-*/logs"):
        print("  cuttlefish logs:", p)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("name")
    c.add_argument("--ram", type=int, default=DEFAULTS["ram"])
    c.add_argument("--cpus", type=int, default=DEFAULTS["cpus"])
    c.add_argument("--disk", type=int, default=DEFAULTS["disk"])
    c.add_argument("--gpu", choices=["gfxstream", "software"], default=DEFAULTS["gpu"])
    c.add_argument("--root", choices=["off", "ksu"], default=DEFAULTS["root"])
    c.add_argument("--serial")
    c.add_argument("--dpi", type=int, default=DEFAULTS["dpi"])
    c.add_argument("--res", default=DEFAULTS["res"])
    c.add_argument("--extra", action="append", metavar="FLAG", help="extra launch_cvd flag (repeatable)")
    s = sub.add_parser("start")
    s.add_argument("name")
    s.add_argument("--timeout", type=int, default=600)
    for n in ("stop", "delete", "logs"):
        sub.add_parser(n).add_argument("name")
    sub.add_parser("status").add_argument("name", nargs="?")
    sub.add_parser("list")
    a = ap.parse_args()
    {"create": cmd_create, "start": cmd_start, "stop": cmd_stop, "status": cmd_status, "list": cmd_status,
     "delete": cmd_delete, "logs": cmd_logs}[a.cmd](a if a.cmd != "list" else argparse.Namespace(name=None))


if __name__ == "__main__":
    main()
