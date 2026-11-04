#!/usr/bin/env python3
"""Compare APIs and syntax-check original transport using a modern QEMU compile command."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

PHASE = Path(__file__).resolve().parents[1]
ROOT = PHASE.parent

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    build = PHASE / ".work/qemu-build-linux"
    commands = build / "compile_commands.json"
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    if not commands.exists():
        raise SystemExit("BLOCKED: first configure the pinned modern QEMU Linux build")
    database = json.loads(commands.read_text())
    reference = next(x for x in database if x["file"].endswith("hw/display/virtio-gpu-pci.c"))
    cmd = reference.get("arguments") or shlex.split(reference["command"])
    filtered = []
    skip = False
    for arg in cmd:
        if skip:
            skip = False
            continue
        if arg in ("-o", "-MF", "-MQ", "-MT"):
            skip = True
        elif arg not in ("-c", "-MD", "-MMD") and not arg.endswith("hw/display/virtio-gpu-pci.c"):
            filtered.append(arg)
    # Expose only the custom headers; never mask modern QEMU headers with old ones.
    overlay = PHASE / ".work/legacy-api-include"
    overlay.mkdir(exist_ok=True)
    for dirname in ("direct-express", "express-gpu", "glad"):
        link = overlay / dirname
        if not link.exists():
            link.symlink_to(ROOT / "include" / dirname, target_is_directory=True)
    result = {"scope": "unmodified legacy transport syntax against modern configured headers",
              "modern_commit": "005c61c0ef6f6ae615283440b4bb7be51b2c6ddd", "units": []}
    for name in ("direct_express.c", "direct_express_pci.c", "express_handle_thread.c", "direct_express_distribute.c"):
        command = filtered + ["-I" + str(overlay), "-Werror=implicit-function-declaration",
                              "-Werror=incompatible-pointer-types", "-fsyntax-only",
                              str(ROOT / "hw/direct-express" / name)]
        run = subprocess.run(command, cwd=reference["directory"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (out / (name + ".log")).write_text(run.stdout)
        result["units"].append({"file": name, "exit_code": run.returncode, "argv": command})
    result["unchanged_legacy_compiles"] = all(u["exit_code"] == 0 for u in result["units"])
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
