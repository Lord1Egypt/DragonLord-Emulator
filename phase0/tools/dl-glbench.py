#!/usr/bin/env python3
"""Boot the guest per graphics mode and run the native GLES benchmark (tools/glbench) inside it.

  dl-glbench.py --modes guest_swiftshader gfxstream --reps 3 --iters 16 64 [--init-boot PATH]

Writes ~/DragonLord/runs/<stamp>-glbench-<mode>-<rep>/ (launch logs, gpu-samples.csv, result.json) and
prints a summary table. Needs tools/glbench/glbench built with the NDK (see glbench.c header).
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
BIN = PHASE / "tools/glbench/glbench"
RUNS = Path.home() / "DragonLord" / "runs"
SERIAL = "127.0.0.1:6520"
MODE_ENV = {"guest_swiftshader": {}, "gfxstream": {"GALLIUM_DRIVER": "d3d12"}}


def adb(*args, timeout=300):
    r = subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True, text=True, timeout=timeout)
    return r.stdout + r.stderr


def sampler(path, stop):
    with open(path, "w") as f:
        f.write("t,util_pct,mem_mib\n")
        while not stop.is_set():
            r = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
                                "--format=csv,noheader,nounits"], capture_output=True, text=True)
            v = [x.strip() for x in r.stdout.split(",")]
            if len(v) == 2:
                f.write(f"{time.time():.1f},{v[0]},{v[1]}\n")
                f.flush()
            stop.wait(1)


def run_once(mode, rep, iters, frames, init_boot):
    run = RUNS / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-glbench-{mode}-{rep}"
    run.mkdir(parents=True)
    env = {**os.environ, "HOME": str(CVD), **MODE_ENV[mode]}
    cmd = [str(CVD / "bin/launch_cvd"), "-vm_manager=qemu_cli", f"-qemu_binary_dir={QEMU_DIR}",
           f"-gpu_mode={mode}", "-start_webrtc=false", "-daemon=false", "-report_anonymous_usage_stats=n",
           "-use_allocd=false", "-memory_mb=4096", "-cpus=4", "-console=true"]
    if init_boot:
        cmd.append(f"-init_boot_image={init_boot}")
    result = {"mode": mode, "rep": rep, "init_boot": init_boot or "stock", "runs": []}
    stop = threading.Event()
    threading.Thread(target=sampler, args=(run / "gpu-samples.csv", stop), daemon=True).start()
    proc = subprocess.Popen(cmd, cwd=CVD, env=env, stdout=open(run / "launch.stdout", "w"),
                            stderr=open(run / "launch.stderr", "w"))
    try:
        end = time.time() + 480
        while time.time() < end and proc.poll() is None:
            if "VIRTUAL_DEVICE_BOOT_COMPLETED" in (run / "launch.stderr").read_text(errors="replace"):
                break
            time.sleep(3)
        else:
            raise RuntimeError("boot did not complete")
        subprocess.run(["adb", "connect", SERIAL], capture_output=True)
        time.sleep(20)  # let the freshly booted system settle
        adb("push", str(BIN), "/data/local/tmp/glbench")
        adb("shell", "chmod 755 /data/local/tmp/glbench")
        for it in iters:
            for k in range(3):
                t0 = time.time()
                out = adb("shell", f"/data/local/tmp/glbench 1280 720 {frames} {it}", timeout=900).strip()
                t1 = time.time()
                m = dict(re.findall(r'(\w+)=("[^"]*"|\S+)', out))
                util = []
                for line in (run / "gpu-samples.csv").read_text().splitlines()[1:]:
                    t, u, _ = line.split(",")
                    if t0 <= float(t) <= t1:
                        util.append(float(u))
                result["runs"].append({"iter": it, "raw": out, "avg_ms": float(m["avg_ms"]) if "avg_ms" in m else None,
                                       "fps": float(m["fps"]) if "fps" in m else None,
                                       "worst_ms": float(m["worst_ms"]) if "worst_ms" in m else None,
                                       "checksum": m.get("checksum"), "renderer": m.get("renderer"),
                                       "gpu_util_avg": round(statistics.mean(util), 1) if util else None,
                                       "gpu_util_max": max(util) if util else None})
        result["ok"] = True
    except Exception as e:
        result["ok"] = False
        result["error"] = str(e)
    finally:
        stop.set()
        subprocess.run([str(CVD / "bin/stop_cvd")], cwd=CVD, env=env, capture_output=True, timeout=120)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
        Path("/dev/shm/dragonlord-cvd-1.mem").unlink(missing_ok=True)
        (run / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return run, result


def main():
    global iters
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", nargs="+", default=["guest_swiftshader", "gfxstream"], choices=list(MODE_ENV))
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--iters", nargs="+", type=int, default=[16, 64])
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--init-boot")
    a = ap.parse_args()
    iters = a.iters
    rows = []
    for rep in range(1, a.reps + 1):
        for mode in a.modes:
            run, r = run_once(mode, rep, a.iters, a.frames, a.init_boot)
            print(f"{mode} rep{rep}: ok={r.get('ok')} {r.get('error', '')} -> {run}", flush=True)
            rows.append(r)
    print(f"\n{'mode':18}{'rep':>4}{'iter':>6}{'avg_ms':>9}{'fps':>8}{'worst':>8}{'gpu_avg':>8}{'gpu_max':>8}  checksum  renderer")
    for r in rows:
        for x in r["runs"]:
            print(f"{r['mode']:18}{r['rep']:>4}{x['iter']:>6}{str(x['avg_ms']):>9}{str(x['fps']):>8}"
                  f"{str(x['worst_ms']):>8}{str(x['gpu_util_avg']):>8}{str(x['gpu_util_max']):>8}  "
                  f"{x['checksum']}  {(x['renderer'] or '')[:60]}")
    sys.exit(0 if all(r.get("ok") for r in rows) else 1)


if __name__ == "__main__":
    main()
