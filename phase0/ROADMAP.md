# Validation roadmap and granular tickets

Statuses describe this mission's captured evidence. DONE means the ticket's stated inspection/artifact work is complete; it does not mean a runtime gate passed. BLOCKED means a prerequisite or test facility is missing. DEFERRED means outside Phase 0 authorization. No remote issues or releases were created.

## Phase 0 — validate before migration

| Ticket | Work / current status | Depends on | Definition of done and required evidence |
|---|---|---|---|
| P0-01 | Preserve legacy and lock current QEMU — DONE | — | Dedicated branch, unchanged main/legacy hash, release page/tag/VERSION agreement, exact upstream commit in lock and preservation evidence. |
| P0-02 | Clean Linux build and diagnostic TCG boot — DONE | P0-01 | Pristine source builds; checksummed upstream diagnostic assets; real guest login/nonce/architecture; exact argv/binary hash, serial/QMP logs; snapshot base unchanged. GPU/Android fields remain NOT_TESTED. |
| P0-03 | Legacy/modern API compatibility audit — DONE, incompatible outcome | P0-01, P0-02 | Reproducible original-source compile probes plus source-linked build/QOM/virtqueue/atomic/ABI/lifecycle table; document failing units and virtio ID collision. No legacy edits. |
| P0-04 | Windows compiler/DLL closure and WHPX diagnostic — DONE | P0-01 | Pinned isolated cross-build passed; native executable enumerated WHPX and booted the same diagnostic with fresh guest nonce, clean QMP quit and unchanged disk. Logs and binary/DLL hashes retained. No software fallback; graphics untested. |
| P0-05 | Linux/KVM and physical GPU comparison host — BLOCKED | P0-02 | Usable /dev/kvm and render node on the comparison machine; strict KVM diagnostic passes with QMP enabled=true; GPU/driver inventory captured. |
| P0-06 | Native Windows Gfxstream renderer test — BLOCKED | P0-04 | Pin renderer and complete dependency/build manifests; run upstream host end-to-end GL/VK correctness tests on a physical ICD; save readback images/test logs/device identity and GPU execution trace; software control distinguished. Standalone result stays separate from VM integration. |
| P0-07 | QEMU/Rutabaga Windows device/memory/fence experiment — BLOCKED | P0-04, P0-06 | Pin/build compatible FFI; actual device/context creation and capset negotiation; blob-map/write/read round-trip, handle close/reuse and fence completion under WHPX; visible scanout/resize correctness. Do not begin a legacy renderer port. |
| P0-08 | License/link graph and distribution feasibility — BLOCKED | P0-01, P0-06 | SBOM for exact linked artifacts; resolve GPLv2/Apache-2.0 combination and per-file terms, LGPL runtime obligations, notices and source/build-material delivery plan. Record review decision; no blanket assumptions about DLLs/processes. |
| P0-09 | Qualify existing Android16 reference artifact on Linux — BLOCKED | P0-05 | Select complete unmodified prebuilt Cuttlefish product+host tools with build ID, hashes/resolved manifest/kernel modules; prove Android16/API36/x86_64 and responsive enforcing guest; run GL/VK control tests. No custom image development. If no suitable artifact is obtainable, record that blocker. |
| P0-10 | Existing Android16 guest on Windows/WHPX — BLOCKED | P0-07, P0-09 | Map required board/partitions/host services using qualified artifacts; successful real boot, ADB/UI, matching HAL/driver stack and guest workload correlated with physical GPU execution. A logo or renderer string is insufficient. If the artifact requires a new BSP, stop and revisit gate scope. |
| P0-11 | Instrumentation and short performance validation — BLOCKED | P0-10 | Run pinned UI/GLES/Vulkan/transfer scenes and software control; capture FPS/pacing/latency/CPU/GPU/memory/boot metrics with stated endpoints; report uncertainty and missing physical latency instruments; short stability run. No fabricated missing counters. |
| P0-12 | Foundation decision review — BLOCKED | P0-03, P0-04, P0-07, P0-08, P0-10, P0-11 | Source+runtime evidence reviewed against proposed architecture. Explicit GO/CONDITIONAL GO/NO-GO and allowed next scope. Full migration/image development stays closed until this gate passes. |
| P0-13 | Optional KernelSU feasibility specification — DONE; runtime BLOCKED | P0-01 | Pin kernel/KernelSU research sources; document config/ABI/hardening and license requirements, isolated opt-in profile, grant/deny/rollback tests. Do not claim compatibility. Its runtime completion is optional for an unrooted foundation decision. |

P0-04 evidence is in `evidence/build-windows-cross.json`, `evidence/windows-native-inventory/` and `evidence/windows-whpx-boot/`. The cross-build required a pinned upstream MinGW header overlay; QEMU remained pristine. P0-06 is now the next Windows experiment. It remains unexecuted, with no built renderer or pinned complete renderer dependency set. No renderer migration has begun.

## Phase 1 — authorized only after P0-12 passes

| Ticket | Work / status | Depends on | Definition of done |
|---|---|---|---|
| P1-01 | Modern engine layout — DEFERRED | P0-12 | Preserve legacy under its existing history; introduce modern integration in an agreed structure without overwriting reference sources; reproducible toolchain locks. |
| P1-02 | Windows VM supervisor — DEFERRED | P1-01 | QMP-driven lifecycle, selected accelerator, deterministic configuration, logs, startup failures and shutdown/reset tests. |
| P1-03 | Minimal Windows graphics adapter — DEFERRED | P0-07, P1-01 | Implement only interfaces shown missing by the experiment; validated ABI, shared memory, fences, scanout and error recovery. |
| P1-04 | Android16 guest product/BSP — DEFERRED | P0-12, P0-09 | Authorized source build pinned to a maintained release; kernel/module/partition/AVB/HAL integration validated against the reference. |
| P1-05 | Display/input/resizing integration — DEFERRED | P1-02, P1-03, P1-04 | Correct DPI/rotation, key/mouse/touch routing and 100 resize cycles, with latency evidence. |
| P1-06 | Optional KernelSU image/profile — DEFERRED | P0-13, P1-04 | Exact custom kernel boots; manager/kernel alignment, grant/deny, SELinux expectations, rollback and graphics regression tests pass. Stock remains default. |

## Phase 2 — correctness, robustness and performance

| Ticket | Work / status | Depends on | Definition of done |
|---|---|---|---|
| P2-01 | Graphics correctness suite — DEFERRED | P1-03, P1-04 | Pinned dEQP/VK-GL-CTS subsets and image comparisons; feature/extension claims match tests and failures are tracked. |
| P2-02 | Transport/security hardening — DEFERRED | P1-03 | Malformed command/resource/fence corpus, fuzzing and sanitizer coverage; bounds/lifetime/ownership failures fixed; threat-model review. |
| P2-03 | Performance optimization — DEFERRED | P2-01, P0-11 | Optimize identified bottlenecks with before/after traces, controlled repeated runs and no correctness regression. |
| P2-04 | Stability and leak qualification — DEFERRED | P2-01, P2-02 | 24-hour load, restart/resize cycles, measured growth slope, no unresolved crashes/TDRs/panics/hangs. |
| P2-05 | Multi-vendor Windows matrix — DEFERRED | P2-03, P2-04 | NVIDIA, AMD and Intel configurations with recorded drivers; no inference from one vendor; standard/root profiles separated. |

## Phase 3 — delivery, requiring separate publication authorization

| Ticket | Work / status | Depends on | Definition of done |
|---|---|---|---|
| P3-01 | Installer/update/rollback — DEFERRED | Phase 2, P0-08 | Reproducible binaries, complete DLL closure, source/notices/SBOM, local update and rollback validation. |
| P3-02 | Release approval — DEFERRED | P3-01 | Explicit owner publication authorization, reviewed evidence and known limitations, signed/checksummed artifacts and support scope. No release is authorized by Phase 0. |

## Gate reopening criteria

GO requires native Windows end-to-end graphics and Android16 evidence plus acceptable correctness, measured short-run behavior and resolved architectural blockers. A CONDITIONAL GO must list finite, non-foundational remaining conditions and the exact limited next work permitted. BLOCKED Windows graphics or Android boot is a foundational gap, so it cannot be called a GO for migration. KernelSU can stay deferred for an unrooted product, with no compatibility claim for that profile.
