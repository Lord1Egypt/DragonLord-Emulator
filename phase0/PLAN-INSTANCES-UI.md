# Instance manager and installer: requirements and design notes

Status: design notes only, nothing built. Windows is the product target; WSL2 is the test bench. Written 2026-11-08 from the user's requests and from what the tests showed.

## User requirements (from the project owner)

- First-run installer, one click: choose VM name, disk size, RAM, CPU count.
- Add instances, several running at once, each with its own settings (like MEmu, LDPlayer, BlueStacks).
- Per-instance options: RAM, CPU cores, root on/off (stock vs KernelSU), graphics mode (host GPU vs software), device identity (IMEI, model, brand, Android ID).
- Android 16 was the original target; the reference image used so far is Android 17 (SDK 37), the owner accepted that.
- GPU acceleration should be fast; a no-GPU mode must also work.

## What each setting maps to (verified unless marked)

| Setting | Mechanism | Evidence |
|---|---|---|
| RAM | `launch_cvd -memory_mb=N`; guest RAM file must be in `/dev/shm` (tmpfs) or RAM-backed storage on Linux. On disk it caused 5x slower boots and ANRs on WSL. Windows needs its own answer (QEMU memory-backend options, not `/dev/shm`). | verified on WSL |
| CPU | `-cpus=N` | verified (4) |
| Disk size | `-blank_data_image_mb=N` **together with `-data_policy=always_create` on the instance's first start** (default `use_existing` ignores it and gives 8 GB); later starts use `use_existing`. | verified: 4096 requested -> 3.9G /data |
| Graphics | `-gpu_mode=gfxstream` + host GL, or `guest_swiftshader` (software). `drm_virgl` does not work with this image. | verified on WSL |
| Root on/off | which `init_boot.img` is passed (`-init_boot_image`): stock or KernelSU-patched (`phase0/tools/ksu-patch.sh`). The base image is userdebug and keeps its own `/system/xbin/su`, so a true "off" needs a user-variant or `su` removed. | verified patched boot, grant/deny, persistence |
| Instance identity | Direct launcher flags exist for `-serial_number`, `-x_res/-y_res`, `-dpi`, `-display0..3`, `-extra_bootconfig_args` (androidboot.* props). **IMEI is hardcoded** (`867400022047199`) in the prebuilt `bin/modem_simulator` (`MiscService::HandleGetIMEI`); `modem_nvram.json` has no IMEI field. A per-instance IMEI needs a patched modem simulator (source is open in AOSP/android-cuttlefish) or a response-rewriting shim. Model/brand/manufacturer properties not yet checked. | flags and strings inspected, nothing booted with custom identity |
| Several instances | `-base_instance_num=N` gives ADB port 6519+N and a separate vsock CID; per-instance HOME and RAM file. **Verified: two instances ran simultaneously** (alpha #1 on 127.0.0.1:6520, beta #2 on :6521, distinct serials, 2 GB and 2 CPUs each, software graphics). Instance #2 had no TAP devices because the QEMU wrapper (`DL_NET=user`) rewrites Cuttlefish's `-netdev tap,...` into QEMU user-mode networking, so no root setup is needed. | verified, 2 instances |
| Shutdown | graceful only: `adb shell sync` then `stop_cvd` (it sends SIGKILL), then wait for all instance processes to exit and remove the RAM file; an unsynced stop lost a KernelSU grant | verified |

## Proposed architecture

1. **Engine**: our QEMU 11.1.3 (Rutabaga + Gfxstream) driven by Cuttlefish `run_cvd` host services, as proven in `ANDROID17-WSL-RUNBOOK.md`. The Cuttlefish launcher is Linux-only: for Windows the QEMU command line (captured in `.work/cuttlefish/reference-qemu-argv.txt`) and the host services (keymint/gatekeeper fifos, logcat, vsock proxy) have to be provided by our own supervisor. This is the largest unknown for the Windows port.
2. **Instance store**: one JSON file per instance (name, id, ram, cpus, disk, gpu_mode, root_profile, identity, ports), plus one directory per instance holding overlays and logs.
3. **Supervisor**: start (allocate ports/TAP/RAM file), health check (`VIRTUAL_DEVICE_BOOT_COMPLETED`, ADB), graceful stop, crash capture through the existing `dlrun.py` scanner.
4. **UI**: first-run wizard, then an instance list with Create / Start / Stop / Clone / Delete and a settings page per instance. Technology not chosen (candidates: native Windows toolkit or a small web UI served locally).

## Open questions and risks

- Windows host graphics: Gfxstream on Windows needs a working host GL/Vulkan path (the earlier Phase 0 notes found a hardware Vulkan path on the owner's RTX 2060 only through the standalone compositor test; guest-visible integration was NO-GO then). Needs a fresh native-Windows experiment.
- Licensing: QEMU is GPLv2; Gfxstream/Rutabaga are Apache-2.0; Cuttlefish host tools and the Android image have their own terms. Redistribution plan unreviewed (Phase 0 ticket P0-08 still open).
- Using Google's prebuilt Rutabaga/Gfxstream libraries with a locally patched header is a dev shortcut, not a shippable setup.
- Android 16 vs 17: choose one for release and pin the build ID and security patch level.
- Identity spoofing (IMEI etc.) feasibility and acceptable scope are undecided.

## Prototype status (`phase0/tools/dlvm.py`, 2026-11-08, WSL2)

Working: `create / start / stop / status / list / delete / logs` with one JSON per instance under `~/DragonLord/instances/<name>/` (own HOME, own Cuttlefish files, own logs, own RAM file `/dev/shm/dl-<name>.mem` via the QEMU wrapper's `DL_MEM_PATH`).
Verified in the guest: custom serial (`DL-TEST-0001`), DPI 280 and 240, 720x1280, 2 CPUs, RAM (3072 MB requested, 2953 MB visible), data disk size (4096 requested, 3.9G), GPU mode (RTX 2060 renderer vs SwiftShader), KernelSU profile (`kernelsu` module loaded), data and settings persist across a graceful stop/start (marker file, serial), second boot 70 s, first boot of a fresh disk 240-330 s.
Also verified: two instances in GPU (gfxstream) mode at the same time, both on the RTX 2060; native GLES benchmark (32-iteration shader, 60 frames) alone 4.1 and 2.9 ms/frame, both at once 4.7 and 7.1 ms/frame, identical image checksums (9948). Boot of the two instances 240 s and 358 s from fresh disks.
Not done: guest internet (with user-mode networking both NICs link up and eth1 gets an IPv6 address, but Android never starts DHCP on eth1: `dumpsys ethernet` says `IpClient is null`, no default network, disabling mobile data did not help; it never worked with TAPs either, needs Android-side investigation, e.g. the Cuttlefish Wi-Fi/openwrt path), two instances with the GPU mode at once, IMEI/model/brand, Windows supervisor, any UI, root-off base image without the debug `su`, input validation beyond basic limits.

## Windows host facts (read-only inspection from WSL via powershell.exe, 2026-11-08)

- Windows 11 Pro build 26300, 12 logical cores, 15.9 GB RAM, 90 GB free on C:. WSL2 uses 13 GB of that RAM, so a Windows-native VM test needs WSL stopped or limited (`.wslconfig`).
- `HypervisorPresent: True` and `WinHvPlatform.dll` exists, so QEMU's WHPX accelerator is available (the earlier Phase 0 work booted QEMU 11.1.3 under WHPX natively). WHPX feature state itself needs elevation to query.
- GPUs: NVIDIA GeForce RTX 2060 (driver 32.0.16.2114, Vulkan 1.4.357 driver 621.14, discrete) and Intel UHD Graphics 630 (Vulkan 1.1.95). **Hardware Vulkan exists on native Windows**, unlike WSL (llvmpipe only), so Gfxstream Vulkan and Vulkan composition can be tested on the real GPU there.
- Present: `git`, `vulkaninfo`, `python` (WindowsApps stub, may not be a real install). Absent: `cargo`, `qemu-system-x86_64`.
- KernelSU release v3.3.1 includes `ksud-x86_64-pc-windows-gnu.exe`, so the root-profile patching step can run on Windows. The Cuttlefish host tools (`launch_cvd`, `run_cvd`, `secure_env`, ...) are Linux ELF binaries: Windows needs either WSL2 as a hidden helper layer or a native supervisor reimplementing them (see Engine above).
- Decision point for the owner: **WSL2-hosted engine with a Windows UI** (fast to ship: our proven stack, GL-only GPU) versus **fully native Windows engine** (hardware Vulkan, no WSL dependency, much more work: supervisor, Gfxstream/Rutabaga Windows builds, licence review).
