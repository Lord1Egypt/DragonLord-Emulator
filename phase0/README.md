# Phase 0: architecture validation and feasibility gate

**Verdict: NO-GO for adopting a Windows accelerated graphics foundation or starting full migration yet.** Clean QEMU builds, a Linux TCG diagnostic boot and a native Windows WHPX diagnostic boot passed. GPU rendering, Android 16 boot and KernelSU are **BLOCKED**. Narrow validation experiments can continue; the proposed graphics foundation has not passed its gates.

All work is on `phase0/architecture-feasibility`, based on `c5447ed4baf97d93e3a87c62534ed7d300d288de`. The original tree and `main` are preserved. No legacy engine files were edited and no release was published.

Read:

- [Feasibility report and gate results](REPORT.md)
- [GPU backend comparison and recommended candidate](GPU-BACKENDS.md)
- [Android 16 guest and optional KernelSU integration](GUEST.md)
- [Performance and stability acceptance protocol](BENCHMARKS.md)
- [Tickets, dependencies and definitions of done](ROADMAP.md)
- [Pinned versions and diagnostic asset hashes](versions.lock.json)
- [Captured evidence](evidence/index.json)

## Smallest reproducible experiment

This builds pristine QEMU 11.1.3 and boots the checksummed Linux assets used by its upstream functional test. It builds no Android image and enables no 3D backend. The guest's original disk is protected by a temporary snapshot. QMP and serial bind to loopback; guest networking is disabled.

The successful Linux run used Ubuntu 24.04, GCC 13.3, Python 3.13, Meson 1.11.1, Ninja 1.13.0, GLib 2.80 and Pixman 0.42.2. Isolated dependencies live in `.work`; the optional bootstrap installs no system packages. It needs existing GCC, Make, pkg-config, Python/venv, apt-get and dpkg-deb. These package versions are pinned, but future archive availability and full binary bit-for-bit reproducibility are not guaranteed. The QEMU build fetches the subprojects pinned in its own wrap files.

Run from the repository root:

```sh
python3 phase0/tools/bootstrap-linux.py
python3 phase0/tools/build-qemu.py --host linux --jobs 6
phase0/.work/build-venv/bin/python phase0/tools/experiment.py fetch-assets
phase0/.work/build-venv/bin/python phase0/tools/experiment.py boot \
  --qemu phase0/.work/qemu-build-linux/qemu-system-x86_64 \
  --bios-dir phase0/.work/qemu-11.1.3/pc-bios \
  --accel tcg --output phase0/results/tcg
python3 phase0/tools/audit-legacy.py --output phase0/results/legacy-api
python3 -m unittest discover -s phase0/tests -v
```

On a Linux host with usable `/dev/kvm`, repeat the boot command with `--accel kvm`. It never falls back to TCG. In this session that gate returns `BLOCKED` with exit code 2. An executed failure returns 1; a diagnostic pass returns 0. Asset checksum mismatches abort rather than becoming boot evidence.

## Native Windows experiment

The isolated Ubuntu-to-Windows cross-build passed, and its executable ran natively on Windows and enumerated WHPX. This is a CPU diagnostic profile without graphics libraries. A native MSYS2 build is an alternative, not a result claimed by this mission. Do not interpret a successful build or enumerated WHPX DLL as proof of a WHPX guest boot.

The subsequent [native WHPX boot](evidence/windows-whpx-boot/result.json) **passed** with guest command execution, clean QMP shutdown and unchanged disk hash. It used the same Linux 6.4.16 diagnostic assets as the TCG experiment. The QEMU log contains an interrupt-vector warning; correctness beyond this single boot and longer stability remain unqualified. This is not graphics or Android evidence.

The tested cross-build path uses the Linux bootstrap above, then:

```sh
phase0/.work/build-venv/bin/python phase0/tools/build-windows-cross.py --jobs 6
```

[windows-cross.lock.json](windows-cross.lock.json) pins the Ubuntu MinGW toolchain, MSYS2 dependency archives and a current upstream WHPX definitions header. The older packaged header failed compilation; the isolated header overlay fixes those missing definitions without modifying QEMU. Runtime DLLs are collected beside `phase0/.work/qemu-build-cross/qemu-system-x86_64.exe`. The captured native inventory used a separately copied diagnostic directory; its binary hash is recorded independently because rebuilds need not produce identical PE bytes. No compiler, DLL or header was installed into Windows or the system toolchain.

For the untested native alternative, use a native MSYS2 MINGW64 terminal with GCC/binutils, Git, Make, Python/venv, Ninja, pkg-config, GLib, Pixman and current WHPX headers. Confirm `pkg-config --modversion glib-2.0 pixman-1` and that `WinHvPlatform.h`/`WinHvEmulation.h` are available. The build explicitly requests WHPX; unavailable headers/libraries must fail the build. This alternative needs its own package lock before claiming reproducibility.

```sh
# Native MSYS2 MINGW64, from the checkout (use a separate checkout from WSL).
python phase0/tools/build-qemu.py --host windows --jobs 6
```

Then in native Windows PowerShell, with Python and the MinGW runtime DLL directory on PATH, use absolute Windows paths:

```powershell
python -m venv .\phase0\.work\asset-venv
.\phase0\.work\asset-venv\Scripts\python.exe -m pip install zstandard==0.25.0
.\phase0\.work\asset-venv\Scripts\python.exe .\phase0\tools\experiment.py fetch-assets

.\phase0\tools\probe-windows.ps1 `
  -Qemu 'C:\src\DragonLord-Emulator\phase0\.work\qemu-build-windows\qemu-system-x86_64.exe' `
  -OutputDirectory 'C:\src\DragonLord-Emulator\phase0\results\windows-inventory'

python .\phase0\tools\experiment.py boot `
  --qemu 'C:\src\DragonLord-Emulator\phase0\.work\qemu-build-windows\qemu-system-x86_64.exe' `
  --bios-dir 'C:\src\DragonLord-Emulator\phase0\.work\qemu-11.1.3\pc-bios' `
  --accel whpx --output .\phase0\results\whpx
```

Provision the Windows Hypervisor Platform OS feature and firmware virtualization separately on the test machine if needed. The scripts do not change OS features, reboot the host or install drivers. WHPX CPU acceleration and GPU acceleration are separate gates.

When assets have already been fetched and decompressed by the Linux runner, native PowerShell needs no Python for the strict boot test:

```powershell
.\phase0\tools\boot-whpx.ps1 `
  -Qemu 'C:\src\DragonLord-Emulator\phase0\.work\qemu-build-cross\qemu-system-x86_64.exe' `
  -Kernel 'C:\src\DragonLord-Emulator\phase0\.work\assets\bzImage' `
  -Disk 'C:\src\DragonLord-Emulator\phase0\.work\assets\rootfs.ext4' `
  -BiosDirectory 'C:\src\DragonLord-Emulator\phase0\.work\qemu-11.1.3\pc-bios' `
  -OutputDirectory 'C:\src\DragonLord-Emulator\phase0\results\whpx-native'
```

Keep `manifest.json` beside the disk and the lock file beside the scripts as in the checkout. Absolute UNC checkout paths also work for invoking the test; host filesystem access speed can materially affect checksum preflight and must not be counted as guest boot time.

`probe-windows.ps1` captures GPU/driver names, QEMU binary hash and available devices/accelerators. It returns `INVENTORY_COLLECTED`, never GPU PASS. The gate also needs a real rendering workload and trace evidence described in the report.

## Collect an independently provisioned Android guest

No generic upstream-QEMU Android boot command is presented as working. A Cuttlefish BSP and launcher/device mapping must first be qualified. After a guest has been launched by that separately validated path:

```sh
adb devices -l
python3 phase0/tools/collect-android.py --serial ACTUAL_ADB_SERIAL --output phase0/results/android
```

This checks completed Android 16/API 36/x86_64 guest properties and saves diagnostic output. It **always leaves GPU and KernelSU unverified**. Renderer strings, root UID and boot properties alone cannot qualify those gates. Logs may contain guest data; inspect/redact before sharing. The captured no-device run is a negative classification check, not an attempted Android boot.

New runs go under ignored `phase0/results`. Preserve raw logs, exact argv, hashes, driver details and run IDs; do not replace a failed result with a success from a different host or backend.
