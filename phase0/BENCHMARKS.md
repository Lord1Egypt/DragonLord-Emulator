# Objective performance and stability protocol

**No Android/GPU benchmark results exist yet.** Numbers below are proposed acceptance targets and measurement definitions, not measurements. The diagnostic Linux boot time in evidence is only a harness sanity result and must not be compared to Android boot performance.

## Controlled configuration and workloads

Record run ID, UTC start, Git/source manifests and hashes, executable/DLL hashes, full VM argv, Windows/Linux build, WHPX/KVM state, CPU/GPU models and selected adapter, drivers, power plan, monitor refresh, guest resolution/DPI, RAM/vCPU allocation, graphics API/backend/capsets, Android fingerprint/kernel, and root/SELinux state. Keep charger/power settings and background workload controlled. Log thermal throttling and GPU clock/power state. Treat the hybrid Intel/NVIDIA laptop's selected adapter as an explicit parameter; do not infer selection from a GPU being installed.

Initial scenario: 1920x1080 at 60 Hz, 4 vCPUs and 4 GiB guest RAM, one VM. Use independently pinned workloads: (1) idle launcher and deterministic UI scrolling; (2) a GLES scene with fixed geometry/textures; (3) a Vulkan scene with equivalent visual work; (4) upload/readback and fence stress; (5) resize/rotation/context-loss recovery. Add real applications only after deterministic workloads. Fix shaders, assets, random seeds, capture settings, application build hashes and replay sequence. A Linux/KVM reference is only directly comparable when CPU/GPU hardware, drivers, work and guest build are controlled; otherwise call it a functional comparison.

Warm up for 60 seconds, capture at least 300 seconds per graphics workload, repeat five times and report every run plus median and spread. Record cold/warm shader caches separately. Keep instrumented correctness runs separate from performance runs when tracing overhead is material. Perform ten cold Android boots and ten guest reboots. Stability qualification is a separate 24-hour mixed-load run, including 100 resize/rotation cycles and 50 app/context restart cycles.

## Metrics

| Metric | Definition and collection | Required output |
|---|---|---|
| FPS | Count distinct completed guest frames per elapsed monotonic second; also count host displayed frames separately. Use Android Perfetto FrameTimeline and host presentation tracing. Exclude loading/warmup by declared windows. | Mean FPS, 1-second series, workload phase, submitted/completed/displayed counts; identify repeats/drops. |
| Frame pacing | Intervals between actual presentations, not just app submissions. Use guest FrameTimeline plus Windows PresentMon/ETW when that presentation API is supported. Instrument the selected renderer if host OpenGL presentation is not visible to the chosen tool. | p50/p95/p99 interval in ms, maximum, jitter, missed refresh deadlines and stalls >100 ms. |
| Latency | Separate input injection→guest handling→frame completion→host presentation. Correlate trace IDs and calibrated clocks. ADB event round-trip is not display latency. | p50/p95/p99 software latency with precise endpoints; physical input-to-photon only with high-speed camera/photodiode or validated equivalent. |
| CPU | Sample cumulative user+kernel CPU time for the VM, renderer/helper process tree, and relevant guest processes; report `delta CPU seconds / wall seconds` as cores used. Also show percentage normalized by host logical CPUs. | Mean/p95 cores used, per-process breakdown, per-vCPU time, idle/load phases. |
| GPU | Correlate guest workload submissions with engine/PID activity on the selected physical adapter through ETW/GPUView/vendor tools on Windows, or validated counters on Linux. A global Task Manager percentage is insufficient. | Engine busy time/utilization, adapter identity, renderer PID, clocks, VRAM usage, software-control comparison. |
| Host and guest memory | Host private committed bytes, resident working set and peak for the full process tree; GPU dedicated/shared allocations separately. Guest PSS/RSS and available RAM from Android dumpsys/Perfetto. Avoid double-counting shared pages. | Idle/warm/steady/peak bytes and time series; post-cycle recovery and long-run growth slope. |
| Boot time | Start at VM process launch; finish at `sys.boot_completed=1`, then separately first responsive launcher frame and ADB usability. Define cold disk/cache and warm restart independently. | Ten individual observations, median/p95, failures/timeouts, image/cache state. |
| Stability | Guest kernel panics, ANRs, renderer/device loss, QEMU crashes/hangs, GPU TDRs, graphics corruption and resource leaks. Collect guest logcat/dmesg and host events. | Failure count per VM-hour; raw incident traces; recovery outcome; all cycle counts. |

## Proposed initial thresholds

These targets must be confirmed on the first qualified hardware configuration before comparing implementations. They are not a promise for every application or machine.

- Deterministic light UI/GLES/Vulkan workloads: median displayed FPS at least 58 at a 60 Hz target, p95 frame interval ≤20 ms, p99 ≤33.4 ms; <1% missed target deadlines and no unexplained >100 ms steady-state stalls.
- Software input-to-present latency p95 ≤50 ms for the controlled scene; if physical instrumentation is unavailable, explicitly leave physical input-to-photon **BLOCKED**.
- Android cold process-to-boot-complete median ≤30 seconds and p95 ≤45 seconds on the qualified reference configuration, with all ten boots passing. Record the responsive-frame endpoint independently.
- After warmup, steady CPU/memory budgets must be set from measured native reference and software-control runs; never invent an efficiency ratio before those baselines exist. Initial idle target: ≤0.25 host cores for the full process tree. Initial host private-commit budget: ≤6 GiB with a 4 GiB guest. Record actual usage before retaining or revising these targets through an ADR.
- After resize/app-restart cycles, resources return within 5% of the measured warm baseline; over a stable 24-hour workload, unexplained private-memory growth ≤100 MiB. No host crashes, guest panics, GPU TDRs, silent fallback, or unrecovered corruption.

Any missing required instrument yields BLOCKED for its metric, not zero or PASS. Metrics with known instrumentation gaps remain unqualified even if other metrics pass. Preserve raw data and analysis version, including excluded intervals and justification. Keep standard and KernelSU profiles in separate result sets.

## Proving hardware acceleration

A hardware name in `vulkaninfo`, EGL initialization, a visible desktop, high FPS, WHPX activity, or an advertised capset alone is insufficient. Require a completed guest graphics correctness workload, the actual host device selected by that renderer, correlated hardware execution traces and correct changing output. Run a software backend control and demonstrate the evidence pipeline distinguishes it. Declare whether rendering, composition, or video decoding was accelerated; do not generalize one to all three.

Primary instrumentation references: [Perfetto FrameTimeline](https://perfetto.dev/docs/data-sources/frametimeline), [Intel PresentMon](https://github.com/GameTechDev/PresentMon), [Microsoft GPUView](https://learn.microsoft.com/en-us/windows-hardware/drivers/display/using-gpuview), [QEMU trace events](https://gitlab.com/qemu-project/qemu/-/blob/v11.1.3/docs/devel/tracing.rst).
