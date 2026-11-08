# Windows standalone edition: engine findings and plan

Written 2026-11-08 from the Linux/WSL edition work and the earlier Phase 0 Windows experiments. Nothing in this file has been run natively on Windows for Android yet.

## What already exists

- Phase 0 cross-built our QEMU 11.1.3 for Windows (MinGW, `windows-cross.lock.json`) and booted a Linux diagnostic guest natively with **WHPX** (`README.md`, `evidence/windows-whpx-boot`). No graphics, no Android.
- Phase 0.7 judged Windows GPU integration through our own Gfxstream/Rutabaga QEMU build **NO-GO** for now (`gpu-readiness/REPORT.md`).
- The owner's machine has hardware Vulkan 1.4 on the RTX 2060 under Windows (none under WSL).
- The web panel (`tools/dlui.py` + HTML) already works from Windows through the WSL edition (`windows/DragonLord.cmd`).

## Why the Cuttlefish engine does not move to Windows as is

The QEMU command line Cuttlefish generates (`.work/cuttlefish/reference-qemu-argv.txt`) depends on Linux-only pieces:

| Piece | Used for | Windows status |
|---|---|---|
| `vhost-vsock-pci` (kernel vhost) | adb, modem simulator, many HALs talk over vsock | not available in QEMU on Windows |
| `vhost-user-input-pci` (switches, rotary, touch) | input devices | vhost-user is Linux-only |
| `memory-backend-file,share=on` | guest RAM, pmem regions (pstore, hwcomposer) | needs a different backend |
| 20 virtio consoles on FIFOs | kernel log, logcat, KeyMint, Gatekeeper, OEM lock, GNSS, sensors, ... | QEMU named pipes exist, but every host service behind them (`secure_env`, `gnss_grpc_proxy`, `modem_simulator`, sensors) is a Linux binary |
| `launch_cvd` / `assemble_cvd` / `run_cvd` | disk assembly, process supervision | Linux binaries |

Porting all of that is a large project (own supervisor plus Windows ports of the Cuttlefish host services, or a vsock replacement in the guest).

## Recommended engine for Edition W: the AOSP Android Emulator (goldfish/ranchu)

Google's Android Emulator is QEMU-based, open source (AOSP `external/qemu`, `hardware/google/gfxstream`), and **runs natively on Windows** with WHPX or AEHD acceleration and Gfxstream on the host GPU (OpenGL ES and Vulkan). It has no Cuttlefish host services: its devices (goldfish pipes, adb over QEMU, telephony modem, sensors) are built into the emulator binary. It also has a headless mode, gRPC control, screen streaming and snapshots.

What would carry over from Edition L: the web panel and instance JSON, the KernelSU LKM approach (the emulator's x86_64 images use the same GKI kernel family; the module must match the image's KMI), per-instance settings (RAM, cores, disk via `-partition-size`, resolution, DPI), APK install and file transfer (adb), and the IMEI question (the emulator's modem is a different code base: needs its own check).

What has to be checked first (milestone W1, needs the owner's Windows machine):
1. Obtain an emulator system image for Android 17 from the same CI branch (`aosp-android-latest-release`; the emulator target name, for example `sdk_phone64_x86_64`, is unverified and must be confirmed on ci.android.com) and a Windows emulator build (from the Android SDK, or built from source).
2. Boot it natively with WHPX and `-gpu host`; measure boot time and run `tools/glbench` (GLES) and a Vulkan sample on the RTX 2060.
3. Headless + screen: `-no-window` with the emulator's gRPC screenshot/streaming or WebRTC, so the existing web panel can show it.
4. KernelSU: patch the image's boot/init_boot like `tools/ksu-patch.sh` (ksud has a Windows build) and confirm the module loads.
5. Licences: the emulator is Apache-2.0/GPLv2 (QEMU part); system images built from AOSP; Google SDK-distributed binaries have their own SDK licence terms, so the shippable route is building the emulator from source.

## Decision for the owner

- **Edition W engine**: AOSP Android Emulator (recommended: native Windows, real GPU incl. Vulkan, no WSL) versus porting the Cuttlefish engine (keeps one engine for both editions but needs a vsock replacement and Windows ports of the host services).
- Until W1 is done, Windows users run Edition L (WSL2) through `windows/DragonLord.cmd` and the web panel.
