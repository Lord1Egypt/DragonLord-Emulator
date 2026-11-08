# DragonLord for Windows (preview)

One portable `DragonLord.exe`. Put it in any folder (another drive, a USB stick) and run it. It creates everything next to itself:

| Folder | Contents |
|---|---|
| `engine\` | Google's Android Emulator 37.2.13, platform-tools and the Android 16 Google Play x86_64 image, downloaded on first run from dl.google.com (about 2.9 GB), each file checked against a pinned SHA-256 |
| `instances\` | one emulator definition and disk per instance |
| `shared\` | your shared folder: "Copy shared folder" (or dropping a file on an instance) copies it into Android's `/sdcard/Shared` |
| `downloads\` | the verified downloads, reused if you set up again |
| `data\` | the panel's access token (keep private) |

The panel opens in your browser (`http://127.0.0.1:8770`, local only, token-protected): create instances (RAM, CPU cores, drive size, wide or phone screen, density), start/stop/delete, install APKs (button or drag and drop), shared folder. Each instance opens in its own emulator window using the Windows Hypervisor Platform and your GPU (Vulkan and OpenGL ES). No WSL is used.

Requirements: Windows 10/11 x64 with the Windows Hypervisor Platform enabled, about 8 GB free disk plus the instances' drives, enough free RAM for each instance (default 3 GB).

Not yet: root (Google Play images are locked user builds), IMEI setting, Android 17 (no Android 17 emulator image is published yet). Google's emulator and images are under the Android SDK licence; they are downloaded on your machine, not shipped by us.

Build from source (WSL/Linux, Go 1.22+): `./build.sh`.
