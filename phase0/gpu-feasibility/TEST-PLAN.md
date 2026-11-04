# Deterministic test and measurement protocol

This is an executable evidence plan plus the results actually obtained. Unexecuted cases below are **NOT TESTED**, not passing specifications. Original Phase 0 performance criteria remain in [BENCHMARKS.md](../BENCHMARKS.md).

## Executed checks

| Test | Result | Evidence / scope |
|---|---|---|
| Published Phase 0 hashes and retained boot evidence | PASS | [Validator](evidence/phase0-validation/result.json): 77 indexed artifacts, local Linux and both Windows PE hashes agree; nine original harness tests pass. No new VM boot. |
| Native Windows tool/API inventory | PASS | [Toolchain](evidence/toolchain/toolchain.json), [host commands](evidence/host/host.json). Inventory-only PASS; no rendering. |
| Native Gfxstream configure/build request | BLOCKED | [MSB8020](evidence/gfxstream-configure/configure.stderr.log), configure exit 1; build and execution never reached. Runner exits 2. |
| Windows target Rutabaga discovery | BLOCKED | [Configure log](evidence/rutabaga-dependency/configure.log), exit 1: missing FFI dependency; no integrated build. |
| Actual QEMU fence callback host-unit oracle | FAIL | [Cases](evidence/fence-probe/run.log): 24 PASS / 2 FAIL. Different context with same ring is incorrectly completed. Compile exit 0, executable exit 1. |
| New evidence-integrity regressions | PASS | Eight tests: both original nonce lengths, echo/wrong-architecture/fallback/blocked rejection, tamper/path-escape checks. [Log](evidence/evidence-tests.log). |
| Native PowerShell syntax and Python syntax | PASS | [Validation record](evidence/package-validation.json); parser/syntax only. |

Failures in the callback oracle remain failures even if a wrapper successfully collects them. No expected-failure conversion is used to promote G4/G6. The repeated callback scaffold cases exercise only host allocations/queues/response capture; they provide no renderer reset or GPU leak/stability coverage.

## Required after native build becomes available

Use a fresh test directory/run ID, exact source/compiler/dependency manifests, complete argv/environment whitelist, executable/DLL hashes and monotonic timestamps. Choose actual upstream discovered test names after compilation. Never guess a GoogleTest filter and report PASS when it matched zero tests; require the expected nonzero case count and per-case results. Preserve stdout/stderr and exit code, including skipped tests.

| Case | Deterministic procedure and acceptance | Current status |
|---|---|---|
| Initialization | Load exact renderer and required DLLs from controlled absolute paths; initialize once with declared features; verify nonempty capsets/API/device. Missing DLL, invalid flags and missing required extensions must fail explicitly. | NOT TESTED |
| Allocation/map | Allocate bounded 64×64 RGBA and bounded blob buffers; query format/usage/alignment; write a seeded byte pattern and check every byte after map/unmap/readback. Include zero, oversized, overflow and duplicate-ID requests with safe errors. | NOT TESTED |
| Rendering | Run upstream GLES clear/triangle and Vulkan clear/draw/readback through Gfxstream. Use fixed shaders, seed, target format and expected pixels/tolerances; verify output changes between two known frames. Native Vulkan bypassing Gfxstream does not qualify G1. | NOT TESTED |
| Synchronization | Submit known write/draw/read operations; use bounded fence waits; verify completion follows visible writes. Cover separate contexts with identical ring/fence IDs, distinct rings, future/duplicate/late fences and callback ownership. | FAIL in isolated callback selection only; real GPU/VM NOT TESTED |
| FFI ABI/handles | Assert C/Rust widths, offsets and calling conventions, especially fence ring field; round-trip descriptors without truncation; duplicate, import/export and close exactly once on success/failure. Check invalid handles and allocation ownership across CRTs. | NOT TESTED |
| WHPX sharing | After G1–G3, use one virtio-gpu device, synthetic guest buffer and negotiated capset. Verify guest→host and host→guest patterns, cache visibility, bounded offset/size and permissions. Correlate actual commands/fences and snapshot base protection. | NOT TESTED |
| Cleanup | Destroy context/resource only after waits/drain; confirm handles, GPU memory and mappings retire. Repeated unmap/destroy/invalid resource must return safe errors. Compare process handle counts and memory against measured baseline. | NOT TESTED |
| Repeated creation/destruction | 100 sequential renderer/context lifecycles, then 1,000 small resource cycles with exact object counts; collect handle/memory counters and failures, not just exit status. Adjust repetition only through a documented test revision. | NOT TESTED |
| Reset/device loss | Reset/recreate with pending commands and active maps; inject load/allocation/import failure; teardown during queued callback. Require bounded termination, no stale completion, use-after-free or host crash, and successful subsequent initialization. Use sanitizers/guards where supported. | NOT TESTED |

No fault injection should disable host security controls, reset a physical adapter or affect unrelated applications. Begin with renderer-level synthetic failure hooks. Physical driver-loss testing needs a separately bounded facility and recovery plan.

## Hardware arm and independent software control

1. Pin the actual vendor EGL/GLES implementation and/or Vulkan ICD and selected physical adapter. Record API version/extensions, device/vendor/driver identity, renderer PID, loaded module paths/hashes and actual renderer selection logs. A requested selection that falls back or lacks verification fails the hardware arm.
2. Do not use the upstream Windows CTest software environment for the hardware arm. Record/clear its scoped software overrides and inspect build-time test-driver definitions; `CONFIG_AEMU` test mode has additional software-selection behavior. Prefer a separate validated direct test invocation. No registry, global PATH or driver changes are required.
3. Require changing correct pixels plus API fences and a GPU execution trace independently attributed to that renderer PID and physical adapter. ETW/GPUView is the proposed Windows mechanism; present/compute/copy engines and LUID mapping must be understood before using percentages. A loaded vendor DLL or global GPU percentage alone is insufficient.
4. Repeat the same deterministic workload with an explicitly selected, hash-pinned SwiftShader/WARP/software implementation as a control, and prove the evidence pipeline identifies it. Software controls must be marked SOFTWARE and never satisfy G1/G2.
5. Store trace acquisition argv, tool versions, provider/configuration identity, run start/end, clock correlation, decoded relevant events and analysis code. Raw ETL may contain unrelated host data and be large: inspect/redact and publish small relevant extracts and hashes; do not upload it automatically. This phase acquired **no GPU trace**.

Only after correctness/hardware proof should FPS, frame intervals, CPU/GPU utilization, memory, boot and stability be measured under the controlled Phase 0 benchmark plan. **No GPU performance or latency numbers were measured in Phase 0.5.**
