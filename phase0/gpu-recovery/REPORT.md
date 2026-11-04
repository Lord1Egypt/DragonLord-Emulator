# Phase 0.6 — GPU foundation recovery

**Verdict: NO-GO for a guest-visible QEMU/Rutabaga Windows GPU integration experiment at this checkpoint.** Native development and isolated rendering are now feasible. Independent tracing/control qualification, integrated memory retirement and distribution licensing remain blocking. Continue only bounded observability, ownership and license work; do not migrate the emulator or build Android images.

Reviewed starting revision: `6c1a0604dcfc63d7efa84fea73b065d9aa8920b5`. First published recovery milestone: `7904adf57c39288bd0b157c6f1d34bbd489c9dbc`. Review: [Draft PR #1](https://github.com/Lord1Egypt/DragonLord-Emulator/pull/1), branch `phase0/architecture-feasibility`. The PR identifies the resulting package commit. No changes to main, legacy engine, previous evidence or pristine upstream working sources.

## Independent acceptance outcomes

| Gate | Status | Executed evidence and limit |
|---|---|---|
| Modern CI | **PASS** at `aabc06f` | [Hosted run 41773385571](https://github.com/Lord1Egypt/DragonLord-Emulator/actions/runs/41773385571), Linux/Windows integrity/harness/lint/PS parsing and separate corrected fence job. PR checkout tree equals the published head tree. Full logs and exact checkout metadata retained. |
| Fence correction | **PASS**, source callback units | Original 26: 24 PASS/2 FAIL; corrected 26/26. Extended original 9 PASS/3 FAIL; corrected 12/12. Actual compiled extracted callbacks, not QEMU/GPU runtime. |
| Native Gfxstream compilation | **PASS**, isolated overlays | Real Windows clang-cl build of backend DLL and two test executables; compiler/configure/build exits captured. Pristine build failed; documented header define and one-line printf correction required. |
| Actual hardware rendering | **PASS**, Gfxstream host compositor only | 90 executions, real image writes/composition/readback, NVIDIA RTX 2060, matched process/adapter positive GPU Engine counters; no software module observed in hardware run. No guest API streaming, GLES HAL, presentation or QEMU evidence. |
| Independent GPU verification | **FAIL**, strict hardware/software control | Positive hardware telemetry exists; every software counter sample is invalid, so measured zero GPU activity cannot be claimed. Both named ETW attempts fail access denied. Runs are distinguishable by selected device and loaded software ICD, but the complete independent tracing/control criterion is not met. |
| Rutabaga FFI/ABI correctness | **BLOCKED**, partial tests PASS | Actual Windows FFI core and Gfxstream-feature builds/link/load PASS. Corrected C fence header: 113 boundary/core tests PASS against each FFI DLL. Original field-width control FAIL. Full renderer ABI, GPU handles/blob mappings, callback shutdown and cross-compiler QEMU linkage remain unqualified. |
| QEMU Windows integration | **BLOCKED** | Intentionally not attempted while independent tracing and critical pointer lifetime remain unresolved. A native Rust MSVC DLL does not prove MinGW QEMU linkage/runtime correctness. |
| Shared-memory/fence lifecycle correctness | **NOT TESTED**, integrated path | Standalone Win32 retirement reference 14/14 and CPU Gfxstream timeline units 140 executions PASS. QEMU MemoryRegion/RCU/WHPX readers, real asynchronous GPU callbacks, reset/hot-unplug and context-ID reuse are not exercised. |

These gates are deliberately independent. A failed original control remains FAIL; a successful archive extraction is not BUILD PASS, BUILD PASS is not GPU PASS, and host-compositor GPU PASS is not integrated emulator PASS.

## CI and upstream correctness recovery

The [full original legacy log](evidence/ci/legacy-job-126330694303.log) identifies three unavailable MSYS2 packages before compilation. The legacy workflow is now manual, explicitly unqualified, using UCRT64/direct dependencies. Its [actual retry](evidence/ci/legacy-retry-job-126372988614.log) passes MSYS2 package setup, then **FAILS** configure with `ModuleNotFoundError: No module named 'pwd'`. Compilation was not reached. This failure has not been suppressed or represented as modern QEMU status. See [revision-bound CI summary](evidence/ci/status-at-7904adf.json) and complete modern job logs alongside it. The completed package also passes [run 41773385571](https://github.com/Lord1Egypt/DragonLord-Emulator/actions/runs/41773385571) at `aabc06ff581b3691a86375ff429c8062b2a6c2fa`: [checkout/head/tree and job identity](evidence/ci/recovery-run-41773385571.json), with all three full job logs retained. GitHub checked a synthetic PR merge commit; its tree hash exactly matches the branch head, not an assumed revision.

[QEMU upstream dbb53a7c](https://gitlab.com/qemu-project/qemu/-/commit/dbb53a7caa04d4e12e93f83511640247a2fd49d6) adds the missing context-ID match to per-ring fence selection. It is absent from pinned v11.1.3 commit `005c61c0ef6f6ae615283440b4bb7be51b2c6ddd`. The exact upstream patch is applied to a copied file, preserving pristine source. [Source/patch identities](evidence/upstream-fence-identity.json), [commands and results](evidence/fence-overlay/result.json) retain baseline and corrected outcomes. The additional 12 cases exercise context/ring isolation, full-width ordering, duplicate/out-of-order/unknown callbacks and scaffold queue-drain/new-context reset. They do not prove live device reset, callback quiescence or context-generation isolation.

## Native toolchain and build

The [provisioning record](evidence/native-provision/result.json), [cryptographic verification](evidence/toolchain-verification.json), [build attempts](evidence/native/) and [reproduction instructions](REPRODUCE.md) establish exact tool/source/binary provenance. Existing VS 2022 Build Tools 17.14, MSVC 14.44.35207 and SDK 10.0.26100.0 supply linker/headers/libraries. Portable official LLVM 23.1.5 and Rust 1.88.0 were extracted into `C:\DLGPU\p06-20261104`; no installer, global PATH, registry, GPU driver, security or virtualization change was made. Primary sources/build/results use short native paths; WSL UNC paths are only script/command entry points.

LLVM archive SHA256 `b2be33385ddc86e83511417a060de927ae8b09d1f3017cc3cdce5c73cd5029d7`; detached signature verified with fingerprint `FFB3368980F3E6BB5737145A316C56D064CACBA5` from official HTTPS release keys. GPG's untrusted Web-of-Trust warning is retained; signature validity is not a claim of independently established signer identity. Rust archive SHA256 `4c5bafcfbb25a2a3b21cb5934d18c70d370b504b518c0119fda51aee7887e7c2` matches the official pinned channel manifest; no independent Rust signing-key validation was performed.

The native build uses pinned Gfxstream `94240f814c0097a63027ae680ea4bec7b0cb25f7`, GoogleTest `52eb8108c5bdec04579160ae17225d66034bd723`, Ninja/CMake and Release clang-cl with two workers. ASTC CPU decoding and host tracing are disabled for this bounded build, not qualified features. Failure sequence is retained:

1. Initial environment capture bug left LIB empty; fixed key/value capture, original logs preserved.
2. Pristine compile failed Winsock 1/2 duplicate definitions. Scoped C/C++ `WIN32_LEAN_AND_MEAN` prevents windows.h importing winsock.h before WinSock2.h.
3. Compile with the define exposed a real `std::string` passed to `%s` variadic logging. Clang correctly rejected it. The [one-line `.c_str()` correction](gfxstream-printf-argument.patch) is applied only to the native experimental copy; no diagnostic was disabled.
4. Incremental native build **PASS**: [build 4](evidence/native/gfxstream-native-4/result.json). A further copied-test-only [device-observation overlay](gfxstream-device-observation.patch) prints Vulkan device identity/LUID and asserts expected vendor/device type. [Build 5](evidence/native/gfxstream-native-5/result.json) also **PASS**. It does not change compositor rendering algorithms or golden comparisons.

Large warning logs are stored in full, losslessly compressed with raw-byte hashes. Numerous upstream compiler warnings remain; BUILD PASS is not a clean static-analysis or security verdict. A second independent clean rebuild has not been performed. The CMake test environment normally forces SwiftShader, so these runs invoke the executable directly under recorded child-only environment controls.

| Final observed artifact | SHA256 |
|---|---|
| `gfxstream_backend.dll` | `b8df95cc18ab1ae7494a21b4c7cd1ccc0f79b2910659bcebc5a69c25bd49a5b0` |
| instrumented `Vulkan_unittests.exe` | `4a9f453d3fdde4bd267afbb2a7bb13a10113bfc6d32be8742ed59e46798aec11` |
| `OpenglRender_unittests.exe` | `6f05d674af4202d0ca500620571643fdd6689de514c5c8f7bcc502f5ae752925` |

No binary/tool archive or build directory is published. PE imports and sampled runtime-loaded module hashes are retained separately. Short-lived modules can be missed between polls; complete dynamic image-load closure remains unqualified without a successful trace. Actual linked Rust registry resolution is captured in Cargo lockfiles and metadata, not described as unspecified latest dependencies.

## Executed rendering and independent attribution

The workload is the actual pinned Gfxstream `CompositorVk`, reached through its upstream `CompositorVkTest` executable. It is not a separate direct-Vulkan triangle claimed as Gfxstream proof. Three tests repeat 30 times on the same instrumented binary in each control:

- `EmptyCompositionShouldDrawABlackFrame`: ten 256×256 images are written/read as red, composed with empty layers, waited to completion and read back as black. Pixel mismatch calls `ADD_FAILURE`.
- `SimpleComposition` and `SolidColor`: real images, composition completion waits and per-pixel comparison against pinned golden PNGs (channel tolerance 4). All compared images are square, avoiding the existing helper's rectangular indexing limitation.

[Hardware raw record](evidence/native/gfx-final-hardware/result.json), [test log](evidence/native/gfx-final-hardware/stdout.log), [software raw record](evidence/native/gfx-final-software/result.json), [test log](evidence/native/gfx-final-software/stdout.log), and [machine qualification](evidence/renderer-qualification-final.json) are the primary evidence. GoogleTest XML reports only the last repeat; complete raw logs establish 90 successful executions per run. Test discovery alone is not counted as execution. No skip or zero-test PASS is accepted.

Hardware process **11428** selected NVIDIA GeForce RTX 2060, vendor `0x10de`, device `0x1f11`, discrete type 2, Vulkan **1.4.351**, driver **617.42** / Windows file version **32.0.16.1742**. Device LUID bytes `f923010000000000` correspond to Windows counter LUID `0x00000000_0x000123f9`. The system loader is 1.4.341.0; NVIDIA `nvoglv64.dll` is hardware-vendor signed and hashed in the runtime record. Intel's ICD was also enumerated/loaded; selected-device assertions identify NVIDIA. No SwiftShader/WARP/LLVMpipe/Lavapipe module is observed in this hardware process.

Windows GPU Engine telemetry is independent of Gfxstream's logging: six valid, positive process/adapter engine samples match PID 11428 and this LUID, including 3D and copy engines. These sparse samples support actual GPU-backed execution of the compositor. They are not an FPS, saturation, latency or frame-pacing benchmark.

Software process **8252** selects SwiftShader Device (Subzero), vendor `0x1ae0`, CPU type 4, Vulkan 1.3.0, with `VK_DRIVER_FILES` explicitly naming the existing Chrome 156.0.8078.80 SwiftShader manifest. DLL/manifest provenance is recorded; browser files were not changed or redistributed. The same 90 pixel tests pass. An NVIDIA DLL is also loaded in the software process: DLL presence alone never proves execution or zero activity.

The software PID's GPU counters all carry invalid status `0xc0000bc6`. Their numeric zero values are **not measured zero GPU usage**. A second two-sample rate-counter attempt retains the same invalid state. Thus the trace/control oracle fails closed. Named `Microsoft-Windows-DxgKrnl` ETW capture returns access denied `0x5`; no existing ETW session was stopped and no elevated tracing/security configuration was silently enabled. Resolve tracing permissions through an appropriate Windows testing environment, then capture/analyze process/device-attributed queue execution and validate both controls.

An initial empty `VK_DRIVER_FILES` override yielded no Vulkan ICD, a failed `vkCreateInstance` and upstream fixture teardown crash. That negative execution is retained. The runner now removes null-valued override variables instead of setting them to empty strings. This is a harness correction, not an ICD/driver installation change.

No emulator FPS, frame pacing, input-to-photon latency, Android memory/boot time, sustained stability or comparative performance claim follows. Per-test times include device/context setup/teardown and instrumentation; the raw CPU/memory observations are sparse, sampled before the counter query and not comparable benchmarks.

## ABI, handles, ownership and retirement

Pinned Rutabaga `4f2bcaf71a6497583362ed664d9fe21cc5043049` / 0.1.85 builds natively for `x86_64-pc-windows-msvc`. Core-only FFI **PASS**; Gfxstream-feature first link **FAILS** when pointed at the build root, then **PASSES** with `GFXSTREAM_PATH_RELEASE=<build>\host`, where the actual import library resides. DLL load and 113 core tests also pass with the Gfxstream-feature DLL; capset mask 0 deliberately chooses the CPU Rutabaga2D component. This is not a streamed guest Gfxstream backend test.

The real C header has `uint32_t ring_idx`; actual Rust `repr(C) RutabagaFence` and Gfxstream use `u8`. Native x64 fence size 24, alignment 8 and field offset 20 agree, which conceals the width bug. An original compile-time assertion **FAILS**. The executable observation control **FAILS 2 checks**: Rust writes 63 to one byte while C reads `0xa5a5a53f` (2779096383) from deliberately initialized padding. This is concrete ABI evidence, not an assumed layout mismatch.

A copied C header with the [single-field width correction](rutabaga-ring-width.patch) passes 113 C/actual-Rust boundary tests against the core DLL, and 113 against the Gfxstream-linked DLL. Tested boundaries include caller-owned fence storage, offsets/alignment/width, full-width ID values, invalid sentinels, borrowed HANDLE duplication, owned drop, import/export and close-on-failure; 20 actual FFI cycles cover CPU resource allocation, changing byte-pattern transfer/readback, bounded/overflow rejection, detach/unref, fence callback and finish clearing the opaque pointer. See `evidence/native/abi-*-2/`, [Gfxstream-linked run](evidence/native/abi-gfx-run/result.json), source and compile command hashes.

HANDLE tests use the actual crate's Windows OwnedDescriptor implementation, not duplicated Rust fence/descriptor definitions. The opaque FFI allocation is created and destroyed by the same Rust DLL. C never frees a Rust/C++ allocation, and neither the reference tests nor DLL-link success approve arbitrary cross-CRT heap sharing. GPU exported handles, duplicated cross-process handles, failure during live graphics submission and long-lived callback ownership remain unverified.

The standalone [Win32 mapping reference](experiments/mapping_retirement.cpp) uses bounded subtraction-based range checks, generation-tagged leases, retirement that rejects new leases/callbacks, reader draining, timeout retention, and unmap-before-close. Fourteen native assertions pass, including a concurrent reader and 100 lifecycles with process handle count 57 before/after. This is **a reference design**, not the pinned Rutabaga Windows mapping implementation and not QEMU RCU/WHPX retirement proof. The actual pinned Windows shared-memory/mapping helpers still return Unsupported on the audited paths.

The pinned [QEMU blob path](https://gitlab.com/qemu-project/qemu/-/blob/v11.1.3/hw/display/virtio-gpu-rutabaga.c) explicitly documents a MemoryRegion pointer dereference-after-unmap risk. Deleting a subregion then immediately calling renderer unmap does not establish that RCU readers, memory listeners, WHPX mappings or in-flight operations have drained. Async callback scheduling retains a raw device pointer; reset/unrealize/cancellation must be audited and tested. Context-ID filtering does not establish generation safety after ID reuse. Treat both as critical engineering blockers, not acceptable residual risks.

A future retirement implementation must prevent new exposure/submissions, invalidate generations, remove the region transactionally, retire accelerator mappings, drain GPU jobs/callbacks and QEMU readers on the right thread, retain allocation owners until all users release, then unmap/free/close through the originating runtime. Timeout must retain ownership rather than free early. This must be proved with extracted-real-code concurrency tests and later an instrumented device experiment; a hand-written lease model alone cannot pass it.

## Guest path, security and licensing

The [source-linked matrix](COMPATIBILITY.md) distinguishes documentation, build and runtime. Android 16 source paths from Phase 0/0.5 remain available, but host pin 94240f8 and Android 16 guest pin 7e9d595 differ. No protocol pairing, Android EGL/Vulkan HAL, gralloc/mapper, composer/fence handles, kernel virtio-gpu/blob/coherent mappings, Android boot, CTS/VTS or KernelSU test is performed here. No image build started.

[Security/license review](SECURITY-LICENSES.md) records boundaries and obligations. QEMU/Gfxstream combined-program license compatibility remains unresolved; neither a DLL nor process boundary automatically clears it. Tools, GoogleTest, Gfxstream third parties, Rust crates and software-control artifacts have separate terms. Only small source patches, our experimental code and text/compressed logs are published. No guest-memory feature or binary distribution is approved until critical ownership and licensing questions close.

Recommended next phase: [bounded recovery tickets](NEXT.md), prioritizing valid tracing controls and a QEMU-specific retirement/ownership proof, followed by legal link-graph closure. Reopen a minimal QEMU device experiment only after those prerequisites pass; full migration remains closed.
