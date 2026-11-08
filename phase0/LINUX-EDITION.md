# DragonLord, Linux / WSL edition (for app development)

Android 17 emulator on our QEMU 11.1.3 with KVM, host-GPU or software graphics, optional KernelSU root, managed from a local web panel. Meant for developing and testing apps; not tuned for games (see Limits).

## Setup (once)

1. Follow `ANDROID17-WSL-RUNBOOK.md` for the one-time root steps (groups, `/usr/lib/cuttlefish-common/bin`), the QEMU build and unpacking the Android image and host package into `.work/cuttlefish/cvd`.
2. `phase0/tools/dl-setup.sh` installs our two wrappers (RAM in `/dev/shm` and user-mode networking for QEMU; guest internet settings for `run_cvd`) and runs the checker.
3. `phase0/tools/dl-doctor.py` at any time: one line per requirement and the fix if something is missing.
4. Optional root profile: `phase0/tools/ksu-patch.sh` (KernelSU). Root instances get the KernelSU manager app installed automatically on their first boot.

## Daily use

- Panel: `python3 phase0/tools/dlui.py` (add `--open` on WSL to open it in the Windows browser; on Windows double-click `phase0/windows/DragonLord.cmd`). The link holds an access token that stays the same across restarts (`~/DragonLord/ui-token`); keep it private.
- In the panel: create instances (name, RAM, CPU cores, drive size, screen, DPI, serial, IMEI, GPU or software, root), Start, Stop, Delete.
- **View** opens the screen in a browser tab. Default source **Direct**: QEMU's own framebuffer over VNC, tunnelled through the panel (token, Host and Origin checked), full resolution, about 19 frames per second while the screen animates; click the screen and type, keys go to Android as a real keyboard. Fallback sources **Video 50/75/100 %** (H.264 from the guest's screen recorder, 5-15 fps). Click = tap and drag = live touch on a real virtio touchscreen (instances started with the current tools; older ones fall back to adb taps), Back/Home/Recents/Power/Volume buttons, **Install APK**, **Upload file** (to the guest's Download folder), list and download files from Download, drag and drop an APK or file onto the screen.
- scrcpy (Windows build in `.work/scrcpy`) was tried as a separate screen window; it fails with "Server connection failed" here, so its button is hidden (`/api/screen` remains for a later retry).
- Command line: `phase0/tools/dlvm.py create|start|stop|status|delete|logs` does the same as the panel.

## Android Studio / adb

Each instance has an adb address shown in the panel (`127.0.0.1:6520` for the first, `6521` for the second, ...). `adb connect 127.0.0.1:6520` from WSL or from Windows (WSL forwards localhost), and the device appears in Android Studio for Run/Debug, Logcat and the Layout Inspector. Root instances: `adb shell su` through KernelSU after granting shell in the manager; the debug image also allows `adb root`.

## Limits (measured on the WSL test bench)

- All running instances together must fit in `/dev/shm` (6.4 GB here); the panel refuses to start an instance that does not fit.
- First boot of a new drive takes 4-8 minutes, later boots about 1-2 minutes.
- Each instance's data disk is `~/DragonLord/instances/<name>/data/userdata.img` (sparse, grows up to the chosen size); deleting the instance deletes it.
- Browser view: Direct (VNC) about 19 fps at full 720x1280 while animating (Python proxy, raw pixels over localhost); Video mode 5 fps at 100 %, 13 fps at 75 %, 15 fps at 50 % (guest software encoder). Touch: Cuttlefish's touchscreen daemon (`cf_vhost_user_input`), which Cuttlefish starts but never attaches in QEMU mode, is run by `dlvm` and attached by the QEMU wrapper; a 17-step swipe is delivered in about 40 ms. (A QEMU virtual tablet does not work: Android gets mouse buttons, not touches.)
- Guest internet works through QEMU user-mode networking (DNS, TCP, UDP); ping (ICMP) does not.
- Graphics in GPU mode use host OpenGL through WSL (no hardware Vulkan in WSL). The Windows edition is planned to use the GPU directly (see `PLAN-INSTANCES-UI.md`).
