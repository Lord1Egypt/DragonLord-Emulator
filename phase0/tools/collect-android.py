#!/usr/bin/env python3
"""Capture evidence from a separately provisioned Android guest; build no images."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--serial", required=True, help="explicit adb serial; never select an arbitrary device")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    result = {"scope": "Android guest evidence only", "android16_boot": "BLOCKED",
              "gpu_acceleration": "UNVERIFIED", "kernelsu": "UNVERIFIED", "serial": args.serial, "commands": {}}
    commands = {
        "boot_completed": ["getprop", "sys.boot_completed"], "release": ["getprop", "ro.build.version.release"],
        "sdk": ["getprop", "ro.build.version.sdk"], "fingerprint": ["getprop", "ro.build.fingerprint"],
        "architecture": ["uname", "-m"], "kernel": ["uname", "-a"], "selinux": ["getenforce"],
        "surfaceflinger": ["dumpsys", "SurfaceFlinger"], "graphics_allocator": ["dumpsys", "android.hardware.graphics.allocator.IAllocator/default"],
        "boot_log": ["logcat", "-b", "all", "-d", "-t", "2000"]}
    try:
        for name, command in commands.items():
            run = subprocess.run(["adb", "-s", args.serial, "shell", *command], capture_output=True, text=True, timeout=30)
            text = run.stdout + run.stderr
            (out / (name + ".txt")).write_text(text)
            result["commands"][name] = {"exit": run.returncode, "sha256": hashlib.sha256(text.encode()).hexdigest()}
        def value(name):
            return (out / (name + ".txt")).read_text().strip()
        required = ("boot_completed", "release", "sdk", "fingerprint", "architecture")
        if all(result["commands"][x]["exit"] == 0 for x in required):
            if value("boot_completed") == "1" and value("release").split(".")[0] == "16" and value("sdk") == "36" and value("architecture") == "x86_64" and value("fingerprint"):
                result["android16_boot"] = "PASS"
            else:
                result["android16_boot"] = "FAIL"
                result["reason"] = "Guest properties do not establish a completed Android16 x86_64 boot"
        else:
            result["reason"] = "ADB guest unavailable or required commands failed"
    except (OSError, subprocess.SubprocessError) as exc:
        result["reason"] = str(exc)
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[result["android16_boot"]]

if __name__ == "__main__":
    sys.exit(main())
