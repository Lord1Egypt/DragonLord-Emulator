#!/usr/bin/env python3
"""DragonLord debug harness: run QEMU with every log captured, then scan for errors.

  dlrun.py run  --name N --qemu BIN [--accel kvm|tcg] [--gpu none|virgl-hw|virgl-sw] [--timeout S] [-- extra qemu args]
  dlrun.py scan [RUN_DIR]        # defaults to the latest run; exit 1 if errors found
  dlrun.py android [RUN_DIR] [--serial S]   # pull logcat/dmesg/props/SurfaceFlinger from a booted guest
  dlrun.py latest

Every run lives in ~/DragonLord/runs/<UTC stamp>-<name>/ (outside git) with:
  manifest.json  exact argv, debug env, host/GPU info, QEMU hash/version, repo revision
  qemu.log       QEMU -D log: guest_errors, unimp, cpu_reset, virtio_gpu* trace events
  qemu.stdout / qemu.stderr   process output (virglrenderer and Mesa debug land here)
  serial.log     guest serial console
  qmp-events.jsonl            every QMP event and the reply to each command we send
  gpu-samples.csv            nvidia-smi GPU/memory utilisation and QEMU CPU/RSS every 2 s
  result.json    exit code / signal / duration;  scan.json  findings
"""
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

RUNS = Path.home() / "DragonLord" / "runs"
REPO = Path(__file__).resolve().parents[2]
DEBUG_ENV = {
    "none": {},
    "virgl-hw": {"GALLIUM_DRIVER": "d3d12"},
    "virgl-sw": {"GALLIUM_DRIVER": "llvmpipe", "LIBGL_ALWAYS_SOFTWARE": "1"},
}
COMMON_ENV = {
    "MESA_DEBUG": "1", "LIBGL_DEBUG": "verbose", "EGL_LOG_LEVEL": "debug",
    "VIRGL_LOG_LEVEL": "debug", "G_MESSAGES_DEBUG": "all",
}
FINDINGS = re.compile(
    r"(?i)\b(error|fail(ed|ure)?|fatal|panic|assert(ion)?|segfault|segmentation|oops|bug:|"
    r"guest_error|unimplemented|not implemented|unsupported|invalid|abort(ed)?|"
    r"avc:\s+denied|anr in|fatal exception|tombstone|crash|killed|timeout|timed out|"
    r"lost device|device lost|gpu hang|tdr)\b")
IGNORE = re.compile(r"(?i)(error_report_once|0 errors|no errors|errors=0|fail_count=0|command line:)")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sh(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except Exception as e:  # tool missing or hung: record that, do not hide it
        return f"UNAVAILABLE: {e}"


def latest_run():
    runs = sorted(p for p in RUNS.glob("*") if p.is_dir()) if RUNS.exists() else []
    if not runs:
        sys.exit("no runs yet")
    return runs[-1]


class Qmp:
    """Minimal QMP client that logs every message to the events file."""

    def __init__(self, path, events):
        self.events = events
        self.sock = socket.socket(socket.AF_UNIX)
        for _ in range(100):
            try:
                self.sock.connect(str(path))
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError(f"QMP socket {path} never came up")
        self.f = self.sock.makefile("rw")
        self.log(json.loads(self.f.readline()))
        self.cmd("qmp_capabilities")
        threading.Thread(target=self._pump, daemon=True).start()

    def log(self, msg):
        with open(self.events, "a") as out:
            out.write(json.dumps({"t": time.time(), "msg": msg}) + "\n")

    def _pump(self):
        try:
            for line in self.f:
                self.log(json.loads(line))
        except (OSError, ValueError):
            pass

    def cmd(self, name, **args):
        msg = {"execute": name, **({"arguments": args} if args else {})}
        self.log({"sent": msg})
        self.f.write(json.dumps(msg) + "\n")
        self.f.flush()


def sampler(pid, out, stop):
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "qemu_cpu_pct", "qemu_rss_kb", "gpu_util_pct", "gpu_mem_mib"])
        while not stop.is_set():
            ps = sh(["ps", "-o", "%cpu=,rss=", "-p", str(pid)]).split()
            gpu = sh(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
                      "--format=csv,noheader,nounits"], 5).split(",")
            ps = ps if len(ps) == 2 else ["", ""]
            gpu = [g.strip() for g in gpu] if len(gpu) == 2 else ["", ""]
            w.writerow([f"{time.time():.1f}", *ps, *gpu])
            f.flush()
            stop.wait(2)


def cmd_run(a, extra):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run = RUNS / f"{stamp}-{a.name}"
    run.mkdir(parents=True)
    env = {**os.environ, **COMMON_ENV, **DEBUG_ENV[a.gpu]}
    argv = [a.qemu, "-machine", f"q35,accel={a.accel}", "-m", str(a.mem), "-smp", str(a.smp),
            "-D", str(run / "qemu.log"), "-d", "guest_errors,unimp,cpu_reset",
            "-trace", "virtio_gpu*", "-trace", "virtio_set_status",
            "-serial", f"file:{run / 'serial.log'}",
            "-qmp", f"unix:{run / 'qmp.sock'},server=on,wait=off", "-no-reboot"]
    if a.accel == "kvm":
        argv += ["-cpu", "host"]
    if a.gpu != "none":
        argv += ["-device", "virtio-vga-gl", "-display", a.display + ",gl=on"
                 if a.display != "egl-headless" else "egl-headless"]
    elif a.display == "egl-headless":
        argv += ["-display", "none"]
    else:
        argv += ["-display", a.display]
    argv += extra
    if a.gdb and shutil.which("gdb"):
        argv = ["gdb", "-batch", "-ex", "run", "-ex", "bt full", "-ex", "info threads", "--args"] + argv
    manifest = {
        "argv": argv, "cwd": os.getcwd(), "started_utc": stamp, "gpu_mode": a.gpu,
        "debug_env": {k: v for k, v in env.items() if k in {**COMMON_ENV, **DEBUG_ENV[a.gpu]}},
        "qemu_sha256": sha256(a.qemu), "qemu_version": sh([a.qemu, "--version"]).splitlines()[0],
        "repo_revision": sh(["git", "-C", str(REPO), "rev-parse", "HEAD"]),
        "repo_dirty_files": sh(["git", "-C", str(REPO), "status", "--short"]).splitlines()[:50],
        "host": {"uname": sh(["uname", "-a"]),
                 "cpu": next((l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo")
                              if l.startswith("model name")), ""),
                 "devices": {d: os.path.exists(d) for d in ("/dev/kvm", "/dev/dxg", "/dev/dri/renderD128")},
                 "nvidia_smi": sh(["nvidia-smi", "-L"]),
                 "gl_renderer": next((l.strip() for l in sh(["glxinfo", "-B"], 30).splitlines()
                                      if "OpenGL renderer" in l), "UNAVAILABLE")},
    }
    # glxinfo above ran without the mode's env; record what the guest-facing mode will see.
    manifest["host"]["gl_renderer_in_mode"] = next(
        (l.strip() for l in subprocess.run(["glxinfo", "-B"], env=env, capture_output=True,
                                           text=True).stdout.splitlines() if "OpenGL renderer" in l),
        "UNAVAILABLE")
    (run / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"run dir: {run}", flush=True)

    t0 = time.time()
    proc = subprocess.Popen(argv, env=env, stdout=open(run / "qemu.stdout", "w"),
                            stderr=open(run / "qemu.stderr", "w"))
    stop = threading.Event()
    threading.Thread(target=sampler, args=(proc.pid, run / "gpu-samples.csv", stop), daemon=True).start()
    qmp = None
    try:
        qmp = Qmp(run / "qmp.sock", run / "qmp-events.jsonl")
        proc.wait(timeout=a.timeout)
    except subprocess.TimeoutExpired:
        if qmp:
            qmp.cmd("quit")
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    except RuntimeError as e:
        (run / "harness-error.txt").write_text(str(e) + "\n")
        proc.kill()
        proc.wait()
    stop.set()
    rc = proc.returncode
    (run / "result.json").write_text(json.dumps({
        "exit_code": rc, "signal": signal.Signals(-rc).name if rc < 0 else None,
        "seconds": round(time.time() - t0, 2), "timeout_s": a.timeout}, indent=2) + "\n")
    return scan(run)


def scan(run, show=40):
    findings = []
    for name in ("qemu.log", "qemu.stderr", "qemu.stdout", "serial.log", "harness-error.txt",
                 "android/logcat.txt", "android/dmesg.txt"):
        p = run / name
        if not p.exists():
            continue
        for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
            if FINDINGS.search(line) and not IGNORE.search(line):
                findings.append({"file": name, "line": n, "text": line.strip()[:300]})
    res = json.loads((run / "result.json").read_text()) if (run / "result.json").exists() else {}
    abnormal = res.get("signal") or res.get("exit_code") not in (0, None)
    summary = {"abnormal_exit": bool(abnormal), "finding_count": len(findings), "findings": findings}
    (run / "scan.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"\nscan {run.name}: exit={res.get('exit_code')} signal={res.get('signal')} "
          f"findings={len(findings)}")
    for f in findings[:show]:
        print(f"  {f['file']}:{f['line']}: {f['text']}")
    if len(findings) > show:
        print(f"  ... {len(findings) - show} more in {run / 'scan.json'}")
    return 1 if findings or abnormal else 0


def cmd_android(run, serial):
    out = run / "android"
    out.mkdir(exist_ok=True)
    adb = ["adb"] + (["-s", serial] if serial else [])
    jobs = {"logcat.txt": ["logcat", "-b", "all", "-d", "-v", "threadtime"],
            "dmesg.txt": ["shell", "dmesg"], "getprop.txt": ["shell", "getprop"],
            "surfaceflinger.txt": ["shell", "dumpsys", "SurfaceFlinger"],
            "gpu-gles.txt": ["shell", "dumpsys", "SurfaceFlinger", "|", "grep", "-i", "-E", "GLES|renderer|vendor"],
            "selinux.txt": ["shell", "getenforce"], "su-id.txt": ["shell", "su", "-c", "id"]}
    for fname, args in jobs.items():
        (out / fname).write_text(sh(adb + args, 120) + "\n")
    print(f"android snapshot in {out}")


def main():
    argv = sys.argv[1:]
    extra = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--name", required=True)
    r.add_argument("--qemu", required=True)
    r.add_argument("--accel", choices=["kvm", "tcg"], default="kvm")
    r.add_argument("--gpu", choices=list(DEBUG_ENV), default="none")
    r.add_argument("--display", default="none", help="none|sdl|gtk|egl-headless (gpu modes need a GL display)")
    r.add_argument("--mem", type=int, default=2048)
    r.add_argument("--smp", type=int, default=2)
    r.add_argument("--timeout", type=int, default=120)
    r.add_argument("--gdb", action="store_true", help="run under gdb batch for a full backtrace on crash")
    for name in ("scan", "android"):
        s = sub.add_parser(name)
        s.add_argument("run_dir", nargs="?")
        if name == "android":
            s.add_argument("--serial")
    sub.add_parser("latest")
    a = p.parse_args(argv)
    if a.cmd == "run":
        sys.exit(cmd_run(a, extra))
    if a.cmd == "latest":
        print(latest_run())
        return
    run = Path(a.run_dir) if a.run_dir else latest_run()
    if a.cmd == "scan":
        sys.exit(scan(run))
    cmd_android(run, a.serial)


if __name__ == "__main__":
    main()
