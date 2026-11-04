#!/usr/bin/env python3
"""Execute historical and extended callback suites before/after an upstream overlay.

The source stays pristine. A copied single-file tree receives the verified patch.
Corrected suites must all pass; the old-code replay must reproduce exact failures.
These are callback host units, not renderer/device reset or guest GPU tests.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

PACKAGE = Path(__file__).resolve().parents[1]
PHASE = PACKAGE.parent
OLD = PHASE / "gpu-feasibility"
QEMU_PIN = "005c61c0ef6f6ae615283440b4bb7be51b2c6ddd"
RUTABAGA_PIN = "4f2bcaf71a6497583362ed664d9fe21cc5043049"
PATCH_SHA = "1126c30202e1ae567c08c816e4b271c60ad423f1d26f2be47c0ea4a12c68db7d"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu-source", type=Path, default=PHASE / ".work/qemu-11.1.3")
    p.add_argument("--rutabaga-source", type=Path, default=PHASE / ".work/rutabaga-gpu-feasibility")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cc", default="cc")
    args = p.parse_args()
    if args.output.exists():
        p.error("use a fresh output directory")
    args.output.mkdir(parents=True)
    result = {"scope": "Source callback host-unit overlay; GPU/actual device reset NOT TESTED", "status": "FAIL", "suites": []}
    try:
        for source, pin in ((args.qemu_source, QEMU_PIN), (args.rutabaga_source, RUTABAGA_PIN)):
            if subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() != pin:
                raise ValueError("Source pin mismatch")
            if subprocess.check_output(["git", "-C", str(source), "diff", "HEAD", "--name-only"], text=True).strip():
                raise ValueError("Tracked source modified")
        original = args.qemu_source / "hw/display/virtio-gpu-rutabaga.c"
        before = original.read_bytes()
        patch = PACKAGE / "upstream-fence-fix.patch"
        if sha(patch.read_bytes()) != PATCH_SHA:
            raise ValueError("Upstream patch checksum mismatch")
        workroot = PHASE / ".work/gpu-recovery"
        workroot.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="fence-overlay-", dir=workroot))
        target = work / "hw/display/virtio-gpu-rutabaga.c"
        target.parent.mkdir(parents=True)
        target.write_bytes(before)
        env = os.environ.copy()
        env["GIT_CEILING_DIRECTORIES"] = str(work.parent)
        for options in (["--check"], []):
            run = subprocess.run(["git", "apply", *options, str(patch.resolve())], cwd=work,
                                 env=env, capture_output=True, text=True, timeout=30)
            (args.output / ("patch-check.log" if options else "patch-apply.log")).write_text(run.stdout + run.stderr)
            if run.returncode:
                raise RuntimeError("Upstream overlay did not apply cleanly")
        after = target.read_bytes()
        if b"cmd->cmd_hdr.ctx_id != fence_data.ctx_id" in before or b"cmd->cmd_hdr.ctx_id != fence_data.ctx_id" not in after:
            raise ValueError("Unexpected baseline/fix content")
        result.update(source_commit=QEMU_PIN, upstream_fix="dbb53a7caa04d4e12e93f83511640247a2fd49d6",
                      original_source_sha256=sha(before), patched_source_sha256=sha(after), patch_sha256=PATCH_SHA)
        spec = importlib.util.spec_from_file_location("historical_probe", OLD / "tools/probe-fences.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        templates = [("original26", OLD / "tests/fence_harness.c.in"),
                     ("extended", PACKAGE / "tests/fence_extended.c.in")]
        for version, source in (("unmodified", before), ("corrected", after)):
            callback = module.extract_function(source.decode(), "virtio_gpu_rutabaga_aio_cb")
            for suite, template in templates:
                name = version + "-" + suite
                generated = work / (name + ".c")
                generated.write_text(template.read_text().replace("/* @UPSTREAM_CALLBACK@ */", callback))
                exe = work / name
                command = [args.cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-I" + str(args.qemu_source / "include"),
                           "-I" + str(args.rutabaga_source / "ffi/src/include"), str(generated), "-o", str(exe)]
                build = subprocess.run(command, capture_output=True, text=True, timeout=60)
                (args.output / (name + "-compile.log")).write_text(build.stdout + build.stderr)
                row = {"name": name, "compile_argv": command, "compile_exit_code": build.returncode,
                       "callback_sha256": sha(callback.encode()), "template_sha256": sha(template.read_bytes())}
                result["suites"].append(row)
                if build.returncode:
                    raise RuntimeError("Callback suite compile failed: " + name)
                executed = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
                (args.output / (name + ".log")).write_text(executed.stdout + executed.stderr)
                cases = [json.loads(x) for x in executed.stdout.splitlines()]
                failed = [x["case"] for x in cases if x["status"] != "PASS"]
                row.update(execute_argv=[str(exe)], execute_exit_code=executed.returncode,
                           binary_sha256=sha(exe.read_bytes()), cases=len(cases), failed=failed,
                           correctness="PASS" if executed.returncode == 0 and not failed else "FAIL")
                if suite == "original26" and len(cases) != 26:
                    raise RuntimeError("Historical case count changed")
                if suite == "extended" and len(cases) != 12:
                    raise RuntimeError("Extended case count mismatch")
                if version == "corrected" and (executed.returncode != 0 or failed):
                    raise RuntimeError("Corrected callback still fails acceptance cases")
                if version == "unmodified" and suite == "original26" and (executed.returncode != 1 or failed != ["different_context_same_ring", "two_contexts_same_ring"]):
                    raise RuntimeError("Did not reproduce exact historical negative control")
                if version == "unmodified" and suite == "extended" and (executed.returncode != 1 or failed != ["four_context_ring_pairs", "unknown_context_cannot_retire", "queue_reset_new_context_rejects_old_signal"]):
                    raise RuntimeError("Extended baseline control changed")
        if original.read_bytes() != before:
            raise RuntimeError("Pristine source changed")
        result.update(status="PASS", source_preserved=True,
                      reason="Correction suites pass; original correctness FAIL remains explicitly recorded, as a differential negative control")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        result["reason"] = str(exc)
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
