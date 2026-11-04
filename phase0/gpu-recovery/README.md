# Phase 0.6 — GPU foundation recovery

**NO-GO for guest-visible QEMU/Rutabaga Windows integration.** Native tooling, the upstream fence overlay and Gfxstream host composition now execute, but independent tracing/control and critical integrated memory/ownership qualification remain open. No full migration or Android image build.

Read the [technical report](REPORT.md), [exact reproduction instructions](REPRODUCE.md), [source-linked compatibility matrix](COMPATIBILITY.md), [security/licensing review](SECURITY-LICENSES.md) and [next bounded tickets](NEXT.md). Review remains on [Draft PR #1](https://github.com/Lord1Egypt/DragonLord-Emulator/pull/1), branch `phase0/architecture-feasibility`. Starting reviewed commit: `6c1a0604dcfc63d7efa84fea73b065d9aa8920b5`; CI/fence milestone: `7904adf57c39288bd0b157c6f1d34bbd489c9dbc`.

| Acceptance | Outcome |
|---|---|
| Modern CI | PASS at first recovery milestone; final revision checked separately |
| Upstream context-ID fence correction | PASS: corrected 26 historical +12 extended; original failures retained |
| Native Gfxstream compilation | PASS with isolated, hashed build overlays |
| Actual hardware rendering | PASS for host-only Gfxstream Vulkan compositor on RTX 2060 |
| Independent GPU verification | FAIL: software counter control invalid; ETW access denied |
| Rutabaga FFI/ABI | BLOCKED overall; corrected-header boundary/core tests PASS |
| QEMU Windows integration | BLOCKED, not attempted |
| Integrated shared-memory/fence lifecycle | NOT TESTED; standalone reference tests PASS |

Raw logs, commands, exit codes, source/binary hashes, Cargo locks and earlier failures live in [evidence](evidence/). Large full logs use lossless gzip with raw-byte SHA256 metadata. No binaries/tool archives/drivers/VM disks are published. [Index](evidence/index.json) covers the package excluding itself; old Phase 0/0.5 evidence is unchanged. Reported evidence is not owner attestation.

```sh
python3 phase0/gpu-recovery/tools/verify-evidence.py --include-recovery
python3 -m unittest discover -s phase0/gpu-recovery/tests -v
```

The GPU qualifier deliberately returns failure when independent control evidence is invalid; a green harness test job does not turn that engineering failure into GPU PASS. Hosted modern CI and manual legacy build remain separate. Legacy dependency setup now passes, but legacy configure still fails on Python `pwd` and has no compilation PASS.
