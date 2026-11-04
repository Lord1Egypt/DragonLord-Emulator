#!/usr/bin/env python3
"""Strict CPU/serial boot gate. A passing diagnostic never qualifies Android or GPU."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import select
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

PHASE = Path(__file__).resolve().parents[1]
LOCK = json.loads((PHASE / "versions.lock.json").read_text())

def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")

def verified_download(url, expected, path):
    path = Path(path)
    if path.exists() and digest(path) == expected:
        return
    temp = path.with_name(path.name + ".part")
    try:
        with urllib.request.urlopen(url, timeout=60) as source, temp.open("wb") as dest:
            shutil.copyfileobj(source, dest)
        if digest(temp) != expected:
            raise ValueError("SHA256 mismatch for " + url)
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()

def fetch_assets():
    assets = PHASE / ".work/assets"
    assets.mkdir(parents=True, exist_ok=True)
    for key, filename in (("kernel", "bzImage"), ("rootfs", "rootfs.ext4.zst")):
        spec = LOCK["diagnostic_guest"][key]
        verified_download(spec["url"], spec["sha256"], assets / filename)
    import zstandard  # installed by bootstrap-linux.py; no import needed for other commands
    raw = assets / "rootfs.ext4"
    temp = assets / "rootfs.ext4.part"
    with (assets / "rootfs.ext4.zst").open("rb") as src, temp.open("wb") as dest:
        zstandard.ZstdDecompressor().copy_stream(src, dest)
    temp.replace(raw)
    write_json(assets / "manifest.json", {"kernel_sha256": digest(assets / "bzImage"),
                                         "rootfs_sha256": digest(raw),
                                         "compressed_rootfs_sha256": digest(assets / "rootfs.ext4.zst")})
    print("Fetched and checksum-verified upstream QEMU diagnostic assets.")

def inventory():
    return {"timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "platform": platform.system(), "release": platform.release(),
            "machine": platform.machine(), "logical_cpu_count": os.cpu_count(),
            "device_access": {p: {"exists": Path(p).exists(), "read_write": os.access(p, os.R_OK | os.W_OK)}
                              for p in ("/dev/kvm", "/dev/dri", "/dev/dxg")},
            "tools": {p: shutil.which(p) for p in ("cc", "make", "pkg-config", "adb", "vulkaninfo", "powershell.exe")}}

def accelerator_blocker(accel, host=None, kvm_access=None):
    host = platform.system() if host is None else host
    if accel == "whpx" and host != "Windows":
        return "Native Windows WHPX execution unavailable in this process; WSL is not a WHPX test host"
    if accel == "kvm":
        accessible = os.access("/dev/kvm", os.R_OK | os.W_OK) if kvm_access is None else kvm_access
        if host != "Linux" or not accessible:
            return "Linux /dev/kvm read/write access unavailable"
    return None

def boot_argv(qemu, accel, kernel, disk, serial_port, qmp_port, bios):
    # Exactly one accelerator. Never add software fallback to a hardware gate.
    escaped_disk = str(disk).replace(",", ",,")
    command = [str(qemu), "-machine", "pc-q35-11.1", "-accel", accel, "-cpu", "Nehalem",
               "-smp", "2", "-m", "1024", "-display", "none", "-monitor", "none",
               "-nic", "none", "-no-reboot", "-kernel", str(kernel),
               "-append", "root=/dev/sda console=ttyS0 panic=-1",
               "-drive", f"file={escaped_disk},format=raw,if=none,id=phase0disk,snapshot=on",
               "-device", "ide-hd,drive=phase0disk,bus=ide.0,unit=0",
               "-serial", f"tcp:127.0.0.1:{serial_port},server=on,wait=off",
               "-qmp", f"tcp:127.0.0.1:{qmp_port},server=on,wait=off"]
    if bios:
        command += ["-L", str(bios)]
    return command

def unused_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def connect(port, process, deadline):
    while time.monotonic() < deadline:
        try:
            return socket.create_connection(("127.0.0.1", port), timeout=1)
        except OSError:
            if process.poll() is not None:
                raise RuntimeError("QEMU exited before opening its console; inspect qemu.log")
            time.sleep(0.1)
    raise TimeoutError("Console connection timeout")

def qmp_rpc(stream, command, ident):
    stream.write((json.dumps({"execute": command, "id": ident}) + "\n").encode())
    stream.flush()
    while True:
        line = stream.readline()
        if not line:
            raise RuntimeError("QMP disconnected")
        response = json.loads(line)
        if response.get("id") == ident:
            if "error" in response:
                raise RuntimeError(str(response["error"]))
            return response["return"]

def ready_evidence(console, marker):
    return ("Linux version " in console and "tuxtest login:" in console
            and re.search(re.escape(marker) + r"\r?\nx86_64(?:\r?\n|$)", console) is not None
            and "Kernel panic - not syncing" not in console)

def smoke(args):
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    result = {"schema": 1, "scope": "Linux diagnostic boot only", "status": "BLOCKED",
              "accelerator": args.accel, "hardware": inventory(),
              "android16": "NOT_TESTED", "gpu": "NOT_TESTED", "kernelsu": "NOT_TESTED"}
    blocked = accelerator_blocker(args.accel)
    if blocked:
        result["reason"] = blocked
        write_json(out / "result.json", result)
        print(json.dumps(result, indent=2))
        return 2
    qemu = Path(args.qemu).resolve()
    assets = PHASE / ".work/assets"
    missing = [str(p) for p in (qemu, assets / "bzImage", assets / "rootfs.ext4", assets / "manifest.json") if not p.is_file()]
    if missing:
        result["reason"] = "Required artifacts missing: " + ", ".join(missing)
        write_json(out / "result.json", result)
        print(json.dumps(result, indent=2))
        return 2
    process = None
    qmp_stream = None
    serial = None
    qmp_socket = None
    try:
        manifest = json.loads((assets / "manifest.json").read_text())
        if digest(assets / "bzImage") != LOCK["diagnostic_guest"]["kernel"]["sha256"]:
            raise ValueError("Kernel checksum mismatch")
        before = digest(assets / "rootfs.ext4")
        if before != manifest["rootfs_sha256"]:
            raise ValueError("Rootfs checksum mismatch; fetch verified assets again")
        version = subprocess.check_output([str(qemu), "--version"], text=True, timeout=15)
        if not version.startswith("QEMU emulator version " + LOCK["qemu"]["version"] + " "):
            raise ValueError("Unexpected QEMU version: " + version.splitlines()[0])
        accel_help = subprocess.check_output([str(qemu), "-accel", "help"], text=True, timeout=15)
        if args.accel not in accel_help.split():
            result.update(status="BLOCKED", reason="QEMU binary does not advertise requested accelerator")
            write_json(out / "result.json", result)
            print(json.dumps(result, indent=2))
            return 2
        serial_port, qmp_port = unused_port(), unused_port()
        while qmp_port == serial_port:
            qmp_port = unused_port()
        command = boot_argv(qemu, args.accel, assets / "bzImage", assets / "rootfs.ext4",
                            serial_port, qmp_port, args.bios_dir)
        result.update(argv=command, qemu_sha256=digest(qemu), qemu_version=version,
                      kernel_sha256=digest(assets / "bzImage"), rootfs_sha256=before)
        start = time.monotonic()
        deadline = start + args.timeout
        child_env = os.environ.copy()
        temp_dir = out / "tmp"
        temp_dir.mkdir(exist_ok=True)
        for name in ("TMPDIR", "TMP", "TEMP"):
            child_env[name] = str(temp_dir)
        with (out / "qemu.log").open("wb") as log:
            process = subprocess.Popen(command, env=child_env, stdout=log, stderr=subprocess.STDOUT)
            serial = connect(serial_port, process, min(deadline, start + 20))
            qmp_socket = connect(qmp_port, process, min(deadline, start + 20))
            qmp_socket.settimeout(10)
            qmp_stream = qmp_socket.makefile("rwb")
            greeting = json.loads(qmp_stream.readline())
            qmp_rpc(qmp_stream, "qmp_capabilities", 1)
            status = qmp_rpc(qmp_stream, "query-status", 2)
            qmp_evidence = {"greeting": greeting, "status": status}
            if args.accel == "kvm":
                kvm = qmp_rpc(qmp_stream, "query-kvm", 3)
                qmp_evidence["kvm"] = kvm
                if not kvm.get("enabled"):
                    raise RuntimeError("QMP reports KVM is not active")
            write_json(out / "qmp.json", qmp_evidence)
            nonce = secrets.token_hex(8)
            marker = "PHASE0_READY_" + nonce
            console = ""
            logged_in = sent_probe = False
            with (out / "serial.log").open("wb") as serial_log:
                while time.monotonic() < deadline:
                    readable, _, _ = select.select([serial], [], [], min(1, max(0, deadline-time.monotonic())))
                    if readable:
                        block = serial.recv(65536)
                        if not block:
                            raise RuntimeError("Guest console disconnected")
                        serial_log.write(block)
                        serial_log.flush()
                        console += block.decode(errors="replace")
                        if "Kernel panic - not syncing" in console:
                            raise RuntimeError("Guest kernel panic")
                        if "tuxtest login:" in console and not logged_in:
                            serial.sendall(b"root\n")
                            logged_in = True
                        if "root@tuxtest:~#" in console and not sent_probe:
                            # Keep the readiness token absent from the echoed input command.
                            serial.sendall(("printf 'PHASE0_'; printf 'READY_" + nonce + "\\n'; uname -m; uname -r\n").encode())
                            sent_probe = True
                        if ready_evidence(console, marker):
                            result["process_to_guest_ready_seconds"] = time.monotonic() - start
                            serial.sendall(b"halt\n")
                            # This is a short boot gate, not a stability or shutdown qualification.
                            qmp_rpc(qmp_stream, "quit", 4)
                            process.wait(timeout=15)
                            if process.returncode != 0:
                                raise RuntimeError("QEMU did not exit cleanly")
                            if digest(assets / "rootfs.ext4") != before:
                                raise RuntimeError("Base root filesystem changed")
                            result.update(status="PASS", reason="Guest logged in and executed a fresh readiness nonce; QMP quit clean; base disk unchanged")
                            break
                    if process.poll() is not None:
                        raise RuntimeError("QEMU exited before guest readiness")
                else:
                    raise TimeoutError("Guest did not become ready before timeout")
    except (OSError, ValueError, RuntimeError, TimeoutError, subprocess.SubprocessError) as exc:
        result.update(status="FAIL", reason=str(exc))
    finally:
        for stream in (qmp_stream, serial, qmp_socket):
            if stream is not None:
                stream.close()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
    write_json(out / "result.json", result)
    print(json.dumps(result, indent=2))
    return {"PASS": 0, "BLOCKED": 2, "FAIL": 1}[result["status"]]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("fetch-assets")
    host = sub.add_parser("inventory")
    host.add_argument("--output", required=True)
    run = sub.add_parser("boot")
    run.add_argument("--qemu", required=True)
    run.add_argument("--accel", choices=("tcg", "kvm", "whpx"), required=True)
    run.add_argument("--bios-dir")
    run.add_argument("--timeout", type=float, default=180)
    run.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.action == "fetch-assets":
        fetch_assets()
    elif args.action == "inventory":
        write_json(args.output, inventory())
    elif args.timeout <= 0:
        parser.error("timeout must be positive")
    else:
        return smoke(args)
    return 0

if __name__ == "__main__":
    sys.exit(main())
