#!/bin/bash
# DragonLord Linux/WSL edition: install our wrappers into the unpacked Cuttlefish tree (idempotent, no root).
# Prerequisites (see ANDROID17-WSL-RUNBOOK.md): Android image + host package unpacked in .work/cuttlefish/cvd,
# our QEMU built in .work/qemu-build-gpu. Run tools/dl-doctor.py afterwards.
set -euo pipefail
P="$(cd "$(dirname "$0")/.." && pwd)"
CVD="$P/.work/cuttlefish/cvd"
[ -x "$CVD/bin/launch_cvd" ] || { echo "missing $CVD/bin/launch_cvd: unpack the Cuttlefish host package and image first" >&2; exit 1; }
mkdir -p "$P/.work/cuttlefish/qemu-ours"
install -m 755 "$P/tools/qemu-shm-wrapper.sh" "$P/.work/cuttlefish/qemu-ours/qemu-system-x86_64"
if [ ! -e "$CVD/bin/run_cvd.real" ]; then
  mv "$CVD/bin/run_cvd" "$CVD/bin/run_cvd.real"
fi
install -m 755 "$P/tools/run-cvd-wrapper.sh" "$CVD/bin/run_cvd"
echo "wrappers installed"
python3 "$P/tools/dl-doctor.py"
