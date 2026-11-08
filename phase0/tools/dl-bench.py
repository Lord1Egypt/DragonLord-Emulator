#!/usr/bin/env python3
"""Boot the Cuttlefish Android guest in each graphics mode and run one fixed UI workload.

  dl-bench.py --modes guest_swiftshader gfxstream --reps 2

Per run it writes ~/DragonLord/runs/<stamp>-bench-<mode>-<rep>/ with launch logs, gpu-samples.csv,
frames.txt (raw gfxinfo), end.png and result.json. A summary table is printed at the end.
Workload: scroll the Settings list SWIPES times on the device itself (one adb shell, no per-swipe
adb latency). Frame times come from `dumpsys gfxinfo com.android.settings`, throughput from the
wall time of the fixed workload. GPU use comes from nvidia-smi every second.
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

PHASE = Path(__file__).resolve().parents[1]
CVD = PHASE / ".work/cuttlefish/cvd"
QEMU_DIR = PHASE / ".work/cuttlefish/qemu-ours"
RUNS = Path.home() / "DragonLord" / "runs"
SERIAL = "127.0.0.1:6520"
MODE_ENV = {"guest_swiftshader": {}, "gfxstream": {"GALLIUM_DRIVER": "d3d12"}}


def adb(*args, timeout=120, check=False):
    r = subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True, text=True, timeout=timeout)
    if check and r.returncode:
        raise RuntimeError(f"adb {args}: {r.stderr.strip()}")
    return r.stdout


def gpu_sampler(path, stop):
    with open(path, "w") as f:
        f.write("t,util_pct,mem_mib\n")
        while not stop.is_set():
            r = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
                                "--format=csv,noheader,nounits"], capture_output=True, text=True)
            vals = [v.strip() for v in r.stdout.split(",")]
            if len(vals) == 2:
                f.write(f"{time.time():.1f},{vals[0]},{vals[1]}\n")
                f.flush()
            stop.wait(1)


def wait_for(path, needles, proc, timeout):
    end = time.time() + timeout
    while time.time() < end:
        if proc.poll() is not None:
            return "exited"
        text = path.read_text(errors="replace") if path.exists() else ""
        for n in needles:
            if n in text:
                return n
        time.sleep(2)
    return "timeout"


def run_once(mode, rep, swipes, mem, cpus):
    run = RUNS / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-bench-{mode}-{rep}"
    run.mkdir(parents=True)
    env = {**os.environ, "HOME": str(CVD), **MODE_ENV[mode]}
    cmd = [str(CVD / "bin/launch_cvd"), "-vm_manager=qemu_cli", f"-qemu_binary_dir={QEMU_DIR}",
           f"-gpu_mode={mode}", "-start_webrtc=false", "-daemon=false",
           "-report_anonymous_usage_stats=n", "-use_allocd=false", f"-memory_mb={mem}",
           f"-cpus={cpus}", "-console=true"]
    result = {"mode": mode, "rep": rep, "swipes": swipes, "cmd": cmd, "env": MODE_ENV[mode]}
    stop = threading.Event()
    threading.Thread(target=gpu_sampler, args=(run / "gpu-samples.csv", stop), daemon=True).start()
    t_launch = time.time()
    proc = subprocess.Popen(cmd, cwd=CVD, env=env, stdout=open(run / "launch.stdout", "w"),
                            stderr=open(run / "launch.stderr", "w"))
    try:
        got = wait_for(run / "launch.stderr", ["VIRTUAL_DEVICE_BOOT_COMPLETED"], proc, 480)
        result["boot"] = got
        if got != "VIRTUAL_DEVICE_BOOT_COMPLETED":
            raise RuntimeError(f"boot did not complete: {got}")
        result["boot_seconds"] = round(time.time() - t_launch, 1)
        subprocess.run(["adb", "connect", SERIAL], capture_output=True)
        time.sleep(3)
        result["android"] = adb("shell", "getprop ro.build.version.release").strip()
        adb("shell", "svc power stayon true; input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard; "
                     "input swipe 360 1100 360 300 200; sleep 2")
        time.sleep(15)  # let the freshly booted system settle
        adb("shell", "am start -n com.android.settings/.Settings; sleep 5")
        renderer = [l.strip() for l in adb("shell", "dumpsys SurfaceFlinger").splitlines() if "GLES:" in l]
        result["renderer"] = renderer[0] if renderer else "UNKNOWN"
        adb("shell", "dumpsys gfxinfo com.android.settings reset")
        t0 = time.time()
        adb("shell", f"for i in $(seq 1 {swipes}); do input swipe 360 900 360 400 150; "
                     f"input swipe 360 400 360 900 150; done", timeout=900)
        t1 = time.time()
        result["workload_seconds"] = round(t1 - t0, 1)
        frames = adb("shell", "dumpsys gfxinfo com.android.settings")
        (run / "frames.txt").write_text(frames)
        m = re.search(r"Total frames rendered: (\d+)", frames)
        result["frames"] = int(m.group(1)) if m else None
        m = re.search(r"Janky frames: (\d+) \(([\d.]+)%\)", frames)
        result["janky_pct"] = float(m.group(2)) if m else None
        for p in (50, 90, 95, 99):
            m = re.search(rf"^{p}th percentile: (\d+)ms", frames, re.M)
            result[f"p{p}_ms"] = int(m.group(1)) if m else None
        with open(run / "end.png", "wb") as f:
            f.write(subprocess.run(["adb", "-s", SERIAL, "exec-out", "screencap", "-p"],
                                   capture_output=True).stdout)
        result["screenshot_bytes"] = (run / "end.png").stat().st_size
        util = []
        for line in (run / "gpu-samples.csv").read_text().splitlines()[1:]:
            t, u, _ = line.split(",")
            if t0 <= float(t) <= t1:
                util.append(float(u))
        result["gpu_util_avg_pct"] = round(statistics.mean(util), 1) if util else None
        result["gpu_util_max_pct"] = max(util) if util else None
        result["ok"] = True
    except Exception as e:  # keep the failure in the record, then clean up
        result["ok"] = False
        result["error"] = str(e)
    finally:
        stop.set()
        subprocess.run([str(CVD / "bin/stop_cvd")], cwd=CVD, env=env, capture_output=True, timeout=120)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
        Path("/dev/shm/dragonlord-cvd-1.mem").unlink(missing_ok=True)  # guest RAM file, set by the qemu-ours wrapper
        (run / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return run, result


def v(r, key):
    return '-' if r.get(key) is None else r[key]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", nargs="+", default=["guest_swiftshader", "gfxstream"], choices=list(MODE_ENV))
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--swipes", type=int, default=60)
    ap.add_argument("--memory-mb", type=int, default=4096)
    ap.add_argument("--cpus", type=int, default=4)
    a = ap.parse_args()
    rows = []
    for rep in range(1, a.reps + 1):
        for mode in a.modes:
            for attempt in (1, 2):  # a guest dependency check (e.g. Bluetooth) occasionally flakes at boot
                run, r = run_once(mode, rep, a.swipes, a.memory_mb, a.cpus)
                r["attempt"] = attempt
                if r.get("ok") or not str(r.get("error", "")).startswith("boot did not complete"):
                    break
                print(f"{mode} rep{rep}: boot failed on attempt {attempt}, retrying", flush=True)
            print(f"{mode} rep{rep}: ok={r.get('ok')} {r.get('error', '')}  -> {run}", flush=True)
            rows.append(r)
    print(f"\n{'mode':18}{'rep':>4}{'boot_s':>8}{'work_s':>8}{'frames':>8}{'jank%':>7}{'p50':>6}{'p90':>6}{'p99':>6}{'gpu_avg':>8}{'gpu_max':>8}")
    for r in rows:
        print(f"{r['mode']:18}{r['rep']:>4}{v(r, 'boot_seconds'):>8}{v(r, 'workload_seconds'):>8}"
              f"{v(r, 'frames'):>8}{v(r, 'janky_pct'):>7}{v(r, 'p50_ms'):>6}"
              f"{v(r, 'p90_ms'):>6}{v(r, 'p99_ms'):>6}{v(r, 'gpu_util_avg_pct'):>8}"
              f"{v(r, 'gpu_util_max_pct'):>8}")
    sys.exit(0 if all(r.get("ok") for r in rows) else 1)


if __name__ == "__main__":
    main()
