#!/usr/bin/env python3
"""Host a single file on port 5000 for a limited time (default 5 minutes)."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_PORT = 5000
DEFAULT_TIMEOUT_SEC = 5 * 60
APP_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "host-on-5000"
PID_FILE = APP_DIR / "current.pid"
STATE_FILE = APP_DIR / "current.json"


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    except SystemError:
        return False
    # On Windows, os.kill(pid, 0) may succeed for zombies; use tasklist/OpenProcess via taskkill probe
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                check=False,
            )
            return str(pid) in out.stdout
        except OSError:
            return True
    return True


def kill_pid(pid: int) -> None:
    if pid <= 0 or not is_pid_alive(pid):
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    for _ in range(20):
        if not is_pid_alive(pid):
            return
        time.sleep(0.1)


def kill_port_listeners(port: int) -> None:
    """Best-effort: free the port if a leftover process still holds it."""
    if os.name != "nt":
        return
    try:
        out = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
    except OSError:
        return
    pids: set[int] = set()
    needle = f":{port}"
    for line in out.splitlines():
        if "LISTENING" not in line.upper():
            continue
        if needle not in line:
            continue
        # Match local address ending with :port
        parts = line.split()
        if len(parts) < 5:
            continue
        local = parts[1] if parts[0].upper().startswith("TCP") else parts[0]
        if not (local.endswith(needle) or local.endswith(f"]{needle}")):
            # also accept 0.0.0.0:5000 / [::]:5000
            if f":{port}" not in local:
                continue
        try:
            pids.add(int(parts[-1]))
        except ValueError:
            continue
    me = os.getpid()
    for pid in pids:
        if pid != me:
            kill_pid(pid)


def stop_previous_instance() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if PID_FILE.exists():
        try:
            old = int(PID_FILE.read_text(encoding="utf-8").strip())
        except ValueError:
            old = 0
        if old and old != os.getpid():
            print(f"Stopping previous host (PID {old})...")
            kill_pid(old)
        try:
            PID_FILE.unlink(missing_ok=True)
        except OSError:
            pass
    if STATE_FILE.exists():
        try:
            STATE_FILE.unlink(missing_ok=True)
        except OSError:
            pass


def write_lock(file_path: Path, port: int, timeout_sec: int) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    STATE_FILE.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "file": str(file_path),
                "port": port,
                "timeout_sec": timeout_sec,
                "started": time.time(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def clear_lock() -> None:
    for path in (PID_FILE, STATE_FILE):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def make_handler(file_path: Path):
    data = file_path.read_bytes()
    filename = file_path.name
    quoted = urllib.parse.quote(filename)
    ctype, _ = mimetypes.guess_type(filename)
    if not ctype:
        ctype = "application/octet-stream"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))

        def _serve(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quoted}',
            )
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
            if path in ("/", f"/{filename}", f"/{quoted}"):
                self._serve()
                return
            # Accept path-only match ignoring extra encoding differences
            if path.rstrip("/").endswith("/" + filename) or path.endswith(filename):
                self._serve()
                return
            self.send_error(404, "Only the hosted file is available")

        def do_HEAD(self) -> None:  # noqa: N802
            path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
            if path in ("/", f"/{filename}", f"/{quoted}") or path.endswith(filename):
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                return
            self.send_error(404, "Only the hosted file is available")

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Host a single file on a temporary web server.")
    parser.add_argument("file", help="Path to the file to host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SEC, help="Seconds before auto-stop")
    args = parser.parse_args()

    file_path = Path(args.file).expanduser().resolve()
    if not file_path.is_file():
        print(f"Not a file: {file_path}", file=sys.stderr)
        return 1

    port = args.port
    timeout_sec = max(1, args.timeout)

    stop_previous_instance()
    kill_port_listeners(port)

    handler = make_handler(file_path)
    try:
        httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
    except OSError as exc:
        print(f"Could not bind port {port}: {exc}", file=sys.stderr)
        # One more try after forcing the port free
        kill_port_listeners(port)
        time.sleep(0.3)
        try:
            httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
        except OSError as exc2:
            print(f"Still could not bind port {port}: {exc2}", file=sys.stderr)
            return 1

    write_lock(file_path, port, timeout_sec)

    local = f"http://127.0.0.1:{port}/{urllib.parse.quote(file_path.name)}"
    lan = f"http://{lan_ip()}:{port}/{urllib.parse.quote(file_path.name)}"
    bare = f"http://127.0.0.1:{port}/"

    print("=" * 60)
    print("host-on-5000")
    print(f"File:     {file_path}")
    print(f"Port:     {port}")
    print(f"Timeout:  {timeout_sec} seconds ({timeout_sec // 60}m)")
    print(f"Local:    {local}")
    print(f"LAN:      {lan}")
    print(f"Also:     {bare}  (same file)")
    print("Press Ctrl+C to stop early.")
    print("=" * 60)

    stop_event = threading.Event()

    def shutdown() -> None:
        if stop_event.is_set():
            return
        stop_event.set()
        print("\nTimeout reached - shutting down.")
        # shutdown() must not run on the request thread; schedule from timer is fine
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    timer = threading.Timer(timeout_sec, shutdown)
    timer.daemon = True
    timer.start()

    def countdown() -> None:
        end = time.time() + timeout_sec
        while not stop_event.wait(1.0):
            remaining = int(end - time.time())
            if remaining < 0:
                break
            mins, secs = divmod(remaining, 60)
            print(f"\rTime left: {mins:02d}:{secs:02d}   ", end="", flush=True)

    threading.Thread(target=countdown, daemon=True).start()

    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        timer.cancel()
        stop_event.set()
        httpd.server_close()
        clear_lock()
        print("\nServer stopped. Port released.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
