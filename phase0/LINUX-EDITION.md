# DragonLord, Linux / WSL edition (for app development)

Android 17 emulator on our QEMU 11.1.3 with KVM, host-GPU or software graphics, optional KernelSU root, managed from a local web panel. Meant for developing and testing apps; not tuned for games (the browser view is a few to 15 frames per second; see Limits).

## Setup (once)

1. Follow `ANDROID17-WSL-RUNBOOK.md` for the one-time root steps (groups, `/usr/lib/cuttlefish-common/bin`), the QEMU build and unpacking the Android image and host package into `.work/cuttlefish/cvd`.
2. `phase0/tools/dl-setup.sh` installs our two wrappers (RAM in `/dev/shm` and user-mode networking for QEMU; guest internet settings for `run_cvd`) and runs the checker.
3. `phase0/tools/dl-doctor.py` at any time: one line per requirement and the fix if something is missing.
4. Optional root profile: `phase0/tools/ksu-patch.sh` (KernelSU). Root instances get the KernelSU manager app installed automatically on their first boot.

## Daily use

- Panel: `python3 phase0/tools/dlui.py` (add `--open` on WSL to open it in the Windows browser; on Windows double-click `phase0/windows/DragonLord.cmd`). The link holds an access token that stays the same across restarts (`~/DragonLord/ui-token`); keep it private.
- In the panel: create instances (name, RAM, CPU cores, drive size, screen, DPI, serial, IMEI, GPU or software, root), Start, Stop, Delete.
- **View** opens the screen in a browser tab: click = tap, drag = swipe, Back/Home/Recents/Power/Volume buttons, text box for typing, quality selector (Fast 50 % / Balanced 75 % / Sharp 100 %), **Install APK**, **Upload file** (to the guest's Download folder), list and download files from Download, drag and drop an APK or file onto the screen.
- **Screen** opens a scrcpy window (Windows build in `.work/scrcpy`); not working yet on this setup (server connection fails), use View.
- Command line: `phase0/tools/dlvm.py create|start|stop|status|delete|logs` does the same as the panel.

## Android Studio / adb

Each instance has an adb address shown in the panel (`127.0.0.1:6520` for the first, `6521` for the second, ...). `adb connect 127.0.0.1:6520` from WSL or from Windows (WSL forwards localhost), and the device appears in Android Studio for Run/Debug, Logcat and the Layout Inspector. Root instances: `adb shell su` through KernelSU after granting shell in the manager; the debug image also allows `adb root`.

## Limits (measured on the WSL test bench)

- All running instances together must fit in `/dev/shm` (6.4 GB here); the panel refuses to start an instance that does not fit.
- First boot of a new drive takes 4-6 minutes, later boots about 1-2 minutes.
- Browser view: about 5 fps at 720x1280, 13 fps at 75 %, 15 fps at 50 % while the screen animates; the guest's software H.264 encoder is the limit. Input latency about 0.1-0.3 s.
- Guest internet works through QEMU user-mode networking (DNS, TCP, UDP); ping (ICMP) does not.
- Graphics in GPU mode use host OpenGL through WSL (no hardware Vulkan in WSL). The Windows edition is planned to use the GPU directly (see `PLAN-INSTANCES-UI.md`).
