#!/usr/bin/env python3
"""Answers Cuttlefish's host capability check (it runs /usr/lib/cuttlefish-common/bin/capability_query.py).

Without the cuttlefish-common package installed, launch_cvd refuses -vm_manager=qemu_cli. DragonLord needs only
these capabilities; `dragonlord setup` prints the one-time sudo command that installs this file there.
"""
import sys

CAPABILITIES = {"capability_check", "qemu_cli", "vsock"}

if len(sys.argv) == 1:
    print("\n".join(sorted(CAPABILITIES)))
else:
    sys.exit(len(set(sys.argv[1:]) - CAPABILITIES))
