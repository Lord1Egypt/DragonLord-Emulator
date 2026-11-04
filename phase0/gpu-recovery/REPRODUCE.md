# Reproduction and exact evidence

Run from the development checkout. Keep the reviewed Phase 0/0.5 directories immutable. Use fresh result directories; never replace an original FAIL. Recorded commands use `C:\DLGPU\p06-20261104`; relocation is supported. A second clean machine replay has not been executed, and matching output/binary hashes across tool installations are not assumed.

## Evidence and callback tests (Linux / CI)

```sh
python3 phase0/gpu-recovery/tools/verify-evidence.py --include-recovery
python3 -m unittest discover -s phase0/tests -v
python3 -m unittest discover -s phase0/gpu-feasibility/tests -v
python3 -m unittest discover -s phase0/gpu-recovery/tests -v
python3 phase0/gpu-recovery/tools/fetch-probe-sources.py
python3 phase0/gpu-recovery/tools/test-fence-overlay.py --output phase0/results/recovery/replay-fences
```

The callback runner builds/exercises actual original and corrected callback bodies. Its acceptance exit 0 requires the exact original failures and all corrected cases PASS; original correctness records remain FAIL. QEMU enclosing device/response behavior is scaffolded. Native GPU execution is not a CI-hosted claim.

## Prepare an isolated Windows workspace

Tested host: Windows 11 Pro 10.0.26300, Intel i7-9750H, NVIDIA RTX 2060 driver 617.42 (Windows 32.0.16.1742), Intel UHD 630 driver 25.20.100.6519. Existing Visual Studio Build Tools 2022 17.14 / MSVC 14.44.35207 / SDK 10.0.26100.0, CMake 4.3.2 and VS Ninja are used. Portable LLVM/Rust fill the actual missing compiler/toolchain components. Official installation sources, if these existing components are absent: [VS Build Tools](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022), [Windows SDK](https://developer.microsoft.com/windows/downloads/windows-sdk/), [CMake](https://cmake.org/download/), [LLVM release](https://github.com/llvm/llvm-project/releases/tag/llvmorg-23.1.5), [Rust archives](https://static.rust-lang.org/dist/channel-rust-1.88.0.toml). Do not alter GPU drivers, system security, virtualization or global PATH.

In WSL with Python 3.13+, Git, GnuPG and enough free C: storage (tens of GB; extracted LLVM tools alone are several GB):

```sh
python3 -m venv phase0/.work/recovery-replay-venv
phase0/.work/recovery-replay-venv/bin/pip install zstandard==0.25.0
python3 phase0/gpu-recovery/tools/fetch-probe-sources.py --native
python3 phase0/gpu-recovery/tools/fetch-toolchains.py
phase0/.work/recovery-replay-venv/bin/python phase0/gpu-recovery/tools/provision-native.py \
  --destination /mnt/c/DLGPU/replay --output phase0/results/recovery/replay-provision
python3 phase0/gpu-recovery/tools/apply-gfxstream-build-fix.py --native-root /mnt/c/DLGPU/replay
python3 phase0/gpu-recovery/tools/prepare-renderer-probe.py --native-root /mnt/c/DLGPU/replay
python3 phase0/gpu-recovery/tools/prepare-abi.py --native-root /mnt/c/DLGPU/replay \
  --command-directory phase0/results/recovery/replay-abi-commands
python3 phase0/gpu-recovery/tools/relocate-commands.py --native-root 'C:\DLGPU\replay' \
  --output phase0/results/recovery/replay-commands
```

Downloads are hash pinned; LLVM signature is verified in a new private temporary keyring on each provision. Existing checksum mismatches are refused, not overwritten. Rust's checksum comes from the pinned official manifest; no independent Rust signing-key qualification is claimed. Pristine Git source is archived into a new local C: layout (one non-build CI symlink omitted as recorded). No `.git`, credentials or user profiles are copied. Source overlay hash mismatches fail.

The observation preparer verifies the checked-in patch before applying it to the copied tests. It currently writes the identical observation manifest back into this evidence package; verify its bytes stay unchanged. Original repository/upstream source is never patched. Copy `experiments/mapping_retirement.cpp` to `C:\DLGPU\replay\experiments\` before compiling that independent reference.

## Native build and FFI tests

Open ordinary native Windows PowerShell. Set `$package` to the absolute path of this `phase0\gpu-recovery` directory (it may be a WSL UNC script path); all primary compilation paths below are native/local:

```powershell
$native='C:\DLGPU\replay'
& "$package\tools\build-native.ps1" -NativeRoot $native `
  -BuildDirectory "$native\build\gfxstream-native-3" `
  -OutputDirectory "$native\results\gfxstream-build" -LeanWindowsHeaders `
  -SourceOverlayManifest "$native\gfxstream-observed-overlay.json"
```

This must actually return 0 and produce backend/test binaries before rendering. Capture the new hashes rather than assuming those in the original log. The native runner initializes existing vcvars only in child environment, uses isolated LLVM/Rust/Cargo cache, and records exact CMake arguments and exits. Use `--parallel 2` (the script default) for this bounded experiment.

Copy `evidence\dependencies\rutabaga-Cargo.lock` to `$native\src\rutabaga\Cargo.lock` and `boundary-Cargo.lock` to `$native\experiments\boundary\Cargo.lock`. Select the **relocated** command files (`$commands`) generated above. Append `--locked` to the three Cargo build argument arrays before replay; initial recorded builds resolved dependencies, while the published lockfiles bind that resolution for future reproductions. `invoke-dev.ps1` consumes command JSON without shell interpolation:

```powershell
& "$package\tools\invoke-dev.ps1" -NativeRoot $native `
  -CommandFile "$commands\cargo-build-command.json" -OutputDirectory "$native\results\ffi-core"
& "$package\tools\invoke-dev.ps1" -NativeRoot $native `
  -CommandFile "$commands\cargo-ffi-gfx2-command.json" -OutputDirectory "$native\results\ffi-gfx"
& "$package\tools\invoke-dev.ps1" -NativeRoot $native `
  -CommandFile "$commands\cargo-boundary-command.json" -OutputDirectory "$native\results\boundary-helper"
```

The `gfx2` command uses the actual `<build>\host` import library. The historical `gfx` command's wrong-directory failure is evidence, not a recommended build command. Each successful compilation/load is separate from GPU qualification.

Run each new ABI command generated by `prepare-abi.py` through `invoke-dev.ps1`, with its own output directory, in this order:

| Command | Expected actual result |
|---|---|
| `abi-original-assert-compile.json` | FAIL, compile exit 1: ring width 4 vs 1 |
| `abi-original-observe-compile.json` | PASS, compiles negative observation control |
| `abi-original-observe-run.json` | FAIL, exit 1: original two ABI mismatches |
| `abi-corrected-compile.json` | PASS |
| `abi-corrected-run.json` | PASS, 113 actual boundary/core cases |

Also run relocated `abi-gfx-run-command.json` after compiling the corrected probe: same 113 core cases against Gfxstream-enabled FFI, with scoped backend DLL lookup. It does not select/stream the Gfxstream component. Use relocated `mapping-compile-command.json`, `mapping-run-command.json`, `gfx-timelines-command.json` and `pe-imports-command.json` to reproduce the separate Win32 reference, CPU timeline and import inspections. Do not convert a negative-control command into an unchecked success or continue to integration after an unexpected failure.

## Rendering and strict qualification

Use the actual executable directly; upstream CTest's Windows setup selects software. Confirm installed driver/ICD provenance first. Relocated hardware command asserts vendor `0x10de`, discrete type 2; another GPU requires a reviewed explicit assertion/qualifier adaptation, not automatic fallback. Software command points at the existing Chrome 156 SwiftShader ICD used here. If absent, report BLOCKED or qualify an explicit separately obtained software ICD; don't silently change the control or redistribute browser files.

```powershell
& "$package\tools\observe-renderer.ps1" `
  -CommandFile "$commands\gfx-final-hardware-command.json" `
  -OutputDirectory "$native\results\gfx-final-hardware"
# Only after hardware run exits, use the identical workload/software control:
& "$package\tools\observe-renderer.ps1" `
  -CommandFile "$commands\gfx-final-software-command.json" `
  -OutputDirectory "$native\results\gfx-final-software"
```

The observer attempts only its own named DxgKrnl ETW session, records permission failure, captures loaded module hashes and per-process Windows GPU Engine samples. The final sampler additionally attempts two rate samples per query; initial one-sample runs and the repeated two-sample software failure are both preserved. Invalid statuses are never measured zeros. No GPU performance inference is made from GoogleTest duration. Keep runs serialized and record external load/environment for future benchmark work.

On the captured directories, from WSL:

```sh
python3 phase0/gpu-recovery/tools/qualify-renderer.py \
  --hardware /mnt/c/DLGPU/replay/results/gfx-final-hardware \
  --software /mnt/c/DLGPU/replay/results/gfx-final-software \
  --output phase0/results/recovery/replay-renderer-qualification.json
```

**The original strict qualifier exits 1 / independent verification FAIL** because software counters are invalid and ETW is denied, despite both 90-test rendering logs passing. That failure is retained. A return code 0 from the observer alone is not acceptance. To reproduce the original exact sampling revision, inspect the preserved command/results; do not describe revised sampling as an identical original trace.

Collect only text evidence using `collect-native-evidence.py`; it losslessly gzips logs larger than 2 MiB and writes raw/stored SHA256 and byte counts. Do not publish binaries, tool archives, credentials, user data, ETL traces or crash dumps automatically. Trace artifacts need separate size/privacy review. New evidence belongs in fresh directories and a new revision-bound index; never mutate prior raw records.
