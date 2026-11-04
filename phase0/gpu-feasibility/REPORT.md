# Phase 0.5 — Windows GPU feasibility

Review date: 2026-11-04. Starting revision: `d74a521f7933baeeb771f412cb9261c3311ded62`. Branch: `phase0/architecture-feasibility`. External review: [Draft PR #1](https://github.com/Lord1Egypt/DragonLord-Emulator/pull/1).

**Recommendation: NO-GO for adopting the Windows QEMU/Rutabaga/Gfxstream graphics foundation or beginning migration.** Continue a limited tooling and correctness validation phase. This experiment did not demonstrate physical GPU rendering through Gfxstream. It does not establish that the architecture is impossible.

The native Windows build attempt stopped at a reproducible missing-toolchain gate: CMake invoked MSBuild, which returned **MSB8020: ClangCL build tools cannot be found**. The user required stopping at unavailable tooling, so no compiler installation, alternative renderer, Android image build or full engine port was attempted. Separately, a deterministic host-unit probe of the unchanged QEMU fence callback failed context isolation. Both issues must be resolved before promotion; an unsafe mapping lifetime is also explicitly acknowledged in the upstream source.

## Gate results

| Gate | Status | Evidence and precise scope |
|---|---|---|
| G1: standalone Windows Gfxstream hardware rendering | **BLOCKED** | [Native configure](evidence/gfxstream-configure/result.json), [MSBuild diagnostic](evidence/gfxstream-configure/configure.stderr.log): configure exit 1, missing ClangCL. No renderer binary/workload was executed. |
| G2: independent hardware execution, software excluded | **NOT TESTED** | Depends on G1. Vulkan/NVIDIA inventories identify available devices only. No selected Gfxstream device, pixels, loaded-module evidence or correlated GPU trace exists. |
| G3: QEMU/Rutabaga Windows compatibility | **BLOCKED** | [Dependency probe](evidence/rutabaga-dependency/result.json) actually fails to find `rutabaga_gfx_ffi`; native Rust/Cargo not found. Windows utility stubs and an FFI field-width discrepancy are source-level gaps; full DLL ABI/device runtime untested. |
| G4: resource sharing and fence behavior | **FAIL** | [Unchanged callback host-unit probe](evidence/fence-probe/result.json): two context-isolation cases fail. This is Linux host-unit evidence, not a Windows VM test. Guest-to-host allocation/map/import/export and physical GPU fences remain NOT TESTED. |
| G5: documented Android 16 graphics integration path | **PASS** | Source/BSP/driver/HAL path and required missing work are mapped in [COMPATIBILITY.md](COMPATIBILITY.md). PASS is for this documented path only; Android boot and driver/HAL interoperability are NOT TESTED. |
| G6: reproducibility and regression acceptance | **FAIL** | Original 9 harness tests and new 8 evidence-integrity tests pass; native scripts parse, source identities and prior artifacts validate. The separate fence correctness probe fails 2/26 cases and rendering/lifecycle/reset tests cannot run. The regression gate is not promoted by green evidence-tool tests. |

## Phase 0 revalidation

All four requested documents were read and checked against their records. The [validator](tools/validate-phase0.py) checked the published index and all **77 indexed artifacts**, both retained serial nonce/architecture responses, strict accelerator argv, and all three locally retained executable hashes. It reran the nine original harness tests successfully. See [result](evidence/phase0-validation/result.json). This revalidates saved evidence; **it is not a new WHPX or TCG boot**. The original result directories were not edited.

The [official download page](https://www.qemu.org/download/) still reports QEMU **11.1.3**. The separate pristine source is commit `005c61c0ef6f6ae615283440b4bb7be51b2c6ddd`. Phase 0 configuration logs agree: Linux enables TCG/KVM and Pixman, with OpenGL/Rutabaga disabled; Windows enables TCG/WHPX, with Pixman/OpenGL/Rutabaga disabled. Thus the Windows diagnostic binary is not a 3D integration build. The original native WHPX boot is backed by a fresh guest response, clean QMP shutdown and unchanged disk hash, with one interrupt-vector warning and no long-run qualification.

The Phase 0 local milestone was published **before** GPU work. `git ls-remote` and the GitHub PR response agreed on branch head `d74a521f7933baeeb771f412cb9261c3311ded62` and unchanged main `c5447ed4baf97d93e3a87c62534ed7d300d288de`; PR #1 is draft. The previous main/history/legacy and evidence are retained.

## Native attempt and available hardware

The tested Gfxstream source is pristine commit `94240f814c0097a63027ae680ea4bec7b0cb25f7`. A real Windows CMake process ran against it using `Visual Studio 17 2022`, x64, `ClangCL`, standalone mode and upstream test targets enabled. CMake 4.3.2 selected SDK 10.0.26100.0, then MSBuild 17.14.60 rejected the missing toolset. No Gfxstream compilation occurred. Installed MSVC is not evidence that the documented ClangCL path is provisioned. The native MSVC alternative was not tested; no claim is made that every possible Windows compiler configuration fails.

| Observation | Captured value | What it establishes |
|---|---|---|
| OS/tooling | Windows 11 Pro 10.0.26300; VS Build Tools 17.14.37827.9; MSVC directory 14.44.35207; CMake 4.3.2 | Native tooling inventory, not Gfxstream build support. |
| Vulkan loader | 1.4.341.0; `vulkaninfo --summary` exit 0 | Loader/device enumeration works. |
| Discrete GPU | NVIDIA RTX 2060, PCI `10de:1f11`; Vulkan API 1.4.351; NVIDIA driver 617.42 / Windows 32.0.16.1742 | Available proprietary hardware ICD. `nvidia-smi` independently reports PCI bus `00000000:01:00.0` and driver 617.42, exit 0. Neither command is a rendering workload. |
| Integrated GPU | Intel UHD 630, PCI `8086:3e9b`; Vulkan API 1.1.95; Windows driver 25.20.100.6519 | A second available adapter; not selected by Gfxstream. |
| Gfxstream adapter/API/backend actually used | **None; NOT TESTED** | No renderer executable ran. The candidate is hardware Vulkan plus a qualified EGL/GLES implementation. |
| EGL/GLES runtime DLLs | `libEGL.dll` and `libGLESv2.dll` not found in PATH/System32 search | A scoped discovery gap, not proof that no usable copies exist anywhere on the host. |
| Trace tools | `wpr.exe` and `xperf.exe` found | Acquisition/attribution was not exercised; no GPU trace or utilization measurement is claimed. |

Raw stdout/stderr, command arguments, exit codes and inventory utility hashes are in [host evidence](evidence/host/host.json) and [toolchain inventory](evidence/toolchain/toolchain.json). Vulkan loader warnings about installed overlay layers are retained. Instance external-memory/fence extension names were enumerated, but external Win32 handle compatibility for a specific image/buffer format was not queried or tested. An enumerated capability is not an allocation/import success.

The first native source preflight failed because Git for Windows reports the WSL-hosted `.kokoro/continuous.cfg` CI symlink as a type change. That attempt is retained. The runner tolerates exactly that non-build CI entry; Linux Git independently verifies the entire tracked source is pristine. This does not establish that a future full build from the long UNC path is supported. Prefer a short local Windows checkout for a newly provisioned build.

## Why default upstream tests cannot prove G2

The pinned [Windows CTest environment](https://github.com/google/gfxstream/blob/94240f814c0097a63027ae680ea4bec7b0cb25f7/toolchain/cmake/SetWin32TestEnvironment.cmake.in) prepends GLES SwiftShader and sets both Vulkan ICD variables to `vk_swiftshader_icd.json`. The source also has explicit software-driver selection and test-mode behavior in [vulkan_dispatch.cpp](https://github.com/google/gfxstream/blob/94240f814c0097a63027ae680ea4bec7b0cb25f7/host/vulkan/vulkan_dispatch.cpp). A normal CTest PASS is therefore a useful software control, not hardware proof.

After the build gate is reopened, select a direct upstream rendering executable/test case, record its compiled options and effective environment, remove software-test overrides for the hardware arm, and verify actual selected physical device plus loaded driver DLLs. `ANDROID_EMU_VK_SELECT_GPU` is a selection hint in the pinned implementation; its failure can fall back to scoring another device, so it is not a hardware assertion. The acceptance process must reject an unexpected device/type or software DLL. EGL/GLES through ANGLE additionally needs the actual ANGLE backend and DXGI adapter, excluding WARP/reference rendering.

Independently correlate the renderer PID and workload interval with physical-adapter engine execution using ETW/GPUView or validated equivalent; check the output/readback against known pixels. Run a deliberately selected software renderer and demonstrate that the same observation pipeline distinguishes it. Installed GPUs, `vulkaninfo`, `nvidia-smi`, renderer strings, timing or high FPS alone are insufficient. No such hardware/software pair was run here. See [test protocol](TEST-PLAN.md).

## Fence reproduction and memory/lifetime risks

The host-unit probe extracts **only** `virtio_gpu_rutabaga_aio_cb` unchanged from the pinned QEMU source and compiles it with the real QEMU queue/virtio and Rutabaga C headers. Minimal enclosing structs and the response sink are test scaffolding. The callback digest is `1608fce69368e4d3229e2383c91bba253693f767698d7a5702b35bc0e898d976`; the original file digest and exact compile/execute argv are recorded. Compilation returns 0; execution returns 1.

With a context-specific signal for context 1/ring 0/fence 7, the callback completes a queued context 2/ring 0/fence 7. With both contexts queued, it completes two commands where one is expected. Different-ring, future-fence and global-versus-context mode controls pass; 20 repetitions of scaffold allocation/queue cleanup also pass. **24 cases pass, 2 fail.** These repetitions do not test renderer creation/destruction or device reset.

The [virtio specification](https://docs.oasis-open.org/virtio/virtio/v1.3/csd01/virtio-v1.3-csd01.pdf), section 5.7.6.7, defines context-specific timelines using both context ID and ring. The observed isolated callback checks ring/mode/fence sequence without matching context ID. This demonstrates that local selection defect; it does not establish end-to-end guest reachability, exploitability, GPU ordering behavior or a Windows driver defect. No upstream source patch was made.

In the same [QEMU release source](https://gitlab.com/qemu-project/qemu/-/blob/v11.1.3/hw/display/virtio-gpu-rutabaga.c), blob mapping registers a renderer-owned pointer as a RAM MemoryRegion. Its comment explicitly acknowledges a possibility of dereference after unmapping. Treat that as a **blocking lifetime-review item**, not acceptable because the source calls it unlikely. Require MemoryRegion/RCU/WHPX mapping retirement before renderer unmap/free, bounded offsets/sizes and overflow handling, and cancellation/draining of queued callbacks before teardown. Reset/device removal during active mappings and fences must be tested with sanitizers and stale-access guards. No such runtime tests were possible here.

An additional ABI review is necessary: the pinned Rutabaga C header declares `rutabaga_fence.ring_idx` as `uint32_t`, whereas its Rust alias and Gfxstream C API use an 8-bit field. Equal structure size/offsets do not settle padding/read-width correctness. This is source evidence of a contract discrepancy, not a measured FFI corruption. Verify all C/Rust/MinGW/ClangCL field widths, offsets, calling conventions and round trips before combining binaries.

## Dependency and security obligations

Keep the renderer in a trusted local diagnostic process with synthetic inputs initially. A future guest boundary sends attacker-controlled lengths, IDs, descriptors and API commands into a host decoder and vendor driver. No guest pointer becomes a native HANDLE or host pointer without validated translation. Check ownership transfer, invalid/sentinel handles, full 64-bit width, duplicate/close behavior, resource bounds and failure rollback. FFI unwind catching does not validate raw pointers or prevent every abort/use-after-free. Keep management endpoints local and guest networking/sharing disabled during first integration. Do not disable global host protections or install drivers to make a gate pass.

The exact combined distribution has not been built or licensed for delivery. QEMU has per-file GPL terms; this Rutabaga QEMU file is GPL-2.0-or-later, which must not be confused with a whole-program GPLv3 conclusion. Gfxstream is Apache-2.0; Rutabaga metadata includes BSD-3-Clause and MIT/vendored Mesa components. [FSF guidance](https://www.gnu.org/licenses/license-list.html#apache2) distinguishes Apache compatibility with GPLv3 from GPLv2-only. Inspect the complete compiled link graph and all exceptions before distribution; a DLL/process boundary does not automatically resolve it. Preserve copyright/notices, appropriate source/build materials, GLib LGPL obligations and every selected dependency's terms.

Clang/LLVM, MSVC/SDK tools, GoogleTest, ANGLE, vendor ICD DLLs, Python/Rust dependencies and optional software controls require exact provenance and their respective licenses. Do not copy arbitrary browser-bundled EGL DLLs into a distributable or claim the current PATH search produced a license-clean runtime. Independent signature checks and an SBOM remain open. Only our scripts/reports/small logs are published; no compiler, renderer DLL, VM disk or Android artifact is uploaded.

## Blockers and recommended next phase

| Blocker | Resolution / definition of done |
|---|---|
| Missing native ClangCL toolset | Provision the documented Visual Studio Clang components or an explicitly chosen isolated toolchain; record versions/provenance; rerun the unchanged configure/build script into fresh directories. This phase stopped before provisioning. |
| Test/dependency closure not reached | Resolve GoogleTest and the selected EGL/GLES/Vulkan implementation with pinned manifests. Build real upstream rendering tests; do not infer closure from compiler detection. |
| G1/G2 hardware proof missing | Complete hardware and deliberate software-control runs with correct pixels, selected API/device/driver, loaded-module list and independent PID/adapter trace attribution. |
| Rutabaga FFI missing; ABI discrepancy | Pin a native Rust toolchain (repository requests 1.88.0), build/link the FFI to the exact renderer, generate/import a MinGW-compatible C library boundary, and pass layout/ownership/callback tests. |
| Windows utility stubs | Keep Linux-specific cross-domain/Wayland off. Determine whether the direct Gfxstream map path meets the minimal use case; implement only proven missing Windows primitives later, with ownership and failure tests. No blanket claim that all map paths are unavailable. |
| Fence isolation and pointer retirement | Review/fix the actual callback context matching and mapped-pointer retirement in a separate narrowly scoped change; this probe and an integrated multi-context/reset test must pass. No workaround that ignores the defect. |
| Android protocol/BSP gap | Qualify an existing complete Android16 artifact and resolved manifest on Linux/KVM, then align host/guest protocols/HALs. No image build is authorized here. |
| License/security closure | Review exact linked artifacts, SBOM/source/notices and the guest-memory threat model before architecture adoption or release. |

Recommended next phase: **a bounded Phase 0.6 tooling and correctness follow-up**, starting with the native ClangCL/dependency gate, the fence and ABI review, then standalone hardware rendering. Attempt a minimal WHPX virtio-gpu integration only after those prerequisites pass. Keep full migration, Android image development and KernelSU runtime work deferred. Continue on the same development branch and Draft PR, never auto-merge. See [README](README.md) for reproduction and [COMPATIBILITY](COMPATIBILITY.md) for the integration map.
