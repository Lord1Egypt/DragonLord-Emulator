# Android 17 Cuttlefish guest on our QEMU 11.1.3 (WSL2 test bench)

Status 2026-11-08: reported evidence from one machine (i7-9750H, RTX 2060, WSL2 kernel 6.18). Not owner-attested.
The guest is **Android 17 (SDK 37)**, not Android 16; the user chose to continue with it. Windows is the product target; this is the Linux test bench.

## Inputs (downloaded by the user from ci.android.com, branch `aosp-android-latest-release`, target `aosp_cf_x86_64_only_phone-userdebug`, build 16644040)

| File | SHA-256 |
|---|---|
| `aosp_cf_x86_64_only_phone-img-16644040.zip` | `eccdb248e171af6cb98711a6f2fbd5e5017e9c3a6e82337580181bbd4bb2c41b` |
| `cvd-host_package.tar.gz` | `ec02c8e23985b37d9769732bf8bed992f10d851f40f7a835cf97128888900ecc` |

Both are unpacked into `phase0/.work/cuttlefish/cvd/` (untracked). The host package ships Google's QEMU 10.2.90 plus `librutabaga_gfx_ffi.so.0` and `libgfxstream_backend.so.0`.

## One-time host setup (needs root)

- `/usr/lib/cuttlefish-common/bin` symlink to the unpacked `cuttlefish-base` deb `bin/`. `launch_cvd` runs `/usr/lib/cuttlefish-common/bin/capability_query.py qemu_cli` from that fixed path; without it, `-vm_manager=qemu_cli` is rejected as "not supported on this machine".
- Groups `kvm`, `render`, `cvdnetwork` for the user (`cvdnetwork` must exist or `assemble_cvd` fails with `Failed to get group id: cvdnetwork`). Restart WSL so they apply.
- Two TAP devices, because the QEMU argv opens them by name (lost on WSL restart):
  `ip tuntap add dev cvd-mtap-01 mode tap vnet_hdr user $USER` and the same for `cvd-etap-01`, then `ip link set <dev> up`.

## Our QEMU

Upstream QEMU 11.1.3 configured with `--enable-kvm --enable-virglrenderer --enable-rutabaga-gfx --enable-opengl --enable-sdl --enable-gtk --enable-slirp` (build dir `phase0/.work/qemu-build-gpu`, meson 1.11.1 from `.work/build-venv`).
Rutabaga comes from a local pkg-config package (`phase0/.work/rutabaga-local`): Google's two prebuilt libraries plus `libc++.so.1`, and the header `rutabaga_gfx/rutabaga_gfx_ffi.h` from `.work/rutabaga-gpu-feasibility` with **one change: `struct rutabaga_fence.ring_idx` is `uint8_t`** (the Rust `RutabagaFence.ring_idx` is `u8`; the C header says `uint32_t`).
Put a stand-in where the launcher looks: copy `phase0/tools/qemu-shm-wrapper.sh` to `phase0/.work/cuttlefish/qemu-ours/qemu-system-x86_64` (edit `REAL=` to your build). It moves the guest-RAM file `qemu.mem` from disk to `/dev/shm` and passes everything else through. **This matters on WSL**: with the file on disk the same boot took 262-394 s and the guest hit ANRs ("System UI isn't responding") because of disk I/O pressure; with `/dev/shm` it boots in 50-66 s. Delete `/dev/shm/dragonlord-cvd-1.mem` after each run (it holds 4 GB of RAM until removed).

## Launch

```
cd phase0/.work/cuttlefish/cvd && export HOME=$PWD
# software graphics
bin/launch_cvd -vm_manager=qemu_cli -qemu_binary_dir=$PWD/../qemu-ours -gpu_mode=guest_swiftshader \
  -start_webrtc=false -daemon=false -report_anonymous_usage_stats=n -use_allocd=false -memory_mb=4096 -cpus=4 -console=true
# host GPU through Gfxstream (GL on the NVIDIA GPU via Mesa d3d12)
GALLIUM_DRIVER=d3d12 bin/launch_cvd ... -gpu_mode=gfxstream
adb connect 127.0.0.1:6520 ; bin/stop_cvd
```

## Results

| Mode | Result |
|---|---|
| `guest_swiftshader`, Google QEMU | boot completed, ADB works, SELinux enforcing |
| `guest_swiftshader`, our QEMU 11.1.3 | boot completed (only a `-mon` deprecation warning) |
| `drm_virgl`, our QEMU | **fails**: SurfaceFlinger aborts "couldn't find an OpenGL ES implementation"; the image has no Mesa/virgl guest driver |
| `gfxstream`, our QEMU + `GALLIUM_DRIVER=d3d12` | boot completed; guest GLES renderer `Android Emulator OpenGL ES Translator (D3D12 (NVIDIA GeForce RTX 2060))`; lock screen and quick settings render correctly |

Not proven: any speed gain (no valid benchmark yet). No hardware Vulkan on WSL (only llvmpipe), so Gfxstream Vulkan and Vulkan composition run in software (`useVulkanComposition: false`). The display is asleep behind the keyguard after boot; send `KEYCODE_WAKEUP` and a swipe before screenshots.
Debug logs for any run: `phase0/tools/dlrun.py scan <run dir>`; Cuttlefish logs are in `cuttlefish/instances/cvd-1/logs/` (`launcher.log`, `logcat`, `kernel.log`).

## Benchmark (`phase0/tools/dl-bench.py`, 40 Settings scroll pairs, 4 vCPU, 4 GB, 2 runs per mode, 2026-11-08)

| Mode | Boot s | Workload s | Median frame ms | Slow frames % | GPU util avg % |
|---|---|---|---|---|---|
| guest_swiftshader | 52 / 50 | 22 / 28 | 32 / 38 | 33 / 40 | 0.1 / 0.0 |
| gfxstream (RTX 2060 GL via d3d12) | 66 / 64 | 20 / 23 | 27 / 53 | 31 / 55 | 24 / 23 |

Reading: no clear speed difference on this light UI workload; run-to-run noise is as large as the gap. Gfxstream boots about 14 s slower. The GPU is demonstrably used (about 23% vs 0%). Earlier numbers taken with RAM on disk (boot 262-394 s, 3.3 s frames) were an I/O artefact and are invalid. A heavy GL workload and a native-Windows run are still needed before claiming a speed benefit.

## Root

- Built-in (userdebug image): `adb root` gives uid 0 (`u:r:su:s0`); `/system/xbin/su` works for the shell user (`su 0 id`). Development only.
- KernelSU v3.3.1, LKM mode, no kernel build: `phase0/tools/ksu-patch.sh` patches `init_boot.img` with `lkm-x86_64-android16-6.12_kernelsu.ko` and `ksuinit-x86_64` (files from the v3.3.1 GitHub release into `phase0/.work/kernelsu`, sizes checked, SHA256SUMS kept). Boot it with `launch_cvd ... -init_boot_image=<path>/init_boot_ksu.img`; the stock image stays untouched, so rollback is just not passing the flag.
- Verified 2026-11-08 (software graphics, our QEMU): `ksuinit` loads `kernelsu.ko` at ~4 s (kernel log "KernelSU: welcome to KernelSU version 32680"), `/proc/modules` lists `kernelsu`, `ksud debug version` = 32680, the manager APK shows **Working, 32680-5, LKM** on kernel 6.12.74-android16-6, boot completes, SELinux stays Enforcing.
- Caveats: the module was built for 6.12.76 and loads on 6.12.74 only because the loader ignores vermagic (kernel notes it is unsigned and taints). On x86_64 the module patches `x64_sys_call` and installs its syscall dispatcher in slot 134, which weakens a syscall-hardening mitigation: keep this profile opt-in. `ksud` is only installed into `/data/adb` when the manager first launches, so the first boot logs `Cannot find '/data/adb/ksud'` for its init hooks; the installer should pre-install it. Per-app grant/deny and reboot persistence were then tested (below); graphics regression with this profile is **not yet tested**.

### KernelSU grant / deny / persistence (2026-11-08, shell uid 2000 via the manager UI, Superuser tab -> Shell -> toggle)

| Step | Result |
|---|---|
| before grant, `/system/bin/su -c id` as shell | `inaccessible or not found` (denied) |
| after granting Superuser to Shell | `uid=0(root) ... context=u:r:ksu:s0` (KernelSU domain, distinct from the debug su `u:r:su:s0`) |
| after revoking | denied again |
| grant, `sync`, full VM stop/start, no manager opened | still `uid=0 ... u:r:ksu:s0` (persisted in `/data/adb/ksu/.allowlist`) |
| grant, immediate `stop_cvd` (power cut, no sync) | grant **lost**: data not flushed. Launcher must shut instances down gracefully |

The image's own debug `/system/xbin/su` stays available regardless (userdebug build), so a real "root off" instance needs a base image without it.

## GPU benchmark with a real GL workload (`tools/glbench`, `tools/dl-glbench.py`, 2026-11-08)

`tools/glbench/glbench.c` (built with the NDK: `x86_64-linux-android30-clang -O2 -o glbench glbench.c -lEGL -lGLESv3 -llog`) renders 30 frames of a heavy fragment shader at 1280x720 into an offscreen FBO inside the guest. 2 boots per mode, 3 runs per boot per size, stock init_boot, 4 vCPU:

| Shader loop | Software (SwiftShader), median ms/frame | GPU (Gfxstream, RTX 2060 GL via d3d12), median ms/frame | Speedup |
|---|---|---|---|
| 8 iterations | 29.7 (range 22.1-32.1) | 3.7 (range 3.4-5.8) | 8.1x |
| 32 iterations | 76.1 (range 63.0-115.6) | 5.6 (range 4.9-9.4) | 13.6x |

Renderer strings confirm the path (`ANGLE (SwiftShader)` vs `Android Emulator OpenGL ES Translator (D3D12 (NVIDIA GeForce RTX 2060))`). Image checksum identical at 8 iterations (9632) and within 1 count at 32 (9951 vs 9952, floating-point difference). The light Settings-scroll benchmark above could not show this gap because the CPU renderer keeps up with a simple UI; heavy 3D is where the GPU pays off.
Caveats: GL only (no hardware Vulkan on WSL); the GPU time is dominated by per-frame round trips at these sizes, not GPU load (nvidia-smi sampling at 1 s is too coarse for such short runs and is not used as evidence); the native test program must `_exit()` because the gfxstream EGL stack aborts in static destructors at normal exit (`pthread_mutex_lock called on a destroyed mutex`), which an ordinary app does not hit in the same way but is worth a regression test.
