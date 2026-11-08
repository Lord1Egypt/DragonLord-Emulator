#!/bin/bash
# Build the Linux/WSL release folder and archive:  phase0/release/make-release.sh VERSION
# Input: the lean QEMU build in phase0/.work/qemu-build-release (configure line in release/NOTICE.md).
# Output: phase0/.work/dist/dragonlord-VERSION-linux-x86_64/ and .tar.gz (+ .sha256).
set -euo pipefail
VERSION="${1:?usage: make-release.sh VERSION}"
P="$(cd "$(dirname "$0")/.." && pwd)"
QEMU="$P/.work/qemu-build-release/qemu-system-x86_64"
NAME="dragonlord-$VERSION-linux-x86_64"
OUT="$P/.work/dist/$NAME"
[ -x "$QEMU" ] || { echo "missing $QEMU (build it first, see release/NOTICE.md)" >&2; exit 1; }
rm -rf "$OUT" "$OUT.tar.gz"
mkdir -p "$OUT"/{tools,qemu/bin,qemu/lib,qemu/wrapper}

install -m 755 "$P/release/dragonlord" "$OUT/dragonlord"
cp "$P/release/README.md" "$P/release/NOTICE.md" "$OUT/"
echo "DragonLord $VERSION (Linux/WSL edition), Android 17 Cuttlefish build 16644040, QEMU 11.1.3" > "$OUT/RELEASE"
for f in dlvm.py dlui.py dlui.html dlview.html dlpaths.py dl-install.py dl-doctor.py gapps-prepare.py capability_query.py; do
  install -m 644 "$P/tools/$f" "$OUT/tools/$f"
done
chmod 755 "$OUT"/tools/*.py
for f in ksu-patch.sh run-cvd-wrapper.sh; do install -m 755 "$P/tools/$f" "$OUT/tools/$f"; done
install -m 755 "$P/tools/qemu-shm-wrapper.sh" "$OUT/qemu/wrapper/qemu-system-x86_64"

install -m 755 "$QEMU" "$OUT/qemu/bin/qemu-system-x86_64"
strip --strip-unneeded "$OUT/qemu/bin/qemu-system-x86_64"
# bundle every library QEMU needs except glibc's own (those must come from the system)
ldd "$QEMU" | awk '$3 ~ /^\// {print $3}' | while read -r lib; do
  case "$(basename "$lib")" in
    libc.so*|libm.so*|libpthread.so*|libdl.so*|librt.so*|ld-linux*|libgcc_s.so*) continue ;;
  esac
  cp -L "$lib" "$OUT/qemu/lib/$(basename "$lib")"
done
cp "$P/../COPYING" "$OUT/LICENSE-QEMU-GPLv2"

# smoke test from the new folder: QEMU starts with only bundled libraries + glibc
LD_LIBRARY_PATH="$OUT/qemu/lib" "$OUT/qemu/bin/qemu-system-x86_64" --version | head -1
if LD_LIBRARY_PATH="$OUT/qemu/lib" ldd "$OUT/qemu/bin/qemu-system-x86_64" | grep "not found"; then
  echo "unresolved libraries" >&2
  exit 1
fi

tar -C "$(dirname "$OUT")" -czf "$OUT.tar.gz" "$NAME"
(cd "$(dirname "$OUT")" && sha256sum "$NAME.tar.gz" > "$NAME.tar.gz.sha256")
ls -la "$OUT.tar.gz"; cat "$OUT.tar.gz.sha256"
