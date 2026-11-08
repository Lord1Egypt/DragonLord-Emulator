#!/usr/bin/env python3
"""DragonLord instance manager UI: first-run wizard + instance list, served on 127.0.0.1 only.

  dlui.py [--port 8765]      then open the printed URL (it contains a per-run access token)

Thin layer over dlvm.py: every action calls the same functions as the CLI, so limits and name checks live in one place.
"""
import argparse
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
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
                       extra=None, imei=str(d.get("imei") or "") or None))


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
        self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'; connect-src 'self'")
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
        if path == "/view":
            return self.send(200, VIEW.replace("__TOKEN__", TOKEN), "text/html; charset=utf-8")
        if path == "/api/stream":
            return self.stream(parse_qs(urlparse(self.path).query).get("name", [""])[0])
        self.send(404, '{"error":"not found"}')

    def stream(self, name):
        """Raw H.264 (Annex B) from the guest's screenrecord, restarted when its 3-minute limit ends."""
        try:
            cfg = dlvm.load(name)
        except SystemExit as e:
            return self.send(400, json.dumps({"error": str(e)}))
        if not dlvm.running(cfg):
            return self.send(400, '{"error":"not running"}')
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while dlvm.running(dlvm.load(name)):
                p = subprocess.Popen(adb_cmd(cfg, "exec-out", "screenrecord", "--output-format=h264", "--time-limit", "180",
                                             "--bit-rate", "4000000", "--size", cfg["res"], "-"),
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

    def do_POST(self):
        if not self.authorised():
            return self.send(403, '{"error":"forbidden"}')
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
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    url = f"http://127.0.0.1:{a.port}/?t={TOKEN}"
    print(f"DragonLord UI: {url}", flush=True)
    if a.open:  # the token is URL-safe, so the URL needs no quoting
        subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", f"Start-Process '{url}'"], stdout=subprocess.DEVNULL)
    srv.serve_forever()


if __name__ == "__main__":
    main()
