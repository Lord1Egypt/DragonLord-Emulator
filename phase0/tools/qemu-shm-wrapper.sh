#!/bin/bash
# Stand-in for qemu-system-x86_64 that Cuttlefish launches. Puts guest RAM in /dev/shm instead of a
# disk file (the file-backed 4 GB RAM plus prealloc causes heavy disk I/O on WSL). With DL_NET=user the tap netdevs
# become user-mode networking (no root TAP setup). All else passes through.
REAL=${DL_QEMU_REAL:-$(cd "$(dirname "$0")/../../qemu-build-gpu" && pwd)/qemu-system-x86_64}  # installed in .work/cuttlefish/qemu-ours
args=()
for a in "$@"; do
  if [[ $a == memory-backend-file,*mem-path=*qemu.mem* ]]; then
    a=$(sed -E "s#mem-path=[^,]*qemu\.mem#mem-path=${DL_MEM_PATH:-/dev/shm/dragonlord-cvd-1.mem}#" <<<"$a")
  fi
  # DL_NET=user: replace Cuttlefish's root-created TAP devices with QEMU user-mode (slirp) networking
  if [[ ${DL_NET:-tap} == user && $a == tap,id=hostnet* ]]; then
    a="user,id=$(sed -E 's/^tap,id=([^,]+).*/\1/' <<<"$a")"
  fi
  args+=("$a")
done
# DL_TOUCH_SOCK: vhost-user touchscreen served by dlvm (cf_vhost_user_input), fed by the panel's browser view
if [[ -n ${DL_TOUCH_SOCK:-} ]]; then
  args+=(-chardev "socket,id=dltouch,path=$DL_TOUCH_SOCK" -device vhost-user-input-pci,chardev=dltouch)
fi
exec "$REAL" "${args[@]}"
