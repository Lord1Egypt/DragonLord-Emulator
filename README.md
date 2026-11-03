# DragonLord Emulator: High-Performance Mobile Emulation through Graphics Projection

![version](https://img.shields.io/badge/Version-Beta-yellow "Beta") ![license](https://img.shields.io/badge/GuestOS-Androidx86-green "Android") ![license](https://img.shields.io/badge/Licence-GPLv2-blue.svg "GPLv2") ![status](https://github.com/Lord1Egypt/DragonLord-Emulator/actions/workflows/main.yml/badge.svg)

DragonLord Emulator is an Android emulator designed to simultaneously meet the goals of high compatibility, security, and rendering efficiency utilizing graphics projection space.

<p float="left" align="middle">
<img align="top" src="https://user-images.githubusercontent.com/32576375/209423491-b2e816f2-b641-446d-9b7f-3ff8c29db773.gif" width="49%"/>
<img align="top" src="https://user-images.githubusercontent.com/32576375/209423951-efd6b3d4-5785-4e11-9365-09b90b26c76f.gif" width="49%"/>
</p>

---

## 1. Getting Started with DragonLord Emulator

### Hardware Requirements

You should run DragonLord Emulator on a **WinTel** (Windows-x64 on Intel) machine, with an NVIDIA dedicated GPU installed with the latest driver (over version 497.09) if possible (integrated GPU is also acceptable). 

**Minimal hardware configurations:**
- 4-core CPU
- 8 GB memory
- 1920x1080 display
- 128 GB storage

### Software Prerequisites

1. Ensure Intel Virtualization Technology (Intel VT-x / AMD-V) is enabled in BIOS settings.
2. Check whether Windows Hyper-V is enabled ([how to determine Hyper-V state](https://docs.microsoft.com/en-us/troubleshoot/windows-client/application-management/virtualization-apps-not-work-with-hyper-v#determine-whether-the-hyper-v-hypervisor-is-running)).
3. If Hyper-V is not available, install Intel HAXM ([v7.6.5 recommended](https://github.com/intel/haxm/releases/download/v7.6.5/haxm-windows_v7_6_5.zip)). Extract the downloaded archive and run `haxm-7.6.5-setup.exe`.

> **Note:** Hyper-V generally provides better CPU performance over HAXM. DragonLord Emulator detects Hyper-V and automatically selects it when available.

---

## 2. Usage Instructions

### 2.1 Guest OS Running & Installation

- **Live Run without Installation:**
  Allows quickly running and evaluating DragonLord Emulator. Note that virtual storage is volatile and limited to 8 GB.
  Press `Enter` when the boot option is `Run Android-x86 without installation`.

- **Installation:**
  To maintain persistent data and full disk sizing, choose `Install Android-x86 to harddisk` during boot.

### 2.2 Advanced Features & Troubleshooting

- **Applications & Play Store:** The guest OS supports [@OpenGApps](https://github.com/opengapps/opengapps) for installing apps from the Google Play Store (including ARM translation compatibility).
- **ADB Connection:** Connect using standard ADB:
  ```bash
  adb connect 127.0.0.1:5555
  ```
- **Freeze / Force Shutdown:** If the emulator hangs during boot or execution, issue a shutdown request or kill the emulator process safely.
- **Diagnostics:** If DragonLord Emulator fails to start, inspect `log.txt` generated in the root execution directory.

---

## 3. Architecture & Code Organization

DragonLord Emulator is built on top of QEMU 5.0 with specialized decoupled high-performance modules:

| Module | Purpose |
| --- | --- |
| `hw/direct-express` | Implements the high-speed data teleporting pipeline between the guest and host using a lightweight packet protocol for fast bidirectional data transfer. |
| `hw/express-gpu` | Implements the host rendering engine using shadow contexts and resource handles within the graphics projection space to manage host OpenGL contexts and window rendering with flow control. |

---

## 4. Building from Source

DragonLord Emulator uses git submodules for dependencies. Initialize submodules after cloning:
```bash
git submodule update --init --recursive
```

### Windows (MSYS2 MinGW-w64)

1. Download and install MSYS2 from [https://www.msys2.org/](https://www.msys2.org/). *(Do not install in a path containing spaces).*
2. Open the **MSYS2 MinGW x64** terminal and install build tools and libraries:
   ```bash
   pacman -S base-devel git mingw-w64-x86_64-binutils mingw-w64-x86_64-crt-git mingw-w64-x86_64-headers-git mingw-w64-x86_64-gcc-libs mingw-w64-x86_64-gcc mingw-w64-x86_64-gdb mingw-w64-x86_64-make mingw-w64-x86_64-tools-git mingw-w64-x86_64-pkg-config mingw-w64-x86_64-winpthreads-git mingw-w64-x86_64-libwinpthread-git mingw-w64-x86_64-winstorecompat-git mingw-w64-x86_64-libmangle-git mingw-w64-x86_64-pixman mingw-w64-x86_64-SDL2 mingw-w64-x86_64-glib2 mingw-w64-x86_64-capstone mingw-w64-x86_64-glfw mingw-w64-x86_64-lzo2 mingw-w64-x86_64-libxml2 mingw-w64-x86_64-libjpeg-turbo mingw-w64-x86_64-libpng
   ```
3. Set up toolchain aliases in the MSYS2 terminal:
   ```bash
   cp /mingw64/bin/ar.exe /mingw64/bin/x86_64-w64-mingw32-ar.exe && \
   cp /mingw64/bin/ranlib.exe /mingw64/bin/x86_64-w64-mingw32-ranlib.exe && \
   cp /mingw64/bin/windres.exe /mingw64/bin/x86_64-w64-mingw32-windres.exe && \
   cp /mingw64/bin/objcopy.exe /mingw64/bin/x86_64-w64-mingw32-objcopy.exe && \
   cp /mingw64/bin/nm.exe /mingw64/bin/x86_64-w64-mingw32-nm.exe && \
   cp /mingw64/bin/strip.exe /mingw64/bin/x86_64-w64-mingw32-strip.exe
   ```
4. **Configure:**
   ```bash
   ./configure --cross-prefix=x86_64-w64-mingw32- --disable-gtk --enable-sdl --enable-whpx --target-list=x86_64-softmmu --disable-werror
   ```
5. **Compile:**
   ```bash
   make install -j$(nproc)
   ```

### Running DragonLord Emulator

To launch via Hyper-V (WHPX):
```powershell
.\x86_64-softmmu\qemu-system-x86_64.exe -accel whpx -cpu android64 -m 4096 -smp 4 -machine usb=on -device usb-kbd -device usb-tablet -boot menu=on -soundhw hda -net nic -net user,hostfwd=tcp::5555-:5555 -device direct-express-pci -display sdl -hda hda.img -cdrom android_x86_64.iso
```

To launch via HAXM:
```powershell
.\x86_64-softmmu\qemu-system-x86_64.exe -accel hax -cpu android64 -m 4096 -smp 4 -machine usb=on -device usb-kbd -device usb-tablet -boot menu=on -soundhw hda -net nic -net user,hostfwd=tcp::5555-:5555 -device direct-express-pci -display sdl -hda hda.img -cdrom android_x86_64.iso
```

---

## 5. Licensing

This project is licensed under the **GNU General Public License v2 (GPLv2)**. See the [LICENSE](LICENSE) and [COPYING](COPYING) files for full details.
