# Phase 0.6 GPU foundation recovery

Starting reviewed commit: `6c1a0604dcfc63d7efa84fea73b065d9aa8920b5`. Development branch: `phase0/architecture-feasibility`. External review stays in [Draft PR #1](https://github.com/Lord1Egypt/DragonLord-Emulator/pull/1). Earlier Phase 0/0.5 evidence and pristine upstream source are preserved.

This first milestone restores separate modern validation and tests the upstream fence correction. Native compilation, hardware execution, FFI/ABI and memory retirement are separate subsequent workstreams; nothing here approves migration or an Android image build.

## CI recovery

The complete 852-line [legacy job log](evidence/ci/legacy-job-126330694303.log) shows that [run 41755551737](https://github.com/Lord1Egypt/DragonLord-Emulator/actions/runs/41755551737) failed in `msys2/setup-msys2`, before compilation. Missing targets were `mingw-w64-x86_64-tools-git`, `mingw-w64-x86_64-winstorecompat-git` and `mingw-w64-x86_64-libmangle-git`. See [failure analysis](evidence/ci/legacy-failure-analysis.json).

The legacy workflow is now explicitly manual and unqualified. It uses UCRT64 and direct compiler/library packages, letting pacman resolve toolchain internals instead of requesting removed package names. [MSYS2 documents MINGW64 deprecation](https://www.msys2.org/news/). This change does **not** claim that the legacy source now compiles; its configure/source/dependency gaps remain separate and any manual failure remains a failed job.

The modern PR workflow runs Linux/Windows evidence integrity, the original and new Python harnesses, pinned Ruff checks and native PowerShell parsing. A separate Linux job tests the corrected source callback. It names and publishes the original FAIL controls explicitly, requires exact historical failures and requires every corrected case to pass. There is no `continue-on-error` or blanket expected-failure conversion. Workflow actions are pinned to inspected official major-tag commit SHAs. A passing modern workflow does not qualify a GPU or build the full modern VMM.

Hosted CI results are pending until this workflow is published and actually runs. Local tests alone are not reported as hosted CI PASS. Captured CI evidence will be added at the exact tested revision.

## Verified upstream overlay

[QEMU commit dbb53a7c](https://gitlab.com/qemu-project/qemu/-/commit/dbb53a7caa04d4e12e93f83511640247a2fd49d6) adds the missing context-ID comparison. It was fetched from the official GitLab repository; the [official GitHub mirror](https://github.com/qemu/qemu/commit/dbb53a7caa04d4e12e93f83511640247a2fd49d6) agrees. The pinned v11.1.3 file lacks it. The original working source remains at `005c61c0ef6f6ae615283440b4bb7be51b2c6ddd` and unchanged. [Identity/hashes](evidence/upstream-fence-identity.json) and the exact [format-patch](upstream-fence-fix.patch) are retained.

The runner copies only the relevant C file into an isolated tree, checks/applies the patch, extracts each actual callback and compiles it against real pinned QEMU queue/virtio and Rutabaga C headers. Enclosing device/response behavior is a test scaffold. Compilation commands, source/callback/patch/template/binary hashes and process exit codes are in [results](evidence/fence-overlay/result.json).

| Executed callback suite | Original code | Corrected overlay |
|---|---|---|
| Historical 26 cases | **FAIL**: 24 PASS, exact original 2 FAIL; exit 1 | **PASS**: 26/26; exit 0 |
| Extended 12 cases | **FAIL**: 9 PASS, 3 FAIL; exit 1 | **PASS**: 12/12; exit 0 |

Extended cases cover context/ring pairs, monotonic/full-width fence ordering, duplicate/out-of-order/empty callbacks, unknown contexts, highest ring, global/context separation and queue-drain/new-context reset scenarios. The latter are **queue-level units**, not real renderer/device reset, asynchronous destruction, context-ID reuse safety or GPU fence validation. Those lifecycle gates remain unqualified.

From the repository root, on Linux with Git, Python and a C compiler:

```sh
python3 phase0/gpu-recovery/tools/verify-evidence.py
python3 phase0/gpu-recovery/tools/fetch-probe-sources.py
python3 -m unittest discover -s phase0/gpu-recovery/tests -v
python3 phase0/gpu-recovery/tools/test-fence-overlay.py \
  --output phase0/results/recovery/fences
```

Use a fresh output directory. Source pins or patch checksum mismatches fail. The runner's PASS means the corrected acceptance suites passed and the exact original failures were reproduced; the original correctness records remain FAIL. No historical result is overwritten.

## Remaining recovery gates

Native Windows work uses a new short isolated directory and verified official compiler archives; no global PATH, GPU driver, security or virtualization change is permitted. BUILD PASS requires an actual native compilation; hardware PASS additionally requires a Gfxstream workload, changing correct pixels, selected adapter/ICD/DLL identity, an independently attributed execution trace and software control. ABI/memory tests and minimal QEMU device integration must wait for their prerequisites. Exact results will be reported separately before the Phase 0.6 stopping decision.
