# Phase 0 architecture validation and feasibility report

Review date: **2026-11-04 Europe/Istanbul** (evidence timestamps use UTC). Branch: `phase0/architecture-feasibility`. Legacy/main commit: `c5447ed4baf97d93e3a87c62534ed7d300d288de`.

## Verdict

**NO-GO for committing to the proposed Windows accelerated graphics architecture or starting full migration/Android image development today.** The candidate has credible documented components, but no end-to-end Windows GPU or Android 16 runtime evidence. Continue the narrow feasibility experiments in the roadmap. This is not a conclusion that Gfxstream cannot work; it is a conclusion that the required acceptance evidence does not yet exist.

Preferred candidate for validation: clean upstream QEMU + standard virtio-gpu PCI + Rutabaga C FFI + Gfxstream, with a matching Android 16 Cuttlefish-derived guest graphics stack and a native Windows presentation path. CPU acceleration is WHPX on Windows; Linux/KVM is the reference comparison. Native hardware Vulkan/EGL support, memory sharing and fences need explicit qualification. See [GPU comparison](GPU-BACKENDS.md) and [guest integration](GUEST.md).

## What was verified

The official [QEMU download page](https://www.qemu.org/download/) reports **11.1.3**, released 2026-10-28. Its official GitLab tag resolves to `005c61c0ef6f6ae615283440b4bb7be51b2c6ddd`; the cloned release's VERSION agrees. This release was cloned separately under ignored `phase0/.work`, not merged over the legacy import. It has its own modern Meson/Kconfig build and pinned subprojects. Moving to it would be a future migration, not a rename of the QEMU 5.0.50 tree.

A clean Linux x86_64 system-emulator build passed using isolated dependencies. The reusable build entry point was run successfully. Its binary hash, configure argv, compiler/tool versions and logs are in [build evidence](evidence/build-linux.json) and [configure log](evidence/configure-linux.log). This profile intentionally omits OpenGL, VirGL and Rutabaga; the compiled presence of KVM is not a KVM runtime test.

The binary booted the checksummed guest kernel/rootfs selected by QEMU's own [x86_64 Tuxrun functional test](https://gitlab.com/qemu-project/qemu/-/blob/v11.1.3/tests/functional/x86_64/test_tuxrun.py). The Linux 6.4.16 guest logged in, executed a fresh readiness nonce and returned x86_64; QMP quit cleanly and the base disk hash remained unchanged. The first attempt failed because QEMU's default temporary directory was read-only; the runner now gives each run a local temporary directory, and both attempts are retained. This is a Linux TCG CPU/boot experiment only. Its measured duration is not an Android or GPU benchmark.

The nine initial evidence-gate unit tests passed. They exercise no-acceleration-fallback behavior, snapshot protection in argv, guest-response validation, checksum rejection and honest blocked classifications. They are harness tests, not emulator conformance tests. See [test log](evidence/harness-tests.log).

The isolated Windows cross-build also passed with WHPX enabled and graphics libraries disabled. Its dependency lock includes six Ubuntu MinGW archives, eight MSYS2 archives and a pinned current MinGW WHPX definitions header. The packaged older header initially failed on missing VMX capability definitions; that [failure log](evidence/cross-build-initial.log) is retained. Updating only the isolated dependency header resolved compilation without patching QEMU. See [cross-build result](evidence/build-windows-cross.json), [configuration](evidence/configure-windows-cross.log) and [dependency lock](windows-cross.lock.json). The resulting PE executable ran natively on Windows and listed `whpx` and `tcg`; this is distinct from a successful accelerated guest boot. The native inventory/test executable was copied before a second successful build, so its separately recorded binary hash differs from the rebuild hash; neither is presented as bit-for-bit reproducible.

The subsequent **native Windows WHPX diagnostic boot passed**: QEMU was invoked with only `-accel whpx`, the same verified Linux 6.4.16 assets and temporary disk snapshot; the guest logged in and executed a fresh nonce plus `uname -m`, then QMP shutdown succeeded and the base disk hash was unchanged. See [result and exact argv](evidence/windows-whpx-boot/result.json), [serial response](evidence/windows-whpx-boot/serial.log) and [QEMU stderr](evidence/windows-whpx-boot/qemu.err.log). One interrupt-vector warning was emitted; this single boot does not establish long-run stability. The recorded 3.52 seconds from process start to diagnostic readiness is neither an Android benchmark nor a controlled TCG/WHPX comparison. Slow UNC asset hashing occurred outside that boot timer. No GPU device or renderer was tested.

## Gate ledger

| Gate | Result | Evidence or blocker |
|---|---|---|
| Original/main/history preservation | PASS | [preservation.json](evidence/preservation.json); no changes outside `phase0/`. |
| Current upstream release/commit identity | PASS | Official release/tag, VERSION, locked commit. |
| Clean modern Linux build | PASS | Actual successful build; binary hash/configure logs captured. |
| Diagnostic Linux TCG boot | PASS | [result](evidence/tcg-boot/result.json), serial and QMP logs. |
| Unchanged legacy transport compiles against modern headers | FAIL | 3/4 probed units fail; [compiler diagnostics](evidence/legacy-api/result.json). This is an audit outcome, not an attempted migration. |
| Windows cross-build and native WHPX diagnostic boot | PASS | [Cross-build](evidence/build-windows-cross.json), [native boot](evidence/windows-whpx-boot/result.json) and guest-response logs; CPU-only, no fallback. Native MSYS2 alternative not tested. |
| Linux/KVM execution | BLOCKED | `/dev/kvm` absent in this WSL session. Runner refuses software fallback. |
| Gfxstream/Rutabaga native Windows renderer+transport | BLOCKED | No built/validated renderer, negotiated VM capsets, shared-resource round trip or graphics workload. |
| Android 16 x86_64 boot | BLOCKED | Source/BSP candidate identified, no qualified complete guest artifact/VM device mapping or boot. ADB inventory had no connected guest. |
| KernelSU integration | BLOCKED | Configuration and requirements inspected; no modified kernel build/load/boot/permission tests. |
| FPS/pacing/latency/resource/stability targets | BLOCKED | No Android GPU workload; protocol defined in BENCHMARKS.md. |
| Distributable graphics link/license closure | BLOCKED | Exact combined-program obligations and dependency notices require review before adopting/releasing the backend. |

Windows read-only inventory succeeded outside the sandbox and reported **Windows 11 Pro 10.0.26300, RTX 2060, Intel UHD 630, and a WHPX DLL**. No QEMU executable was found in PATH and no compiler at `C:\msys64\mingw64\bin\gcc.exe`; a Visual Studio installation was detected. These are scoped observations, not proof that no compiler exists elsewhere. Initial sandboxed PowerShell interop failed; elevated read-only inventory overcame that restriction. Linux has no `/dev/kvm`, `/dev/dri` or `/dev/dxg`. These facts are in [host inventory](evidence/host.json) and [Windows inventory](evidence/windows-hardware.json).

The later [native QEMU inventory](evidence/windows-native-inventory/inventory.json) used our isolated cross-built executable and succeeded. Its first run was classified BLOCKED because an optional `vulkaninfo` warning was treated as a terminating PowerShell error; that attempt is retained separately, and the probe now records optional Vulkan diagnostics without invalidating the QEMU inventory. Even a successful Vulkan inventory is not rendering evidence. The Windows CIM `VirtualizationFirmwareEnabled=false` field does not negate the successful strict WHPX runtime result.

## Legacy compatibility audit

The original Direct Express/Express GPU code remains preserved. The source review follows its PCI wrapper, virtqueue call assembly, guest mappings, per-thread rings, completion/recycling, GL/EGL/cluster decoding, resource maps, shader transformation, graphic-buffer presentation/input and shutdown paths.

| Area | Legacy design | Modern 11.1.3 finding | Consequence |
|---|---|---|---|
| Build wiring | Root Makefile.objs and per-directory Makefile.objs plus Kconfig | Modern devices use Meson source sets plus Kconfig; legacy files are not registered there. | Additive wiring work would be needed even before an API port. |
| Header layout | `hw/qdev-properties.h`, `hw/pci/pci.h` conventions | Current core headers moved; direct PCI compile probe stops at the old qdev-properties include. | No unchanged source drop-in. |
| QOM realization | `object_property_set_bool(obj, true, "realized", errp)` and manual bus setup | Modern boolean setter order is `(obj, name, value, errp)` and current virtio PCI models use `qdev_realize`. | Adapt error propagation and realization deliberately. |
| QOM class data | Class initializer takes `void *data` | Current TypeInfo callback uses `const void *data`. | Function-pointer compatibility must be corrected. |
| Atomics | `atomic_read/set/cmpxchg` | Current APIs use `qatomic_*`; probes detect unresolved old names. | Renaming alone does not validate ring memory ordering. |
| Virtio initialization | `virtio_init(vdev, "direct-express", id, size)` | Modern `virtio_init` takes the device, numeric ID and config size; the name argument is gone. The compiler reports too many arguments. | Update initialization as part of a tested device port. |
| Virtqueue essentials | `virtqueue_pop`, `virtqueue_push`, `virtio_add_queue`, virtio feature callback | These facilities and the old-style get_features callback still exist. | Some conceptual infrastructure remains usable; not every API disappeared. |
| Virtio identity | Proprietary device ID 32 | [Modern virtio IDs](https://gitlab.com/qemu-project/qemu/-/blob/v11.1.3/include/standard-headers/linux/virtio_ids.h) assign 32 to SCMI. | Existing device/guest ABI collides with a standardized identity. Do not reuse it in a new guest. |
| Width/ABI assumptions | `uint64_t` declarations vs `unsigned long long` definitions, pointer casts | Linux LP64 probe catches a conflicting function declaration; Windows LLP64 behavior is a separate check. | Fix wire widths explicitly and validate both host ABIs. |
| Native graphics/window | Windows WGL, GLAD, GLFW, custom SDL handoff | External UI/window and threading integration remains a downstream maintenance surface. | A modern upstream device does not supply the legacy window semantics automatically. |
| Lifecycle | Global singleton queues/maps, Windows events; no complete reset/migration/unrealize registration | Current QEMU has explicit device and memory lifecycles; accelerated resource lifetime remains delicate. | Reset, stop, VM exit, context loss, cancellation and teardown need tests before reuse. |

Actual compiler probes used a generated modern virtio-gpu PCI compile command, modern headers/configuration and an overlay exposing only the original custom headers. No legacy header tree was allowed to mask modern QEMU headers. `direct_express.c`, `direct_express_pci.c` and `direct_express_distribute.c` failed; `express_handle_thread.c` passed Linux syntax only. The latter has empty non-Windows wait branches, so a syntax pass does not establish correct worker behavior or Windows compatibility. Express GPU's Windows translation units were source-audited, not fully compiled or executed.

Other source findings needing dedicated tests include batched-call parameter/offset validation, the same-surfaces shortcut in `d_eglMakeCurrent` before checking context changes, `d_eglGetSyncAttrib` output assignment, keyboard indexing based on a different value than the bounds check, inactive DSA default branches, and unreachable wait code in `draw_wait_GSYNC`. These are investigation targets, not fabricated runtime failures. The large GL decoder's 411 declaration/case matches and EGL's 34/33 match are only static coverage counts.

Relevant modern API sources: [virtio PCI example](https://gitlab.com/qemu-project/qemu/-/blob/v11.1.3/hw/display/virtio-gpu-pci.c), [virtio declarations](https://gitlab.com/qemu-project/qemu/-/blob/v11.1.3/include/hw/virtio/virtio.h), [QOM declarations](https://gitlab.com/qemu-project/qemu/-/blob/v11.1.3/include/qom/object.h), [atomics](https://gitlab.com/qemu-project/qemu/-/blob/v11.1.3/include/qemu/atomic.h).

## Missing dependencies and unresolved assumptions

- The legacy import lists 19 submodules but tracks no gitlinks; missing dependency trees and CRLF/non-executable configure are real reproducibility gaps. This mission did not normalize or repair that preserved import.
- The Linux baseline needed GLib/Pixman development headers, pcre2 metadata and Python build tools. They were downloaded/extracted into `.work`; no system packages were installed. Debian package filenames/hashes and the Python tool pins are recorded. Initial configure failures and their fixes were scoped to those local dependencies.
- A pinned Windows CPU diagnostic cross-build and local runtime DLL collection now exist. The selected Windows graphics libraries, renderer/FFI ABI and their full transitive dependency closure still need a working pinned build. Linux `.so` libraries cannot substitute for Windows DLLs. The alternative native MSYS2 build was not executed.
- A Cuttlefish-derived Android guest requires complete partition/boot artifacts, kernel/modules, graphics HALs and a device/host-service map. A system GSI or SDK emulator image is not a complete interchangeable PC guest.
- Host-visible memory, cache coherency under WHPX, resource sharing/fences and native presentation are unverified. Rutabaga's cross-platform API or Gfxstream's Windows tests do not prove their combination inside QEMU on this host.
- ARM app translation, Google Play/GMS, anti-cheat/attestation, video decode, suspend, accelerated snapshots and multi-VM operation are outside this initial experiment and carry separate compatibility/licensing requirements. None is implied by Android 16 x86_64 boot.

## Licensing and delivery gate

Keep the original GPL notices, source and history. A delivered QEMU/legacy binary needs the applicable GPL source/build-material obligations and notices, including any modifications; firmware has its own licenses. Track GLib LGPL obligations and relinkability, the exact compiler/runtime DLLs, and all renderer/third-party notices in an SBOM.

The inspected Gfxstream root license is **Apache-2.0**; Rutabaga identifies **BSD-3-Clause**. QEMU's LICENSE describes GPLv2 for the emulator with per-file variation. Apache-2.0 is not compatible with a GPLv2-only combined work according to the [FSF license compatibility guidance](https://www.gnu.org/licenses/license-list.html#apache2). This is a **release-blocking link-graph review**, not a declaration that every possible QEMU/Gfxstream build is unlawful: determine the actual compiled files, permissible license version, dependency boundaries, any exceptions and distribution model. Neither dynamic loading nor a separate process automatically settles that analysis. Do not change the repository license or assume upstream integration resolves the obligations for our build.

Mesa is mostly MIT with file-specific exceptions, so examine the selected driver build rather than labeling every Mesa component identically. Android userspace, Linux kernel, firmware and SDK/GMS artifacts also have distinct terms. KernelSU's root repository is GPLv3 while `kernel/LICENSE` is GPLv2; audit manager/userspace and kernel components separately. See [Mesa licensing](https://docs.mesa3d.org/license.html), [Gfxstream license](https://github.com/google/gfxstream/blob/94240f814c0097a63027ae680ea4bec7b0cb25f7/LICENSE), [QEMU LICENSE](https://gitlab.com/qemu-project/qemu/-/blob/v11.1.3/LICENSE) and the pinned sources in GUEST.md. No binaries/images or licenses were published or redistributed in this mission.

## Security and operational risks

The graphics decoder consumes guest-controlled buffers inside a host process and interacts with a privileged vendor GPU driver. Treat hostile apps and guests as inputs for malformed-command, allocation, handle and lifetime testing. Bound batch counts/lengths, use explicit wire types, avoid guest pointer trust, validate resource ownership, and plan fuzzing and sanitizer runs before exposing the new device to arbitrary apps. Do not inherit the legacy security claims without evidence.

Keep VM management, serial/QMP and ADB bound to loopback with access control; avoid host filesystem sharing in early experiments. CPU hypervisor availability does not establish GPU isolation. Pin and update the VMM/renderer/kernel/DLL supply chain, and record source/signature/checksum provenance. The current diagnostic guest is an old isolated test asset with networking disabled, not a production guest image.

The cross-build validates locked archive/header hashes from HTTPS repository metadata; independent package/tag signature verification and an SBOM are still required before production distribution. The locally collected DLL set is a working diagnostic closure, not a minimal or audited redistributable runtime. No dependency was installed into Windows or the system compiler tree.

KernelSU remains optional and off in the standard profile. Its documented x86 syscall-dispatcher integration weakens a kernel hardening mitigation; preserve a stock kernel and scoped per-app permissions, rollback and regression tests. Do not disable SELinux or change global host security policy merely to get a passing boot.

## Architecture decisions

- **ADR-000:** preserve `main` and the complete legacy implementation; Phase 0 is additive in its own directory/branch.
- **ADR-001:** evaluate a clean pinned release in an isolated source/build tree; do not graft the old source into it before gates pass.
- **ADR-002:** prioritize standard virtio-gpu/Rutabaga/Gfxstream as a candidate; distinguish a renderer's Windows build from an integrated Windows VM stack.
- **ADR-003:** use a pinned Cuttlefish Android 16 BSP as the guest reference, with a Linux reference boot preceding custom Windows integration; no Android image development during this gate.
- **ADR-004:** keep standard and KernelSU guest profiles separate; root and GPU correctness must be independently qualified.
- **ADR-005:** require executable evidence with honest BLOCKED/FAIL statuses and no hardware-to-software fallback. GPU architecture approval waits for native end-to-end runtime, correctness and security/license closure.

These decisions and the actual evidence are recorded in ThothMemory. The granular path to reopen the gates is in [ROADMAP.md](ROADMAP.md).
