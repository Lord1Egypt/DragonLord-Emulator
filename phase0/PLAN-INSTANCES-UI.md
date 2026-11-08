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
| Several instances | `-instance_nums`, per-instance dirs, ports (ADB 6520+n), vsock CID, TAP names (`cvd-mtap-01`, `cvd-etap-01`, ...), guest RAM file name | untested, TAPs need root |
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
Not done: a second instance running at the same time (needs TAP devices `cvd-mtap-02`/`cvd-etap-02` created with root), IMEI/model/brand, Windows supervisor, any UI, root-off base image without the debug `su`, input validation beyond basic limits.
