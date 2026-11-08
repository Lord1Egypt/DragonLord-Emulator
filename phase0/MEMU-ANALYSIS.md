# MEmu 9.5.6.1: how it is built and what DragonLord can learn

Date: 2026-11-08. Method: read-only inspection of the owner's own MEmu install (file layout, sizes, the public headers of its disks, its per-VM configuration files, its logs and its UI language file). MEmu was **not run** by us and none of its code or assets was copied or decompiled; this report records observations and design ideas only. Personal data found in its configuration (IMEI, SIM, location) is deliberately not recorded here.

## 1. Architecture (observed)

| Layer | What MEmu does | Evidence |
|---|---|---|
| Programs | `MEmu.exe` (one instance window, Qt5), `MEmuConsole.exe` (the Multi-MEmu manager), `MemuService.exe` (background service, 3 MB RAM idle), `MEmuHeadless.exe` (the VM process, no window of its own), `MEmuRepair.exe`, `MEmuPush.exe`, bundled `adb.exe`, `aapt.exe`, `7za.exe`, `screenrecord.exe`, ffmpeg DLLs | install folder listing, process list |
| VM engine | A fork of **VirtualBox 6.1.40** ("MemuHyperv VM 6.1.40"): same code layout renamed (`MEmuSVC`, `MEmuDD`, `MEmuRT`, `MEmuC`, ring-0 driver `HPVR0.r0`, machine files `*.memu` in VirtualBox's XML shape). It is a full device model, not a thin wrapper | log header, DLL names, `.memu` XML |
| Hypervisor | Its own VT-x/AMD-V driver, **or, when Windows Hyper-V is active (as on this PC), a fallback to the Windows hypervisor interface**: "HMR3Init: Attempting fall back to NEM: VT-x is not available". NEM is the same Windows Hypervisor Platform API that Google's emulator and our edition use. A second backend exists: a Windows **Host Compute Service** (HCS, the API under WSL2 and Windows Sandbox) VM described by `hyperv.json`, with UEFI boot | log lines, `hyperv.json` |
| Disks | Files named `.vmdk` are really **VHD** (Microsoft format; they start with the `conectix` footer). Layered: a **shared, read-only system disk** per Android version (2.4 GB, `image\120\...disk1`), a **small per-instance data disk** (63 MB as a template, 5.2 to 5.6 GB in use, dynamic), and a 4 MB boot disk. A new instance is therefore a copy of a tiny template. Options in the UI: "Shared system disk" (less space) versus "Independent system disk" (writable) | headers, sizes, `hyperv.json`, UI strings |
| Disk caching | UI choice between "High-Performance: cache data in RAM (may corrupt on power failure)" and "Stability: no cache"; disks attached with `CachingMode: Cached` | UI strings, `hyperv.json` |
| Guest devices | virtio network (two port forwards per instance: adb and an internal "MVD" channel), USB tablet pointer, null audio at the VM level, and **custom pipe devices**: `MEmuPipeCommand`, `MEmuPipeVInput` (input injection), `MEmuPipeIme` (keyboard text), `MEmuPipeAudio`, `MEmuPipeDevice`, `MEmuPipeAS`, `MEmuPipeMemud` (a guest daemon `memud`). The host controls the guest through these pipes, not only through adb | `.memu` ExtraData, log |
| Graphics | Goldfish-style host-side OpenGL ES: `libOpenglRender2.dll` plus `libGLES_V2/CM_translator.dll` and a shader translator (the lineage of Google's classic emulator renderer), with a render-mode setting (`graphics_render_mode = 3`; the UI offers "Switch to DirectX and restart"), vsync, a "GPU memory optimization" switch and a frame-rate display/limit option. Only 12 MB of emulated VRAM | DLL names, guest properties, UI strings |
| Guest | Android-x86-class images: `image\96` (Android 9) and `image\120` (Android 12), a custom lightweight build, with VirtualBox Guest Additions 5.1.34 | folders, log |
| Instances | Default instance here: 6 GB RAM, 6 CPUs, 12 MB VRAM, 1280x720 at 240 dpi; `MEmu_1` and `MEmu_2` are clones of the same layout (5 to 6 GB each, 12 GB total) | `.memu`, guest properties |
| Speed | From the last log: VM created in 3 s, powering on at 3.2 s, the guest kernel reports in at **8.4 s**. Android's home screen is expected within roughly half a minute (not measured by us). Compare DragonLord Windows: 14 s with a quick-boot snapshot, about 160 s cold | log timeline |

## 2. Device identity and per-instance settings (observed as guest properties)

MEmu sets these as simple key-value properties the guest reads at boot: brand, manufacturer, model, board, hardware, baseband string; IMEI, IMSI, SIM serial, phone number; operator name, MCC/MNC, country; Wi-Fi SSID and BSSID, cell id and LAC; latitude and longitude; screen width, height and DPI; graphics mode; vsync; root switch (`enable_su`); GPU memory option; language; keyboard mode. The default model it presents is a recent Samsung flagship. This is the whole "device spoofing" feature set, and none of it needs a special engine, only a guest that reads the properties.

## 3. Feature inventory (from the manager's UI strings)

**Multi-instance manager:** create, clone, import and export (`.ova`, `.memu`), batch import, rename, sort and arrange windows, start several with a configurable **delay between launches**, apply a setting to all, language per manager, close-all prompts while tasks run, license/key handling (commercial).
**Operation synchronizer:** mirror one instance's clicks and keys to all others (start, stop, pause, resume), the standard tool for game farms.
**Key mapping:** per-game keyboard and mouse layouts (move keys, aim, skills, "auto sprint", auto-walk distance), switchable configs, F1 to toggle, import and export, "smart key mapping" that needs a minimum resolution, high-FPS mode for certain MOBA games.
**Macros and scripts:** operation recorder, macro editor, script list, run on launch, import and export, pause or stop playback.
**Per instance:** CPU cores and RAM (minimum 512 MB, recommends 1 GB host free), resolution and DPI, root mode, network NAT or bridged (installs a bridge driver), virtual ISP info and phone number, fake GPS with a map, microphone/speaker choice, rotate, fullscreen, boss key, shake/volume style controls, screenshot, screen recording with start/stop hotkeys, shared folders (music, movie, picture, download), APK and XAPK install (drag and drop, "Download and install"), export APK to PC, auto-clear old APK files, reboot Android.
**Disk management:** auto-expand versus manual capacity, compact and defragment, space warnings, an "out of space, VM suspended" safety stop.
**Maintenance:** repair tool for drivers and permissions, detection and handling of Hyper-V, FAT32, non-ASCII install paths and low host memory.

## 4. What this means for DragonLord

Findings that match what the owner saw ("heavy, slow, laggy"):

1. **The speed comes from a small, purpose-built guest and a slim device model**, not from a different hypervisor: on this PC both MEmu and our emulator sit on the same Windows hypervisor API. MEmu boots a trimmed Android-x86 image (no Google services starting at boot, 2.4 GB system disk) and virtualises little (12 MB VRAM, virtio network, pipes instead of many emulated devices). Our Windows edition boots a full Android 16 Google Play image with a complete phone device model (modem, sensors, camera, many services) and Gfxstream's Vulkan path.
2. **Layered VHD disks** make creating and cloning instances almost free and keep disk use low; ours writes a full 8 GB data disk per instance.
3. **Default sizing**: ours is 3 GB and 4 cores, MEmu 6 GB and 6 cores, so the load difference is not the default size but the image and services.

## 5. Adoption plan (ordered by value for effort)

**A. No engine change needed (Windows and Linux, days):**
- Fewer features at boot: for Windows, create AVDs without camera, audio input, sensors and extra services; start with `-no-audio -no-snapshot-save` options where useful; default RAM 2 GB and 2 cores with a "performance profile" choice (Light / Balanced / Power).
- One window: embed the controls in the emulator window (a thin native toolbar app) and drop the console and the browser tab on Windows.
- Silent start with a progress bar (already requested).
- Instance features copied by idea: clone instance, batch start with delay, rename, export and import, shared folders, rotate, screenshot, screen recording, APK and XAPK drop, fake GPS and device identity profiles (brand, model, operator, phone number), per-instance render mode and FPS cap, hotkeys including a boss key.
- Keyboard and mouse key-mapping for games and the operation synchronizer for multiple instances (large, but pure host-side work: inject the same input into every instance).

**B. Medium (weeks): a lighter guest.** Test a slim Android-x86/Bliss-class image, or AOSP without GApps as a base with Google Play as an optional layer (our GApps option already works this way on Linux), on the Google emulator. Goal: boot to home in under 30 s cold, under 10 s from a snapshot, and half the idle RAM.

**C. Large (months, decide later): a custom engine like MEmu's**: a stripped VirtualBox-style or QEMU device model on the Windows hypervisor with a shared read-only system VHD, per-instance differencing VHDs, host-side GLES translator and control pipes. Highest payoff and highest cost; QEMU 11 with a shared base image and per-instance qcow2 overlays is the closest open path (our Linux edition already uses overlays), but its Windows GPU path was judged NO-GO in Phase 0.

**D. Licence note:** MEmu's engine is a VirtualBox fork (GPLv2 / CDDL parts) and its renderer descends from Google's emulator (Apache-2.0); those upstreams are the legitimate sources to build on. Nothing proprietary from MEmu should be copied.

## 6. What this study did not cover

MEmu was not started, so live CPU and RAM numbers, frame rates and the exact Android boot time are unmeasured. BlueStacks, LDPlayer and NoxPlayer are not analysed here: next step is the same read-only study for them, only if they are installed on this PC, otherwise from their public documentation.
