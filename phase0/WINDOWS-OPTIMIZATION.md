# Windows edition: performance measurements and decisions (2026-11-09)

Machine: the owner's Windows 11 PC (i7-9750H, RTX 2060, 16 GB; WSL holding most RAM so only about 1 GB was free during the tests, a hard but realistic condition). Engine: Google Android Emulator 37.2.13 on the Windows Hypervisor Platform with the host GPU. One instance at a time, 2 GB RAM, 2 cores, 1280x800, snapshots as the emulator saves them on stop. Script: `bench.ps1` (kept outside the repository with the test folder).

## Image comparison

| | Light: AOSP "default" Android 16 (844 MB download) | Google Play Android 16 (1.9 GB download) |
|---|---|---|
| Cold boot (first start of an instance) | 103 s | 128 s |
| Start from quick-boot snapshot | **16 s** | 25 s |
| Idle RAM of the VM process after snapshot start | **1.1 GB** | 2.3 GB |
| Idle CPU (share of one core, 30 s) | **17 %** | **159 %** (265 % right after a cold boot) |
| Instance folder on disk | 3.3 GB | 4.0 GB |

The Google Play image never goes idle (Play Services, updates, many background services), which is the likely cause of the heavy, laggy feel on a PC with little free memory. The Light image has no Google services, so it idles at one tenth of the CPU and half the RAM. Light is therefore the default from 0.2.0; Google Play stays one choice away in the new-emulator form (downloaded only when chosen).

## Emulator flags tried on the Light image (snapshot start, idle after 60 s)

| Flags | Start | RAM | Idle CPU |
|---|---|---|---|
| none | 45 s (snapshot was stale) | 1118 MB | 22.9 % |
| `-no-audio` | 16 s | 986 MB | 13.5 % |
| `-feature -Vulkan` | 22 s | 1094 MB | 17.9 % |
| both | 13 s | 1063 MB | 15.5 % |

Decision: the Light profile starts with `-no-audio`; Balanced and Power keep audio. Vulkan stays on (games need it, the gain is small). Differences of a few percent are within the noise of this measurement.

## Root and terminal

- **Root without KernelSU:** the AOSP image is a debug-capable build; after boot the app runs `adb root` and the shell is `uid=0`, `su` works. The Google Play image is a locked build, so root is offered only with the Light image (the app refuses root on Google Play with a clear message).
- **Terminal:** a WebSocket to `adb shell -tt` (the pty lives on the device, so plain pipes work on Windows), rendered with xterm.js 5.5.0 (MIT, embedded). Tested: connections without or with a foreign Origin are refused, the page's own origin gets a root prompt and runs commands.

## Bugs found and fixed while measuring

1. Creating a second instance deadlocked the panel (a lock taken twice).
2. "Booted" detection depended on an adb round trip that can hang; it now uses the emulator's own "Boot completed" log line or an adb check limited to 4 s.
3. Starting an instance right after stopping it failed ("same AVD"): stop, start and delete now wait for the emulator process and its lock files (stale locks older than 30 s are removed).

## Clone, rename and what the snapshot depends on (measured, headless emulators)

- Clean cycle on the Light image: cold boot 101-106 s, restart from the quick-boot snapshot **7 s**, adb usable at once; a **clone** (3.3 GB copy, 12 s) starts in **8 s** because its snapshot restores.
- A snapshot is discarded ("different AVD configuration") if `config.ini` differs from what the emulator saved, so the app never regenerates `config.ini` for an existing instance; a clone or rename edits only the name and the instance paths in `config.ini` and in the snapshot's `hardware.ini`. The emulator also raises data disks below 6 GB to 6 GB, so the form's minimum is 6144 MB.
- A clone is built in `NAME.avd.tmp` and moved into place when complete, so a half-copied instance never shows up or can be started.
- **Never force-kill the emulator** (Task Manager, `taskkill /F`): it can leave a half-written snapshot, after which the next start hangs with adb offline. My own test runs did this once and produced exactly that state; after removing those instances and testing again with graceful stops everything worked. Stop and Quit in the panel are graceful.
- Console programs started from the window-less exe (adb every second or two, the emulator launcher) opened a black console window each time; all child processes now start hidden.

## Still to do for the Windows edition

One native window with the controls inside it (instead of the browser panel), clone/rename/import/export, batch start, identity profiles (brand, model, operator, phone number), fake GPS, key mapping, macros, operation synchronizer, screen recording, boss key, a lighter guest than stock AOSP (a trimmed image would cut the 100 s cold boot), and a comparison run against BlueStacks on this PC.
