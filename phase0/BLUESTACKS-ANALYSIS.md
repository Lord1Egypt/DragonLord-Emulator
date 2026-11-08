# BlueStacks (nxt): how it is built and what it does at runtime

Date: 2026-11-09. Method: read-only look at the owner's own install (`C:\Program Files\BlueStacks_nxt`, `C:\ProgramData\BlueStacks_nxt`): file names and sizes, disk headers, and the settings file `bluestacks.conf` (identifiers, accounts and tokens were skipped and are not recorded). BlueStacks was not run by us; nothing was copied or decompiled.

## Architecture (observed)

| Layer | Finding |
|---|---|
| Engine | The same family as MEmu: a **VirtualBox fork** with renamed parts (`BstkSVC.exe`, `BstkVMMgr.exe`, `BstkVMM.dll`, `BstkDD.dll`, `BstkRT.dll`, a kernel driver `BstkDrv_nxt.sys`, ring-0 modules `*.r0`). Helper programs with the `HD-` prefix: `HD-Player.exe` (the window), `HD-MultiInstanceManager.exe`, `HD-Adb.exe`, `HD-Aapt.exe`, `HD-EnableHyperV.exe`, `HD-DiskCompaction.exe`, `HD-GLCheck.exe`, `HD-ForceGPU.exe` (picks the discrete GPU), `HD-CheckCpu.exe`, `HD-VNC.exe` |
| Android | `Rvc64` = Android 11 (R), 64-bit, with an ABI list `x86,x64,arm,arm64` (ARM apps run through a translation layer) |
| Disks | Layered like MEmu: a **shared read-only system disk** `Root.vhd` (2.2 GB), a **per-instance dynamic data disk** `Data.vhdx` (3.7 GB in use) with an **80 MB template** `Data_orig.vhdx` (a new or reset instance starts from it), and an 11 MB boot disk `fastboot.vdi`. Engine folder 5.6 GB total |
| Boot time | Its own setting records `boot_duration = 14278` ms (14.3 s) for the last start, from a ready snapshot-style boot |
| Defaults | 4 CPUs, 4 GB RAM, 240 dpi, 60 fps cap, vsync off, root off |
| Memory and GPU knobs | `enable_mem_dedup = 1` (merge identical memory pages across the VM), `libc_mem_allocator = jem` (jemalloc inside Android), `astc_decoding_mode = software` (texture decoding on the CPU), `graphics_renderer` and `graphics_engine` selectable, Vulkan flag, **eco mode with a maximum of 5 fps** when the window is not in use, a high-FPS option, an FPS overlay, separate `max_fps` |
| Services around the VM | A lot: cloud instances, an AI assistant and "AI highlights", clip recording and auto-upload, Discord integration, a rewards currency, programmatic ads inside Android (ad app package, display times, screen-share limits), usage and boot statistics, remote adb option, quick-launch and sign-in prompts. These run on top of the emulator and are a large part of why it feels heavy |

## What to take from it for DragonLord

1. **Same disk idea as MEmu** (shared read-only base + small per-instance data disk + tiny boot disk): confirms the plan. With Google's emulator we have a per-instance copy of the data partition (3.3 GB); a base-plus-overlay layout would make cloning and new instances near-instant (the emulator already supports copy-on-write system overlays internally).
2. **Eco mode** is cheap and effective: drop to 5 fps (or pause the VM) when the window is not focused. The Google emulator has a console command to pause and resume the VM (`adb emu avd stop` / `avd start`); an "Eco: pause idle instances" setting is planned.
3. **Memory deduplication and a lighter allocator** inside the guest help idle RAM; the emulator's `-memory`/ballooning options and a trimmed guest are the equivalent for us.
4. **No telemetry, no ads, no cloud, no AI add-ons**: our idle load can be far lower by construction (Light image measured at 17 % of one core and 1.1 GB; see `WINDOWS-OPTIMIZATION.md`).
5. The **14 s boot** is the target for cold starts; our snapshot start is 16 s, our cold boot 103 s (a first-start-only cost; a trimmed guest and a pre-warmed snapshot shipped with the image would remove it).

## Not measured

Live CPU, RAM and frame rate of BlueStacks were not measured (not started by us). A fair comparison needs a run of the same game on both with the same RAM and cores, which the owner should approve first.
