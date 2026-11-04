# Phase 0.7 interruption recovery report

**Recovery milestone: validated. Architecture verdict: NO-GO for guest-visible GPU integration, unchanged.** This report recovers unfinished engineering work and diagnoses three development failures. It does not declare Phase 0.7 complete.

Reviewed/published starting commit: `4de8297ab162e71b0271c5e9e6148c44b5ef360a`. Branch: `phase0/architecture-feasibility`. [Draft PR #1](https://github.com/Lord1Egypt/DragonLord-Emulator/pull/1) records the resulting commit SHA and revision-specific CI. The implementation, report, commands and evidence are committed together; the PR's commit permalink identifies their exact revision.

## Recovered state and preservation

At recovery start, HEAD and the branch matched the reviewed commit. There were no tracked edits or additional local commits, and `phase0/gpu-readiness/` was untracked. The six recent commits were the initial release and the published Phase 0–0.6 milestones. Existing native output also remained under `C:\DLGPU\p07-20261104\results` and ignored build/command data under `phase0/.work/gpu-readiness`.

A non-destructive snapshot was created at `phase0/.work/gpu-readiness/recovery-snapshot-20261104T1008` before further edits. The [pre-recovery inventory](evidence/pre-recovery-inventory.json) records 59 files with paths, sizes and SHA256 hashes, including files hidden by ordinary ignore-aware searches. The snapshot preserves the original package source; exact original native logs are now also published under [recovered-native](evidence/recovered-native/). [Preservation checks](evidence/preservation-check.json) confirm all 44 original package-evidence/native-result files remain byte-identical. Source edits have before-fix copies. Earlier attempts did not retain every historical source revision or output-binary hash; no missing variant is reconstructed and presented as original evidence. New recovery commands retain before/after source hashes and native binary identities. No reset, clean, evidence overwrite, history rewrite or deletion occurred.

All Phase 0/0.5/0.6 evidence is unchanged. Their 77, 43 and 284 indexed artifacts revalidate. Pristine upstream QEMU/Gfxstream/Rutabaga working trees are retained. New native source/object/executable names prevent overwriting the earlier observer; future core-probe builds require a fresh work directory. No binary is uploaded. [CHANGED-FILES.txt](CHANGED-FILES.txt) lists the complete recovery change set, including the modern validation workflow.

## 1. JSONDecodeError, line 1 column 108

The error is reproduced exactly from the retained hardware log. It is JSON line 1 within an individually decoded record, at physical stdout line 606. [Diagnosis](evidence/json-diagnosis/result.json) retains the raw malformed line and source hash:

```text
..."luid_low":74745,"vendor":4318[compositor_vk.cpp(172)] Created CompositorVk
```

The parent observer wrote `DLK` JSON records to stdout while its Gfxstream child inherited the same output stream. Buffered parent writes and child logging interleaved inside records. The hardware file contains 21 malformed `DLK` lines; the software file contains two. This is a transport/serialization failure, not evidence that the JSON decoder was too strict or a GPU failure.

The observer now writes diagnostics to a dedicated `kernel.jsonl` file; child stdout/stderr retain their own established capture paths. The [strict parser](tools/parse-kernel-trace.py) rejects corruption, incomplete traces, failed/timed-out children and mismatched sample PIDs. It does not skip invalid JSON or turn invalid numeric-zero samples into valid data. The original corrupted record remains an explicit failing regression at column 108.

One three-test compositor iteration per control was sufficient to test the transport fix. Both child processes exit 0, with three successful pixel tests each. Separate traces parse completely: [hardware parse](evidence/recovered-hardware-parse.json), [software parse](evidence/recovered-software-parse.json), and corresponding raw files in `evidence/recovered-native/recovery-smoke-{hardware,software}`. Parse PASS qualifies trace format/completion only.

## 2. QOM assertion: type->abstract == false

The original construction call was `object_new(TYPE_OBJECT)` in [core_smoke_initial.c.in](experiments/core_smoke_initial.c.in). In pinned QEMU `005c61c0ef6f6ae615283440b4bb7be51b2c6ddd`, [`qom/object.c`](https://gitlab.com/qemu-project/qemu/-/blob/v11.1.3/qom/object.c) registers `object_info` with `.name = TYPE_OBJECT`, `.instance_size = sizeof(Object)`, `.class_init = object_class_init`, and **`.abstract = true`**. `register_types()` installs this root through `type_register_internal`. `object_new` eventually calls `object_initialize_with_type`, whose enabled assertion rejects an abstract type before construction. This assertion is correct.

The fixture needed a concrete memory owner, not the abstract QOM base. [Corrected fixture](experiments/core_probe.c.in) registers `phase07-smoke-owner` using `type_register_static`: parent `TYPE_OBJECT`, instance size `sizeof(Object)`, default `.abstract = false`. It then calls `object_new("phase07-smoke-owner")`. The hierarchy is `phase07-smoke-owner → object`; no production device type is substituted or redefined. Parent registration already occurs in QEMU's normal initialization.

The corrected object was compiled before the interruption but had not been run. Recovery verified the executable hash against its build record, then executed only its `safe` mode. [Actual run](evidence/core-smoke2-safe-run/result.json): **exit 0**, real QEMU `MemoryRegion` initialization, `address_space_map` and `address_space_unmap` complete. Source SHA256 is `a1d81d3ac855abbed53da3e6b0b4f229c8f156d006e26cd90ea61b928005a897`; executable SHA256 is `5b7b37f893450bd573384bbd40b3729a4680414464918e494987eb5f6a1470bd`. Original assertion failures remain in `evidence/core-initial-runs`.

No assertion was disabled and no abstract flag in QEMU was changed. The probe main is ASan/UBSan instrumented and relinked with existing QEMU core objects; those objects were not rebuilt with sanitizers. Leak detection is disabled for this bounded startup smoke, and coroutine-support warnings are preserved. This is not a clean rebuild, fully sanitized QEMU test, actual Rutabaga map/unmap test, concurrent-reader test or retirement proof. The corrected `unsafe` mode was **not run** during recovery.

## 3. Native PowerShell exit 1 with unavailable console output

The command/result records identify separate native build failures rather than one unexplained Windows failure:

| Attempt | Actual result/cause | Existing correction |
|---|---|---|
| `kernel-build-1` | FAIL, clang exit 1; library arguments treated as compilation inputs with `/Fo` | Pass libraries after `/link` |
| `kernel-build-2` | FAIL, clang exit 1; SDK `NTSTATUS` undeclared | Include installed SDK `winternl.h` before `d3dkmthk.h` |
| `kernel-build-3` | BUILD PASS; original shared-output runtime logs later corrupt | Preserve compilation result; do not qualify those trace records |
| `kernel-build-4` | FAIL, clang exit 1; `/WX` rejects deprecated `_wfopen` | Use `_wfopen_s`, preserving `/W4 /WX` |

The old native runner deliberately redirects child stdout and stderr into files, then propagates failure as PowerShell exit 1 without echoing diagnostics. The output was unavailable at the console boundary, but **not lost**: [build-4 stderr](evidence/recovered-native/kernel-build-4/stderr.log) contains the complete compiler error. No missing executable, permission failure or unsupported native operation explains this command's failure.

The secure writer correction [compiles successfully](evidence/recovered-native/recovery-fixed-build/result.json) at a fresh filename with the same pinned clang-cl, SDK and strict warning flags. The exact before-fix source is [preserved](evidence/source-snapshots/kernel-observer-before-recovery.cpp). Compiling it as a negative control still **FAILS, child/wrapper exit 1**, under the new [diagnostic wrapper](tools/run-native.ps1). That wrapper prints the status, exit code, result location and stderr tail while retaining complete raw logs and the original exit. It never converts a failed command into success. No deprecation suppression was added.

## Status of Phase 0.7 work

See [GATES.md](GATES.md) for individual gates and implementation state. T1 and T2 have partial source/diagnostic work; T3 lifecycle tests, T4 cross-compiler FFI qualification and T5 new SBOM/link-graph/vulnerability work were not implemented. T6 streaming remains blocked and unattempted. T7 now has a validated recovery checkpoint and narrow parser/CI regressions, not full phase-wide reproducibility qualification.

Useful retained findings include current upstream master `f29ccc287a6cfdd51d3a4fd17fbe9af3310a0ac5`, its Rutabaga path history, exact fence-fix patch and [cleanup fix ca5d368f](https://github.com/qemu/qemu/commit/ca5d368f110b11d5a9565c211b8d40bb72a131ac). The cleanup change addresses leaked guest-backing metadata, **not** the still-present mapped-pointer lifetime warning. These patches are preserved evidence; they are not applied to the pristine source or validated as a new lifecycle correction in this milestone.

The read-only [Windows rights/hook audit](evidence/recovered-native/rights-hooks/result.json) shows no elevated administrator token and no Performance Log Users membership. OBS `graphics-hook64.dll` and TikTok `game_detour_64.dll` are signed and retain the previous hashes. Both still appear in recovered renderer module observations. No application was stopped, hook disabled, driver changed, global setting changed or tracing permission granted.

The experimental D3DKMT observer obtains PID/LUID/raw accounting data, including successful and unsuccessful queries. Successful software observations returned raw zero while invalid observations remain invalid. This does not resolve the older invalid PDH control, validate a complete GPU queue timeline or independently isolate hook activity. [Microsoft documents D3DKMTQueryStatistics as reserved for system use](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3dkmthk/nf-d3dkmthk-d3dkmtquerystatistics). Its semantics, coverage and attribution still need qualification. No FPS, GPU utilization, frame timing or complete T1 PASS is claimed.

## Validation and remaining blockers

Executed recovery checks: corrected QOM safe smoke exit 0; original compiler negative exit 1 with visible stderr; corrected native compile exit 0; hardware/software three-test pixel smokes exit 0 and separate trace parses PASS; five fail-closed parser regressions PASS; pinned Python lint and native PowerShell parsing. Original negative logs remain negative. The three successful modern CI jobs are preserved and extended with readiness artifact integrity, parser tests and lint; the existing 38 corrected source-fence regressions remain mandatory and unchanged. Hosted results are recorded separately against their actual published revision in the PR.

MemoryRegion/RCU/WHPX retirement, callback ownership/reset generation, MinGW↔MSVC full renderer ABI, independent hardware attribution and the complete licensing/security review remain unresolved. No guest-visible GPU integration, Android image, KernelSU work, migration, main change, merge, force-push, tag or release occurred. [Reproduction instructions](REPRODUCE.md) and [bounded next actions](NEXT.md) restore a reviewable development checkpoint without weakening these gates.
