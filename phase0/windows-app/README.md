# DragonLord for Windows (preview)

One portable `DragonLord.exe`. Put it in any folder (another drive, a USB stick) and run it. It creates everything next to itself:

| Folder | Contents |
|---|---|
| `engine\` | Google's Android Emulator 37.2.13, platform-tools and the **Light** Android 16 image (no Google services), downloaded on first run from dl.google.com (about 1.3 GB). The Google Play image (1.9 GB) is downloaded only if you choose it. Every file is checked against a pinned SHA-256 |
| `instances\` | one emulator definition and disk per instance |
| `shared\` | your shared folder: "Copy shared folder" (or dropping a file on an instance) copies it into Android's `/sdcard/Shared` |
| `downloads\` | the verified downloads, reused if you set up again |
| `data\` | the panel's access token (keep private) and `dragonlord.log` |

DragonLord.exe has no console window; first-run setup shows a progress bar in the panel and everything is logged to `data\dragonlord.log`. The panel opens in your browser (`http://127.0.0.1:8770`, local only, token-protected): create instances (RAM, CPU cores, drive size, wide or phone screen, density), start/stop/delete, install APKs (button or drag and drop), shared folder. Each instance opens in its own window titled "DragonLord - <name>", using the Windows Hypervisor Platform and your GPU (Vulkan and OpenGL ES). No WSL is used.

Measured Light versus Google Play on the same PC: 16 s versus 25 s from a snapshot, 1.1 GB versus 2.3 GB RAM when idle, 17 % versus 159 % of a core when idle (see `../WINDOWS-OPTIMIZATION.md`). Boot times measured on a Windows 11 PC with an RTX 2060 and little free RAM: the first start of a new instance is a cold boot (about 2.5 minutes); stopping saves a quick-boot snapshot, and later starts take about 15 seconds.

Requirements: Windows 10/11 x64 with the Windows Hypervisor Platform enabled, about 8 GB free disk plus the instances' drives, enough free RAM for each instance (default 3 GB).

**Clone** copies a stopped instance together with its quick-boot snapshot (the clone starts in about 8 s); **Rename** moves one. **Root** works on the Light image (adb root, `su`), not on Google Play. **Terminal**: a root-capable shell in the browser. Not yet: IMEI setting, Android 17 (no Android 17 emulator image is published yet). Google's emulator and images are under the Android SDK licence; they are downloaded on your machine, not shipped by us.

Build from source (WSL/Linux, Go 1.22+): `./build.sh`.
