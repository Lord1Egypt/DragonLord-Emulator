# Phase 0.5 evidence and reproduction

**Verdict: NO-GO for the Windows GPU foundation.** Native Gfxstream configure is BLOCKED by missing ClangCL; no rendering ran. A separate unchanged-QEMU-callback unit probe fails context isolation. Full report: [REPORT.md](REPORT.md). Integration map: [COMPATIBILITY.md](COMPATIBILITY.md). Test requirements/results: [TEST-PLAN.md](TEST-PLAN.md).

Phase 0 was published first at [d74a521](https://github.com/Lord1Egypt/DragonLord-Emulator/commit/d74a521f7933baeeb771f412cb9261c3311ded62), in [Draft PR #1](https://github.com/Lord1Egypt/DragonLord-Emulator/pull/1). This package is additive on `phase0/architecture-feasibility`; the original main/legacy and Phase 0 evidence remain unchanged. [versions.lock.json](versions.lock.json) pins the research sources; [evidence/index.json](evidence/index.json) hashes this package's files, excluding itself. Build trees and binaries stay in ignored `phase0/.work`; replay outputs belong in ignored `phase0/results`.

## Validate the published baseline and source pins

From the repository root on Linux/WSL, with Python 3.9+ and Git:

```sh
python3 phase0/gpu-feasibility/tools/validate-phase0.py \
  --output phase0/results/gpu-review/phase0-validation
python3 phase0/gpu-feasibility/tools/fetch-sources.py
python3 -m unittest discover -s phase0/gpu-feasibility/tests -v
```

Each output directory must be fresh. Baseline validation checks retained bytes, strict acceleration argv and actual returned nonce/architecture, then reruns the original nine tests. Locally built executables are compared to their saved hashes when present; their absence is NOT TESTED and does not become a fresh build/boot claim. To build them, use the existing [Phase 0 instructions](../README.md). No prior evidence directory is replaced.

`fetch-sources.py` creates pinned Gfxstream and Rutabaga source clones under `.work` and rejects mismatched/modified existing trees. A modern QEMU clone at `.work/qemu-11.1.3` is supplied by the Phase 0 build script. For source inspection/fence testing alone, obtain it without building:

```sh
git clone --depth 1 --branch v11.1.3 https://gitlab.com/qemu-project/qemu.git \
  phase0/.work/qemu-11.1.3
git -C phase0/.work/qemu-11.1.3 rev-parse HEAD
# Expected: 005c61c0ef6f6ae615283440b4bb7be51b2c6ddd
```

Run that clone command only if the directory is absent. The probes refuse a different tracked source revision. Git tag/source hashes are captured; independent release/package signature review remains open.

## Native Windows build gate

Prerequisites for the documented build: native Windows x64, Git, Visual Studio 2022 Build Tools with the **ClangCL/LLVM toolset**, SDK and CMake, then complete pinned test/graphics dependencies. The upstream README mentions VS2019/ClangCL; this attempt selected the installed VS2022 generator. [Microsoft's Clang toolset instructions](https://learn.microsoft.com/en-us/cpp/build/clang-support-msbuild?view=msvc-170) describe the separate components. The scripts discover/use installed tools; they install nothing and change no registry, driver or OS feature.

Use absolute paths in native Windows PowerShell. Prefer a short Windows checkout such as `C:\src\DragonLord-Emulator`; place pinned source clones under its `phase0\.work` using the fetch script when native Python is available, or equivalent explicit `git clone --no-checkout` and `git checkout --detach` commands from the lock. A WSL clone can be addressed through its full UNC path, as in the captured attempt; a complete UNC build has not passed.

```powershell
$repo = 'C:\src\DragonLord-Emulator'
& "$repo\phase0\gpu-feasibility\tools\probe-toolchain.ps1" `
  -OutputDirectory "$repo\phase0\results\gpu-review\toolchain"
& "$repo\phase0\gpu-feasibility\tools\collect-host.ps1" `
  -OutputDirectory "$repo\phase0\results\gpu-review\host"
& "$repo\phase0\gpu-feasibility\tools\build-gfxstream.ps1" `
  -SourceDirectory "$repo\phase0\.work\gfxstream-gpu-feasibility" `
  -BuildDirectory "$repo\phase0\.work\gpu-feasibility\gfxstream-native-run2" `
  -OutputDirectory "$repo\phase0\results\gpu-review\gfxstream-configure" `
  -Build
$LASTEXITCODE
```

The captured equivalent uses CMake 4.3.2:

```text
cmake -S <pinned-gfxstream> -B <fresh-build> -G "Visual Studio 17 2022" -A x64 -T ClangCL
  -DBUILD_STANDALONE=ON -DENABLE_VKCEREAL_TESTS=ON -DASTC_CPU_DECODING=OFF
  -DGFXSTREAM_ENABLE_HOST_TRACING=OFF
```

Actual result: CMake exit **1**, MSBuild **MSB8020**, wrapper exit **2/BLOCKED**. The requested `cmake --build ... --config Release --target gfxstream_backend --parallel 4` was **not reached**. No Gfxstream DLL/test executable/hash is claimed. `-Build` would request the library only after configure succeeds; it does not automatically build/run the rendering tests or claim GPU PASS.

Do not run CTest defaults as hardware proof: the pinned Windows test environment forces SwiftShader. There is no validated rendering execution command in this package because compilation stopped first. Actual selected tests, hardware/software environments and trace acquisition must be qualified according to [TEST-PLAN.md](TEST-PLAN.md), including nonzero executed test counts. Do not substitute direct vendor Vulkan rendering for a Gfxstream test.

## Reproduce the fence failure

On Linux with GCC/Clang C and the pinned source clones, no renderer/DLL/VM is needed:

```sh
python3 phase0/gpu-feasibility/tools/probe-fences.py \
  --output phase0/results/gpu-review/fences
```

Expected on this exact upstream revision: compile exit **0**, probe exit **1/FAIL**; 24 case results PASS and 2 FAIL, including `different_context_same_ring` and `two_contexts_same_ring`. The script extracts the unchanged source callback into an ignored generated C file and uses upstream queue/virtio/FFI headers plus [test scaffold](tests/fence_harness.c.in). Recorded source/callback/binary hashes and exact commands identify the tested code. This is a local selection-logic reproduction, not a full QEMU, Windows ABI or GPU fence test. Repetition exercises scaffold cleanup only.

## Reproduce target-library discovery

This optional dependency probe needs the existing Phase 0 isolated Windows cross-toolchain and build venv; it installs nothing:

```sh
python3 phase0/gpu-feasibility/tools/probe-rutabaga-build.py \
  --build-directory phase0/.work/gpu-feasibility/rutabaga-probe-run2 \
  --output phase0/results/gpu-review/rutabaga-dependency
```

Captured configure exit **1** reports `Dependency "rutabaga_gfx_ffi" not found (tried pkg-config)`; wrapper exits **2/BLOCKED**. It requests the optional dependency in the Phase 0 CPU profile, retaining disabled Pixman; this is deliberately **not a complete graphics build configuration**. It proves the dependency is absent from that target search path, not that a fully provisioned Windows build is impossible. A future complete integration profile also needs Pixman and renderer/FFI closure.

## Evidence handling and external synchronization

Preserve failures and fresh run directories. Initial native Git preflight and the first Phase 0 validator result are retained. The validator initially assumed a 128-bit nonce for both runners; Linux TCG actually uses a 64-bit nonce. The corrected validator accepts both original formats with command-response checks; dedicated tests cover them. Original Phase 0 results did not change.

Host inventories redact the Windows user-profile path. A local initial unredacted inventory is kept under ignored `.work` and is excluded from publication. No credentials, compiler archives, executable/DLLs, VM images or raw GPU traces are published. Evidence status is agent-reported, not owner attestation.

At a completed validated engineering milestone: commit relevant source/docs/scripts/small reproducible evidence, fetch/reconcile safely, push this development branch without force, verify the remote SHA, and update the same Draft PR targeting main. PR body/handoff must identify base/head commits, environment, commands, PASS/FAIL/BLOCKED/NOT TESTED results, evidence hashes, limitations and next action. Never auto-merge, change main, delete branches, tag or release. GitHub is the authoritative review artifact; ThothMemory stores context/checkpoints and commit/PR links. Authentication failures must be reported honestly.
