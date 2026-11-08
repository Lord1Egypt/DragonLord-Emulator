#!/bin/bash
# Build the opt-in KernelSU profile: patch the stock init_boot.img with KernelSU's LKM (no kernel rebuild).
# Inputs (from github.com/tiann/KernelSU release v3.3.1, see ANDROID17-WSL-RUNBOOK.md) live in phase0/.work/kernelsu.
# The stock init_boot.img is never modified; boot the result with launch_cvd -init_boot_image=<out>.
set -euo pipefail
K="$(cd "$(dirname "$0")/.." && pwd)/.work/kernelsu"
STOCK="${1:-$K/../cuttlefish/cvd/init_boot.img}"
mkdir -p "$K/out"
sha256sum "$STOCK" > "$K/out/stock_init_boot.sha256"
"$K/ksud-x86_64-unknown-linux-musl" boot-patch -b "$STOCK" \
  -m "$K/lkm-x86_64-android16-6.12_kernelsu.ko" -i "$K/ksuinit-x86_64" \
  --arch x86_64 --kmi android16-6.12 -o "$K/out" --out-name init_boot_ksu.img
echo "patched image: $K/out/init_boot_ksu.img"
