#!/bin/bash
# Stand-in for qemu-system-x86_64 that Cuttlefish launches. Puts guest RAM in /dev/shm instead of a
# disk file (the file-backed 4 GB RAM plus prealloc causes heavy disk I/O on WSL); all else passes through.
REAL=/home/lordegypt/DragonLord/DragonLord-Emulator/phase0/.work/qemu-build-gpu/qemu-system-x86_64
args=()
for a in "$@"; do
  if [[ $a == memory-backend-file,*mem-path=*qemu.mem* ]]; then
    a=$(sed -E "s#mem-path=[^,]*qemu\.mem#mem-path=${DL_MEM_PATH:-/dev/shm/dragonlord-cvd-1.mem}#" <<<"$a")
  fi
  args+=("$a")
done
exec "$REAL" "${args[@]}"
