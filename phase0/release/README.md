# DragonLord (Linux / WSL edition)

Android 17 emulator for app development: KVM-accelerated QEMU 11.1.3, host-GPU (Gfxstream) or software graphics, optional KernelSU root and Google Play, several instances, and a local web panel with the screen in your browser (touch, keyboard, APK install by drag and drop, file transfer).

This is a **preview**. It has been tested on one machine (Windows 11 + WSL2 Ubuntu 24.04, NVIDIA RTX 2060). Native Linux desktops are expected to work but are not tested yet.

## Requirements

- x86_64 Linux with glibc 2.39 or newer (Ubuntu 24.04+, Debian 13+, Fedora 40+), or WSL2 on Windows 11 with such a distribution.
- KVM (`/dev/kvm`), python3, about 12 GB free disk, 8 GB RAM or more (each instance takes its RAM from `/dev/shm`).
- Host GPU mode: a working OpenGL driver (NVIDIA/AMD/Intel; on WSL the Windows GPU through Mesa). Otherwise choose software graphics.

## Start

```
tar xzf dragonlord-*-linux-x86_64.tar.gz
cd dragonlord-*-linux-x86_64
./dragonlord
```

The first run downloads Google's Android 17 image and Cuttlefish host tools (about 2 GB, from ci.android.com, SHA-256 checked) and the KernelSU files, then checks your machine. A few things need root once; the checker prints the exact commands, for example:

```
sudo groupadd -f cvdnetwork && sudo usermod -aG kvm,render,cvdnetwork $USER     # then log in again (WSL: wsl --shutdown)
sudo mkdir -p /usr/lib/cuttlefish-common/bin && sudo install -m 755 tools/capability_query.py /usr/lib/cuttlefish-common/bin/
```

Then `./dragonlord` opens the web panel in your browser. Create an instance (name, RAM, CPU cores, drive size, screen, DPI, serial, IMEI, GPU or software, root, Google Play) and press **View**.

Other commands: `./dragonlord help`, `./dragonlord doctor`, `./dragonlord gapps` (builds the Google Play bundle from Google's own image, 1.9 GB download), `./dragonlord vm create|start|stop|status|delete ...`.

## Where things are

Everything stays inside this folder (`data/`: Android image, instances, root and Google Play files, the panel's access token). Move or copy the folder and it keeps working; `DL_HOME=/other/place ./dragonlord` keeps the data elsewhere. Each instance has an adb address shown in the panel (`127.0.0.1:6520`, `6521`, ...) for Android Studio.

## Limits

- First boot of a new instance takes 4-8 minutes; later boots 1-2 minutes. All running instances' RAM must fit in `/dev/shm`.
- Browser view: about 19 frames per second; good for app work, not tuned for games.
- No sound yet. Guest network has no ping (ICMP).
- Google Play: Android 16 Google apps on Android 17 (no Android 17 x86_64 package exists); Google may ask you to register the device as uncertified before sign-in.
- "Root off" still has the image's debug `su` (userdebug build).
