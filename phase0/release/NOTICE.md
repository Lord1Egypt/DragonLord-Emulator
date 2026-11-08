# Third-party components

| Component | Where | Licence | Source |
|---|---|---|---|
| QEMU 11.1.3 (unmodified upstream) | `qemu/bin/qemu-system-x86_64` | GPL-2.0 (`LICENSE-QEMU-GPLv2`) | https://download.qemu.org/qemu-11.1.3.tar.xz, built as described below |
| Rutabaga gfx FFI, Gfxstream backend (Google prebuilt, from the Cuttlefish host package build 16644040) | `qemu/lib/librutabaga_gfx_ffi.so.0`, `qemu/lib/libgfxstream_backend.so.0` | Apache-2.0 / BSD-3-Clause | https://chromium.googlesource.com/crosvm/crosvm (rutabaga_gfx), https://android.googlesource.com/platform/hardware/google/gfxstream |
| libc++ (LLVM) | `qemu/lib/libc++.so.1` | Apache-2.0 with LLVM exception | https://github.com/llvm/llvm-project |
| GLib, PCRE2, pixman, libslirp, libaio, zlib (from Ubuntu 24.04) | `qemu/lib/` | LGPL-2.1+, BSD-3-Clause, MIT, BSD-3-Clause, LGPL-2.1+, zlib | Ubuntu 24.04 source packages (glib2.0, pcre2, pixman, libslirp, libaio, zlib) |

Downloaded on your machine at first run, not shipped here: Google's Android 17 Cuttlefish image and host tools (AOSP build 16644040, ci.android.com; AOSP licences, see the image's NOTICE files), KernelSU v3.3.1 (GPL-3.0, github.com/tiann/KernelSU), and, only if you run `./dragonlord gapps`, Google's proprietary Play Services / Play Store / Services Framework taken from Google's Android 16 x86_64 Play emulator image (Android SDK licence terms apply; for your own use).

## How QEMU was built

The Rutabaga header used at build time has one local change (`struct rutabaga_fence.ring_idx` is `uint8_t`, matching the Rust library); QEMU's own sources are unmodified.

```
PKG_CONFIG_PATH=<rutabaga-local>/lib/pkgconfig ../qemu-11.1.3/configure --target-list=x86_64-softmmu \
  --without-default-features --enable-kvm --enable-slirp --enable-vnc --enable-pixman --enable-rutabaga-gfx \
  --enable-vhost-user --enable-vhost-kernel --enable-vhost-net --enable-vhost-vdpa --enable-attr --enable-linux-aio \
  --enable-fdt=internal --disable-docs --disable-werror
ninja qemu-system-x86_64
```

DragonLord's own scripts (`dragonlord`, `tools/`) are part of the DragonLord-Emulator repository (GPL-2.0): https://github.com/Lord1Egypt/DragonLord-Emulator
