#!/usr/bin/env python3
"""DragonLord instance manager UI: first-run wizard + instance list, served on 127.0.0.1 only.

  dlui.py [--port 8765]      then open the printed URL (it contains a per-run access token)

Thin layer over dlvm.py: every action calls the same functions as the CLI, so limits and name checks live in one place.
"""
import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import secrets
import socket
import struct
import subprocess
import sys
import termios
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dlvm  # noqa: E402



def load_token():
    """Reuse one token across restarts so bookmarked links keep working; the file is private to the user."""
    f = dlvm.ROOT.parent / "ui-token"
    try:
        t = f.read_text().strip()
        if len(t) >= 32:
            return t
    except OSError:
        pass
    t = secrets.token_urlsafe(24)
    f.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(t + "\n")
    return t


TOKEN = load_token()
BUSY = {}  # instance name -> "starting" | "stopping"
LOCK = threading.Lock()
PAGE = (Path(__file__).resolve().parent / "dlui.html").read_text()
VIEW = (Path(__file__).resolve().parent / "dlview.html").read_text()


def ns(**kw):
    return argparse.Namespace(**kw)


def list_instances():
    out = []
    for p in sorted(dlvm.ROOT.glob("*/instance.json")):
        c = dlvm.load(p.parent.name)
        c["running"] = dlvm.running(c)
        c["busy"] = BUSY.get(c["name"])
        c["adb"] = dlvm.adb_serial(c)
        out.append(c)
    return out


def intval(d, key, default):
    v = d.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise ValueError(f"{key} must be a number")
    try:
        return int(v)
    except ValueError:
        raise ValueError(f"{key} must be a number")


def do_create(d):
    name = str(d.get("name", ""))
    serial = str(d.get("serial") or "") or None
    if serial and not dlvm.re.fullmatch(r"[A-Za-z0-9_-]{4,32}", serial):
        raise ValueError("serial: 4-32 letters, digits, - or _")
    gpu, root = d.get("gpu", "gfxstream"), d.get("root", "off")
    if gpu not in ("gfxstream", "software") or root not in ("off", "ksu"):
        raise ValueError("gpu or root value not allowed")
    dlvm.cmd_create(ns(name=name, ram=intval(d, "ram", 4096), cpus=intval(d, "cpus", 4), disk=intval(d, "disk", 8192),
                       gpu=gpu, root=root, serial=serial, dpi=intval(d, "dpi", 320), res=str(d.get("res", "720x1280")),
                       extra=None, imei=str(d.get("imei") or "") or None,
                       gapps=d.get("gapps") is True))


SCRCPY = Path(__file__).resolve().parents[1] / ".work/scrcpy/win64/scrcpy-win64-v5.0.1"


def show_screen(cfg):
    """Open a scrcpy window (Windows build, run through WSL interop) mirroring the instance with mouse and keyboard."""
    try:
        socket.create_connection(("127.0.0.1", 6520 + cfg["number"] - 1), timeout=2).close()
    except OSError:
        raise ValueError(f"{cfg['name']} has not finished booting yet (adb port is closed); wait until the state says running")
    exe = SCRCPY / "scrcpy.exe"
    if not exe.exists():
        raise ValueError(f"scrcpy not found at {SCRCPY}")
    win = subprocess.run(["wslpath", "-w", str(exe)], capture_output=True, text=True, check=True).stdout.strip()
    args = (f"'--tcpip={dlvm.adb_serial(cfg)}','--window-title={cfg['name']}','--no-audio','--force-adb-forward',"
            "'--video-encoder=c2.android.avc.encoder'")  # name is [A-Za-z0-9_-] only; no audio capture on the virtual device
    subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", f"Start-Process -FilePath '{win}' -ArgumentList {args}"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


KEYS = {"home": 3, "back": 4, "recents": 187, "power": 26, "volup": 24, "voldown": 25, "enter": 66, "del": 67, "tab": 61}
TEXT_OK = re.compile(r"[A-Za-z0-9 ._@-]{1,100}")


def adb_cmd(cfg, *args):
    return ["adb", "-s", dlvm.adb_serial(cfg), *args]


def coord(d, key, limit=5000):
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= limit:
        raise ValueError(f"{key} out of range")
    return str(int(v))


def do_input(cfg, d):
    """Inject one input event. adb joins its arguments into one shell command, so every value is whitelisted or numeric."""
    kind = d.get("type")
    if kind == "tap":
        shell = f"input tap {coord(d, 'x')} {coord(d, 'y')}"
    elif kind == "swipe":
        shell = f"input swipe {coord(d, 'x')} {coord(d, 'y')} {coord(d, 'x2')} {coord(d, 'y2')} {coord(d, 'ms', 5000)}"
    elif kind == "key":
        if d.get("key") not in KEYS:
            raise ValueError("unknown key")
        shell = f"input keyevent {KEYS[d['key']]}"
    elif kind == "text":
        t = d.get("text")
        if not isinstance(t, str) or not TEXT_OK.fullmatch(t):
            raise ValueError("text: letters, digits, space and . _ @ - only (max 100)")
        shell = "input text " + t.replace(" ", "%s")
    else:
        raise ValueError("unknown input type")
    subprocess.run(adb_cmd(cfg, "shell", shell), capture_output=True, timeout=15)


def do_touch(cfg, d):
    """Write virtio input events for a batch of touch steps into the instance's touchscreen FIFO (see dlvm.start_touch)."""
    steps = d.get("steps")
    if not isinstance(steps, list) or not 0 < len(steps) <= 200:
        raise ValueError("steps: 1-200 items")
    w, h = (int(v) for v in cfg["res"].split("x"))
    groups = []
    ev = lambda t, c, v: struct.pack("<HHi", t, c, v)
    for st in steps:
        out = b""
        if not isinstance(st, dict) or st.get("t") not in ("down", "move", "up"):
            raise ValueError("step t must be down, move or up")
        if st["t"] != "up":
            out += ev(3, 0, int(coord(st, "x", w - 1))) + ev(3, 1, int(coord(st, "y", h - 1)))
        if st["t"] == "down":
            out += ev(1, 330, 1)
        elif st["t"] == "up":
            out += ev(1, 330, 0)
        groups.append(out + ev(0, 0, 0))
    if not cfg.get("touch_pid"):
        raise ValueError("this instance has no touchscreen (start it again to add one)")
    try:
        fd = os.open(dlvm.touch_fifo(cfg), os.O_WRONLY | os.O_NONBLOCK)
    except OSError:
        raise ValueError("touchscreen not available")
    def drained(limit=0.1):  # bytes still in the FIFO, readable from the write end too
        end = time.time() + limit
        while struct.unpack("i", fcntl.ioctl(fd, termios.FIONREAD, b"\0\0\0\0"))[0] and time.time() < end:
            time.sleep(0.001)
    try:
        # cf_vhost_user_input forwards only the first SYN-terminated group of each read and keeps the rest until the
        # next read, so two groups in the FIFO at once leave one stuck (a touch that never lifts). Fixed delays failed
        # under load; instead each group is written only after the daemon has taken the previous one.
        for g in groups:
            drained()
            os.write(fd, g)
        drained()
    finally:
        os.close(fd)


FILE_OK = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._ -]{0,99}")  # also the shell-safety rule for guest paths
GUEST_DIR = "/sdcard/Download"
MAX_UPLOAD = 4 * 2**30


def guest_file(name):
    if not isinstance(name, str) or not FILE_OK.fullmatch(name) or ".." in name:
        raise ValueError("file name: letters, digits, space and . _ - only (max 100)")
    return name


def list_files(cfg):
    out = subprocess.run(adb_cmd(cfg, "shell", f"ls -p {GUEST_DIR}"), capture_output=True, text=True, timeout=30).stdout
    return [f for f in out.splitlines() if f and not f.endswith("/") and FILE_OK.fullmatch(f)]


def background(name, verb, fn):
    with LOCK:
        # a boot in progress can always be cancelled by stop/delete; everything else waits for the current action
        if name in BUSY and not (BUSY[name] == "starting" and verb == "stopping"):
            raise ValueError(f"{name} is {BUSY[name]}")
        BUSY[name] = verb

    def run():
        try:
            fn()
        except SystemExit as e:
            print(f"{name}: {verb} failed: {e}", file=sys.stderr)
        finally:
            if BUSY.get(name) == verb:
                BUSY.pop(name, None)
    threading.Thread(target=run, daemon=True).start()


class H(BaseHTTPRequestHandler):
    server_version = "dlui"

    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        port = self.server.server_address[1]  # 'self' does not cover ws: in every browser engine
        self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'; "
                         f"connect-src 'self' ws://127.0.0.1:{port} ws://localhost:{port}")
        self.end_headers()
        self.wfile.write(data)

    def authorised(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):  # blocks DNS-rebinding
            return False
        given = self.headers.get("X-DL-Token") or parse_qs(urlparse(self.path).query).get("t", [""])[0]
        return secrets.compare_digest(given, TOKEN)

    def do_GET(self):
        if not self.authorised():
            return self.send(403, '{"error":"forbidden"}')
        path = urlparse(self.path).path
        if path == "/":
            return self.send(200, PAGE.replace("__TOKEN__", TOKEN), "text/html; charset=utf-8")
        if path == "/api/instances":
            return self.send(200, json.dumps(list_instances()))
        if path in ("/api/files", "/api/pull"):
            q = parse_qs(urlparse(self.path).query)
            if path == "/api/pull":
                return self.pull(q.get("name", [""])[0], q.get("file", [""])[0])
            try:
                cfg = dlvm.load(q.get("name", [""])[0])
            except SystemExit as e:
                return self.send(400, json.dumps({"error": str(e)}))
            return self.send(200, json.dumps(list_files(cfg) if dlvm.running(cfg) else []))
        if path == "/api/vnc":
            return self.vnc(parse_qs(urlparse(self.path).query).get("name", [""])[0])
        if path == "/view":
            return self.send(200, VIEW.replace("__TOKEN__", TOKEN), "text/html; charset=utf-8")
        if path == "/api/stream":
            q = parse_qs(urlparse(self.path).query)
            return self.stream(q.get("name", [""])[0], q.get("q", ["75"])[0])
        self.send(404, '{"error":"not found"}')

    def stream(self, name, quality):
        """Raw H.264 (Annex B) from the guest's screenrecord, restarted when its 3-minute limit ends."""
        try:
            cfg = dlvm.load(name)
        except SystemExit as e:
            return self.send(400, json.dumps({"error": str(e)}))
        if not dlvm.running(cfg):
            return self.send(400, '{"error":"not running"}')
        pct = {"100": 100, "75": 75, "50": 50}.get(quality)
        if not pct:
            return self.send(400, '{"error":"quality must be 100, 75 or 50"}')
        w, h = (int(v) * pct // 100 // 2 * 2 for v in cfg["res"].split("x"))  # the software encoder is the bottleneck
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while dlvm.running(dlvm.load(name)):
                p = subprocess.Popen(adb_cmd(cfg, "exec-out", "screenrecord", "--output-format=h264", "--time-limit", "180",
                                             "--bit-rate", "4000000", "--size", f"{w}x{h}", "-"),
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                try:
                    while True:
                        chunk = p.stdout.read1(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
                finally:
                    p.kill()
                    p.wait()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def upload(self):
        """Raw file body. action=install runs adb install (APK); action=push copies it to the guest's Download folder."""
        try:
            q = parse_qs(urlparse(self.path).query)
            cfg = dlvm.load(q.get("name", [""])[0])
            if not dlvm.running(cfg):
                raise ValueError("not running")
            fname, action = guest_file(q.get("file", [""])[0]), q.get("action", [""])[0]
            if action not in ("install", "push") or (action == "install" and not fname.lower().endswith(".apk")):
                raise ValueError("action must be install (.apk) or push")
            n = int(self.headers.get("Content-Length") or -1)
            if not 0 < n <= MAX_UPLOAD:
                raise ValueError("file must be 1 byte to 4 GB")
            tmp_dir = dlvm.inst_dir(cfg["name"]) / "uploads"
            tmp_dir.mkdir(exist_ok=True)
            tmp = tmp_dir / f"{secrets.token_hex(8)}-{fname}"
            try:
                with open(tmp, "wb") as f:
                    left = n
                    while left:
                        chunk = self.rfile.read(min(left, 1 << 20))
                        if not chunk:
                            raise ValueError("upload interrupted")
                        f.write(chunk)
                        left -= len(chunk)
                if action == "install":
                    r = subprocess.run(adb_cmd(cfg, "install", "-r", str(tmp)), capture_output=True, text=True, timeout=600)
                else:
                    r = subprocess.run(adb_cmd(cfg, "push", str(tmp), f"{GUEST_DIR}/{fname}"), capture_output=True, text=True, timeout=600)
            finally:
                tmp.unlink(missing_ok=True)
            out = (r.stdout + r.stderr).strip().splitlines()
            if r.returncode != 0 or (action == "install" and not any("Success" in l for l in out)):
                raise ValueError(f"{action} failed: {out[-1] if out else r.returncode}")
            self.send(200, json.dumps({"ok": True, "result": out[-1] if out else ""}))
        except SystemExit as e:
            self.send(400, json.dumps({"error": str(e)}))
        except (ValueError, OSError, subprocess.TimeoutExpired) as e:
            self.send(400, json.dumps({"error": str(e)}))

    def pull(self, name, fname):
        try:
            cfg = dlvm.load(name)
            fname = guest_file(fname)
        except (SystemExit, ValueError) as e:
            return self.send(400, json.dumps({"error": str(e)}))
        p = subprocess.Popen(adb_cmd(cfg, "exec-out", f"cat '{GUEST_DIR}/{fname}'"), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
        self.end_headers()
        try:
            while chunk := p.stdout.read1(1 << 20):
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            p.kill()
            p.wait()

    def vnc(self, name):
        """WebSocket tunnel to the instance's QEMU VNC server (127.0.0.1, 6443 + instance number).

        QEMU's own WebSocket listener has no authentication and any web page could reach it, so the browser only
        talks to this authorised endpoint; the Origin check stops other sites from using a leaked token."""
        try:
            cfg = dlvm.load(name)
        except SystemExit as e:
            return self.send(400, json.dumps({"error": str(e)}))
        port = self.server.server_address[1]
        if self.headers.get("Origin") not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            return self.send(403, '{"error":"bad origin"}')
        key = self.headers.get("Sec-WebSocket-Key")
        if (self.headers.get("Upgrade") or "").lower() != "websocket" or not key or not dlvm.running(cfg):
            return self.send(400, '{"error":"websocket upgrade to a running instance required"}')
        try:
            up = socket.create_connection(("127.0.0.1", 6443 + cfg["number"]), timeout=5)
        except OSError:
            return self.send(503, '{"error":"VNC not reachable yet"}')
        up.settimeout(None)
        for sock in (up, self.connection):  # small RFB requests must not wait for Nagle's algorithm
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.protocol_version = "HTTP/1.1"  # browsers reject a WebSocket upgrade answered as HTTP/1.0
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        self.wfile.flush()
        conn, lock = self.connection, threading.Lock()

        def frame(opcode, data):
            n = len(data)
            head = bytes([0x80 | opcode]) + (bytes([n]) if n < 126 else
                                             bytes([126]) + n.to_bytes(2, "big") if n < 65536 else
                                             bytes([127]) + n.to_bytes(8, "big"))
            with lock:
                conn.sendall(head + data)

        def pump():  # VNC server -> browser
            try:
                while data := up.recv(1 << 20):
                    frame(2, data)
            except OSError:
                pass
            finally:
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        threading.Thread(target=pump, daemon=True).start()
        r = self.rfile
        try:
            while True:  # browser -> VNC server; RFC 6455 client frames are always masked
                h = r.read(2)
                if len(h) < 2:
                    break
                op, n = h[0] & 0x0F, h[1] & 0x7F
                if n == 126:
                    n = int.from_bytes(r.read(2), "big")
                elif n == 127:
                    n = int.from_bytes(r.read(8), "big")
                if not h[1] & 0x80 or n > 1 << 20:
                    break
                mask = r.read(4)
                data = r.read(n)
                data = (int.from_bytes(data, "big") ^ int.from_bytes((mask * (n // 4 + 1))[:n], "big")).to_bytes(n, "big") if n else b""
                if op == 8:
                    break
                if op == 9:
                    frame(10, data)
                elif op in (0, 2):
                    up.sendall(data)
        except OSError:
            pass
        finally:
            try:
                up.shutdown(socket.SHUT_RDWR)  # wakes the pump thread; close() alone leaves it blocked and the link open
            except OSError:
                pass
            up.close()
            self.close_connection = True

    def do_POST(self):
        if not self.authorised():
            return self.send(403, '{"error":"forbidden"}')
        if urlparse(self.path).path == "/api/upload":
            return self.upload()
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 10000:
                raise ValueError("body too large")
            d = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(d, dict):
                raise ValueError("body must be an object")
            path = urlparse(self.path).path
            if path == "/api/create":
                do_create(d)
                name = d["name"]
                if d.get("start"):
                    background(name, "starting", lambda: dlvm.cmd_start(ns(name=name, timeout=900)))
            elif path == "/api/screen":
                name = str(d.get("name", ""))
                cfg = dlvm.load(name)
                if not dlvm.running(cfg):
                    raise ValueError(f"{name} is not running")
                show_screen(cfg)
            elif path == "/api/touch":
                cfg = dlvm.load(str(d.get("name", "")))
                if not dlvm.running(cfg):
                    raise ValueError("not running")
                do_touch(cfg, d)
            elif path == "/api/input":
                cfg = dlvm.load(str(d.get("name", "")))
                if not dlvm.running(cfg):
                    raise ValueError("not running")
                do_input(cfg, d)
            elif path in ("/api/start", "/api/stop", "/api/delete"):
                name = str(d.get("name", ""))
                dlvm.load(name)  # validates the name and that it exists
                fn = {"/api/start": lambda: dlvm.cmd_start(ns(name=name, timeout=900)),
                      "/api/stop": lambda: dlvm.cmd_stop(ns(name=name)),
                      "/api/delete": lambda: dlvm.cmd_delete(ns(name=name))}[path]
                background(name, {"/api/start": "starting", "/api/stop": "stopping", "/api/delete": "stopping"}[path], fn)
            else:
                return self.send(404, '{"error":"not found"}')
            self.send(200, '{"ok":true}')
        except SystemExit as e:
            self.send(400, json.dumps({"error": str(e)}))
        except (ValueError, json.JSONDecodeError) as e:
            self.send(400, json.dumps({"error": str(e)}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true", help="open the page in the Windows default browser (from WSL)")
    a = ap.parse_args()
    url = f"http://127.0.0.1:{a.port}/?t={TOKEN}"
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    except OSError:
        srv = None  # already running (the token file is shared, so the same link works): just open the page again
    print(f"DragonLord UI {'already running' if srv is None else 'started'}: {url}", flush=True)
    if a.open:  # the token is URL-safe, so the URL needs no quoting
        subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", f"Start-Process '{url}'"], stdout=subprocess.DEVNULL)
    if srv:
        srv.serve_forever()


if __name__ == "__main__":
    main()
