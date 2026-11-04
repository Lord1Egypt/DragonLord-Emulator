#!/usr/bin/env python3
"""Run an unchanged upstream QEMU fence callback in a narrow host-unit scaffold.

Uses real upstream queue, virtio and FFI headers. Response delivery and enclosing
device structs are test scaffolding. This is not a GPU, Windows or VM test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

PACKAGE = Path(__file__).resolve().parents[1]
PHASE = PACKAGE.parent
PINS = {"qemu": "005c61c0ef6f6ae615283440b4bb7be51b2c6ddd",
        "rutabaga": "4f2bcaf71a6497583362ed664d9fe21cc5043049"}


def extract_function(text, name):
    start = text.index("static void\n" + name + "(")
    brace = text.index("{", start)
    depth = 1
    pos = brace + 1
    # This pinned callback contains no braces in strings/comments. Its complete
    # digest is retained; a changed source requires a new probe review.
    while depth:
        if text[pos] == "{": depth += 1
        if text[pos] == "}": depth -= 1
        pos += 1
    return text[start:pos]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu-source", type=Path, default=PHASE / ".work/qemu-11.1.3")
    parser.add_argument("--rutabaga-source", type=Path, default=PHASE / ".work/rutabaga-gpu-feasibility")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cc", default="cc")
    args = parser.parse_args()
    if args.output.exists(): parser.error("use a fresh output directory")
    args.output.mkdir(parents=True)
    result = {"scope": "Unmodified QEMU callback host unit; not Windows/GPU/VM execution",
              "status": "BLOCKED", "pins": PINS, "gpu": "NOT TESTED"}
    try:
        for name, source in (("qemu", args.qemu_source), ("rutabaga", args.rutabaga_source)):
            assert subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() == PINS[name]
            assert not subprocess.check_output(["git", "-C", str(source), "diff", "HEAD", "--name-only"], text=True).strip()
        original = args.qemu_source / "hw/display/virtio-gpu-rutabaga.c"
        callback = extract_function(original.read_text(), "virtio_gpu_rutabaga_aio_cb")
        result["source_sha256"] = hashlib.sha256(original.read_bytes()).hexdigest()
        result["callback_sha256"] = hashlib.sha256(callback.encode()).hexdigest()
        work = PHASE / ".work/gpu-feasibility/fence-probe"
        work.mkdir(parents=True, exist_ok=True)
        generated = work / "fence_probe.c"
        generated.write_text((PACKAGE / "tests/fence_harness.c.in").read_text().replace("/* @UPSTREAM_CALLBACK@ */", callback))
        executable = work / "fence_probe"
        argv = [args.cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-I" + str(args.qemu_source / "include"),
                "-I" + str(args.rutabaga_source / "ffi/src/include"), str(generated), "-o", str(executable)]
        result["compile_argv"] = argv
        compile_run = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        (args.output / "compile.log").write_text(compile_run.stdout + compile_run.stderr)
        result["compile_exit_code"] = compile_run.returncode
        if compile_run.returncode:
            raise RuntimeError("Callback scaffold compile failed")
        run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=20)
        (args.output / "run.log").write_text(run.stdout + run.stderr)
        result.update(status="PASS" if run.returncode == 0 else "FAIL", exit_code=run.returncode,
                      execute_argv=[str(executable)], cases=[json.loads(x) for x in run.stdout.splitlines()],
                      binary_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                      reason="Per-context fence isolation oracle against unchanged callback; inspect individual cases")
    except (AssertionError, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        result["reason"] = str(exc) or "Source revision/pristine check failed"
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}, indent=2))
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[result["status"]]


if __name__ == "__main__": sys.exit(main())
