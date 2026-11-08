#!/bin/bash
# Installed as cvd/bin/run_cvd (real binary renamed run_cvd.real).
# assemble_cvd leaves ril_* empty when no host network bridge exists, so the simulated modem hands the
# guest no address and Android never brings up mobile data. Fill in QEMU user-mode (slirp) values first.
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ "${DL_NET:-}" = "user" ]; then
  for f in "$HOME"/cuttlefish/assembly/cuttlefish_config.json "$HOME"/cuttlefish/instances/cvd-*/cuttlefish_config.json; do
    [ -f "$f" ] || continue
    sed -i -e 's|"ril_broadcast" : "[^"]*"|"ril_broadcast" : "10.0.2.255"|' \
           -e 's|"ril_dns" : "[^"]*"|"ril_dns" : "10.0.2.3"|' \
           -e 's|"ril_gateway" : "[^"]*"|"ril_gateway" : "10.0.2.2"|' \
           -e 's|"ril_ipaddr" : "[^"]*"|"ril_ipaddr" : "10.0.2.15"|' \
           -e 's|"ril_prefixlen" : [0-9]*|"ril_prefixlen" : 24|' "$f"
  done
fi
exec "$DIR/run_cvd.real" "$@"
