# Android 16 guest baseline and optional KernelSU

**Status: candidate identified; Android 16 boot and KernelSU functionality BLOCKED.** No Android image was developed or built in Phase 0. A Linux diagnostic boot must not be promoted to this gate.

## Candidate guest

Use an AOSP Cuttlefish **64-bit-only x86_64 phone** product as the primary open-source BSP reference. The examined release is `android-16.0.0_r4` (Android 16 QPR2), manifest commit `15128c9e27cfa599c48d294babd39286ee8f1426`; its Cuttlefish repository commit is `4d368849922b04124e66b1aad48f93b3209f3c8d`. `vsoc_x86_64_only/phone/aosp_cf.mk` identifies `aosp_cf_x86_64_only_phone`. This pins research sources, not a qualified guest binary. There is no selected artifact build ID, resolved full `repo manifest -r`, kernel artifact hash or successful guest boot yet.

The pinned phone path uses the shared **6.12 kernel series** by default, while other products in the same tree choose different kernels. Resolve the actual kernel and virtual-device modules from the exact product build, not merely from the Android version. Android and kernel release numbers are not interchangeable. The release tag is an identifiable reference, not a statement that its security patch level is current enough for production in November 2026. Select and record a maintained patch set before shipping.

Cuttlefish is documented as a Linux host platform. A Cuttlefish image is not a generic Android-x86 PC installer. Its partition/bootloader/AVB configuration, vendor ramdisks, device layout, property injection and host services need to match the VM. A raw GSI supplies system userspace but does not supply the complete vendor BSP, drivers or kernel needed to boot it on QEMU/WHPX. SDK API 36 x86_64 images are a useful Android Emulator reference/control, but they target that downstream emulator's virtual board and have separate image/SDK terms; they are not evidence of upstream QEMU compatibility.

## Concrete graphics integration requirements

The pinned `shared/graphics/device_vendor.mk` includes:

| Layer | Examined reference | Validation required |
|---|---|---|
| EGL/GLES guest driver | `libEGL_emulation`, `libGLESv1_CM_emulation`, `libGLESv2_emulation`, encoders and codec libraries | Correct matching Gfxstream protocol/version, loader properties and transport. |
| Vulkan guest driver | `com.google.cf.vulkan` when Vulkan support is selected | ICD loading, negotiated features, working submissions and readback/presentation. |
| Composition | `com.android.hardware.graphics.composer.drm_hwcomposer` and `.ranchu` package choices | Select the matching implementation and VINTF service; validate fences, vsync, resize and display discovery. |
| Buffer allocation/mapping | `com.google.cf.gralloc`, minigbm allocator service, `mapper.minigbm` | Matching buffer handles/formats/usage flags and import/export semantics across the selected transport. |
| Device assumptions | `/dev/dri/card0`, a pmem-backed composer property and graphics init service | Reproduce or deliberately replace the reference device map; do not copy properties onto a different board blindly. |

Select one coherent graphics stack from the BSP. Installing all these components or setting a renderer property does not make them interoperable automatically. SurfaceFlinger, allocator, mapper, HWC, EGL and Vulkan must agree on buffer ownership and synchronization. The reference even marks some DRM present fences unreliable; frame pacing must be measured independently.

## Kernel and virtual-board checklist

Start from the reference kernel configuration and exact module set. Required facilities include x86_64/SMP and the intended page size (ordinary x86_64 4 KiB first); PCI/MSI/virtio PCI; the chosen virtio GPU with context, capset, blob and host-visible mappings; DRM/KMS; DMA-BUF and sync-file/fence support; Android Binder/BinderFS; SELinux and security hooks; cgroups/namespaces; virtio storage/console/input/rng/network; and the relevant filesystems, device mapper and AVB/dm-verity path. VSock, pmem, virtio-dma-buf and vendor services must be either reproduced or accounted for in a host-service replacement design.

Many drivers are modules, not built-ins. The reference BoardConfig enumerates GPU/input/network/dma-buf and first-stage storage/PCI/console/vsock modules. Ensure their vermagic, KMI, module signatures, load order and vendor/system DLKM partitions match the boot kernel. Avoid listing symbols as enabled without checking the built `.config` and loaded modules. A kernel command line alone cannot repair a missing vendor HAL or an incompatible device layout.

Before any guest development is authorized by the foundation gate, first select an existing reference artifact with matching host tools and run it on Linux/KVM. Preserve boot, vendor_boot, init_boot, vbmeta, partition metadata and hashes. This is the oracle for later Windows VM integration. If no complete releasable artifact exists for the selected source tag, mark artifact qualification BLOCKED rather than downloading an unrelated nightly and calling it the same baseline.

## Android boot definition of done

- Record full fingerprint, SDK 36, Android release 16, `uname -m = x86_64`, kernel version/config, artifact hashes, product and fully resolved source manifest.
- Observe `sys.boot_completed=1`, working ADB, responsive launcher, stable SurfaceFlinger, correct allocator/composer services and SELinux enforcing for the non-root baseline.
- Exercise storage persistence across reboot, input, display resize, audio and network in separate scoped tests; qualify each feature rather than assuming a successful logo implies a usable emulator.
- Prove EGL/GLES and Vulkan operation with correctness workloads and capture driver/device identity and host execution traces. Check that no software fallback was silently used.
- Repeat cold boots and stability tests defined in BENCHMARKS.md. This gate is currently BLOCKED.

## Optional KernelSU profile

Keep the standard guest kernel/root state as the default. KernelSU is a separate opt-in test image/profile with its own kernel and manager hashes and an easy return to the stock boot artifacts. Root stays inside the guest; do not add host filesystem access or expose debugging endpoints to the network.

Current upstream KernelSU documents x86_64 support, but modern syscall hardening requires either its `KSU_X86_PATCH_SYSCALL_DISPATCHER` mechanism or the matching kernel source patches, not both. The documented mechanism weakens a syscall hardening mitigation. Its effect and threat model must be accepted explicitly for this optional profile, rather than silently changing the normal kernel.

The examined `kernel/Kconfig` depends on KPROBES and EXT4. A working integration must also match the selected kernel's symbol/KMI/module/signature policy and SELinux behavior. Upstream architecture support is not proof that an unmodified prebuilt GKI or LKM works with this Cuttlefish kernel. No KernelSU build or load was performed here.

Definition of done: boot the exact modified kernel on both qualified hosts; verify manager/kernel agreement and explicit grant/deny behavior for test applications; confirm guest UID escalation only when allowed; retain SELinux expectations; test denied apps, reboot, module load/unload if using LKM, rollback to stock, graphics regression and stability. Merely running `su` or using `adb root` is not a KernelSU test. Record the root repository's GPLv3 terms separately from the kernel subdirectory's GPLv2 license.

## Primary sources

- [AOSP Android release tags/API levels](https://source.android.com/docs/setup/reference/build-numbers), [Cuttlefish host scope](https://source.android.com/docs/devices/cuttlefish).
- [Pinned product](https://android.googlesource.com/device/google/cuttlefish/+/4d368849922b04124e66b1aad48f93b3209f3c8d/vsoc_x86_64_only/phone/aosp_cf.mk), [BoardConfig](https://android.googlesource.com/device/google/cuttlefish/+/4d368849922b04124e66b1aad48f93b3209f3c8d/shared/BoardConfig.mk), [graphics packages](https://android.googlesource.com/device/google/cuttlefish/+/4d368849922b04124e66b1aad48f93b3209f3c8d/shared/graphics/device_vendor.mk).
- [Android common kernel/KMI overview](https://source.android.com/docs/core/architecture/kernel/android-common), [SurfaceFlinger composition](https://source.android.com/docs/core/graphics/surfaceflinger-windowmanager).
- [Android 16 Emulator setup](https://developer.android.com/about/versions/16/get), [GSI releases and limitations](https://developer.android.com/topic/generic-system-image/releases).
- [KernelSU x86_64 requirements](https://kernelsu.org/guide/x86_64-support), [pinned KernelSU configuration](https://github.com/tiann/KernelSU/blob/28db74f6f4692e97006ce9ebd8b19b9cc614b5b7/kernel/Kconfig), [kernel license](https://github.com/tiann/KernelSU/blob/28db74f6f4692e97006ce9ebd8b19b9cc614b5b7/kernel/LICENSE).
