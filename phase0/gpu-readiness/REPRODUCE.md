# Reproduce the recovery checkpoint

Use the published development revision shown in Draft PR #1. All commands require fresh output paths. Do not clean/reset the repository or overwrite historical results. The previous native workspace and pinned Linux CPU build are prerequisites for native/core replay; a fresh full stack rebuild is not claimed here.

## Portable regressions

From repository root:

```sh
python3 phase0/gpu-recovery/tools/verify-evidence.py --include-recovery
python3 phase0/gpu-readiness/tools/verify-evidence.py
python3 -m unittest discover -s phase0/gpu-readiness/tests -v
```

The five tests use real recovered records. They require the old malformed record to continue failing at column108, reject truncation/PID mixing and preserve invalid counter status even when its numeric value is zero. Parser PASS is not a GPU PASS. Existing modern CI also retains all earlier Python harnesses and the38 corrected source-fence cases.

## Native compiler, failure output and separate trace

The reused Phase0.6 tools/root is `C:\DLGPU\p06-20261104`: pinned clang-cl23.1.5, installed VS2022/SDK10.0.26100.0, unchanged instrumented Gfxstream executable SHA256 `4a9f453d3fdde4bd267afbb2a7bb13a10113bfc6d32be8742ed59e46798aec11`. The preparer checks compiler and workload hashes. Provisioning/source instructions remain in [Phase0.6 reproduction](../gpu-recovery/REPRODUCE.md); do not upgrade dependencies to make a replay pass.

From WSL, choose a new short C: directory:

```sh
python3 phase0/gpu-readiness/tools/prepare-native-recovery.py \
  --native-root /mnt/c/DLGPU/p07-replay-1 \
  --tools-root /mnt/c/DLGPU/p06-20261104 \
  --commands phase0/results/readiness/replay-commands-1 --repeats 1
```

Native PowerShell: set `$package` to this checkout's absolute `phase0\gpu-readiness` directory, and `$commands` to the generated command directory (a WSL UNC script/command path is acceptable; primary build paths are native/local). Run each command with a new output directory:

```powershell
& "$package\tools\run-native.ps1" -NativeRoot 'C:\DLGPU\p06-20261104' `
  -CommandFile "$commands\negative-build.json" `
  -OutputDirectory 'C:\DLGPU\p07-replay-1\results\negative-build'
# Expected actual FAIL/exit1; inspect the printed and preserved compiler error.
& "$package\tools\run-native.ps1" -NativeRoot 'C:\DLGPU\p06-20261104' `
  -CommandFile "$commands\recovered-build.json" `
  -OutputDirectory 'C:\DLGPU\p07-replay-1\results\fixed-build'
# Require actual compile exit0 before any smoke.
```

Then run `smoke-hardware.json` and, after it exits, `smoke-software.json`, using output directories exactly `C:\DLGPU\p07-replay-1\results\recovery-smoke-hardware` and `...\recovery-smoke-software`. The generated trace filenames match those directories. Each run executes only three tests once; this is a bounded transport/fixture regression. The negative build compiles the preserved `_wfopen` source under `/WX` and must still fail. The corrected build uses `_wfopen_s`; warnings are not suppressed.

The software control explicitly selects the existing Chrome156.0.8078.80 SwiftShader ICD. If it or the pinned binary is unavailable, report BLOCKED/FAIL rather than choosing an uncontrolled replacement. No installed application, hook, GPU driver, tracing right or global setting should be changed. PowerShell invocations during recovery used process-only `-ExecutionPolicy Bypass`; no system/user execution-policy configuration was changed.

After execution, collect exact files (the collector includes `.jsonl`, unlike the older general collector):

```sh
python3 phase0/gpu-readiness/tools/collect-recovery.py \
  --native-root /mnt/c/DLGPU/p07-replay-1 \
  --output phase0/results/readiness/replay-native-evidence-1
python3 phase0/gpu-readiness/tools/parse-kernel-trace.py \
  /mnt/c/DLGPU/p07-replay-1/results/recovery-smoke-hardware/kernel.jsonl \
  --output phase0/results/readiness/replay-hardware-parse-1.json
```

Repeat parsing for software with a fresh result filename. A failed child, malformed/truncated trace or PID mismatch must fail. Original pre-recovery shared stdout remains corrupt and is never silently repaired. D3DKMT accounting is experimental and does not establish the missing independent GPU acceptance gate.

## Corrected QOM fixture / actual core smoke

Prerequisites: pristine pinned QEMU source `phase0/.work/qemu-11.1.3`, the original Linux build with `compile_commands.json`, all linked objects and pinned Ninja/venv from Phase0. The builder takes the actual main compile command and expanded link command, substitutes an instrumented probe main, and writes new objects/executable into a fresh ignored subdirectory. It does not modify original QEMU sources/objects.

```sh
python3 phase0/gpu-readiness/tools/build-core-probe.py \
  --output phase0/results/readiness/replay-core-build-1
ASAN_OPTIONS=detect_leaks=0:abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
  phase0/.work/gpu-readiness/core/replay-core-build-1/core_probe safe
```

The fixture registers concrete `phase07-smoke-owner` under abstract `TYPE_OBJECT` before construction. Required result: exit0 and both actual QEMU map/unmap markers. The original `object_new(TYPE_OBJECT)` failure is preserved in the initial source/logs; assertions must remain enabled. Source and binary hashes change with a fresh relink and must be captured rather than assumed identical.

Only the probe main is sanitizer-instrumented; coroutine-support warnings and the disabled leak check limit interpretation. Do not run the optional intentional `unsafe` mode as a routine smoke or call this test proof of actual Rutabaga retirement/reset/WHPX safety. It was not run after the concrete-owner correction in this recovery milestone.

The read-only rights/hook inventory can be repeated with `audit-native.ps1 -OutputDirectory <fresh-native-directory>`. It observes permissions and relevant file provenance; it does not grant tracing rights or remove hooks.
