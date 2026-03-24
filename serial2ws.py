#!/usr/bin/env python3
"""
serial2ws — virtual serial port ↔ WebSocket bridge

Creates /dev/tty.<name> and /dev/cu.<name>, then bridges them
bidirectionally to a WebSocket server.  Requires root on macOS
to create the /dev/ symlinks.

Usage:
  sudo serial2ws                      # auto name, auto port
  sudo serial2ws -s mydevice          # /dev/tty.mydevice + /dev/cu.mydevice
  sudo serial2ws -p 9000              # WebSocket on port 9000
  sudo serial2ws -s mydevice -p 9000
"""

import argparse
import asyncio
import fcntl
import os
import pty
import signal
import sys
from pathlib import Path

try:
    import websockets
except ImportError:
    sys.exit("Missing dependency — run:  pip install websockets")

DEFAULT_NAME = "serial2ws"
DEFAULT_PORT = 8765


# ── bridge ────────────────────────────────────────────────────────────────────

class Bridge:
    def __init__(self, name: str, port: int):
        self.name = name
        self.port = port
        self.master_fd = None
        self.slave_fd  = None
        self.tty_path  = None
        self.cu_path   = None
        self.clients: set = set()

    # -- setup / teardown ---------------------------------------------------

    def setup(self):
        """Open pty and create /dev/ symlinks. Raises PermissionError if not root."""
        self.master_fd, self.slave_fd = pty.openpty()
        slave = os.ttyname(self.slave_fd)

        # Non-blocking master so loop.add_reader never stalls
        flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
        fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        self.tty_path = Path(f"/dev/tty.{self.name}")
        self.cu_path  = Path(f"/dev/cu.{self.name}")

        try:
            for p in (self.tty_path, self.cu_path):
                if p.is_symlink() or p.exists():
                    p.unlink()
                p.symlink_to(slave)
        except PermissionError:
            self._close_fds()
            raise PermissionError(
                "Creating /dev/tty.* requires root.\n"
                f"  Run:  sudo {' '.join(sys.argv)}"
            )

    def teardown(self):
        for p in (self.tty_path, self.cu_path):
            if p and p.is_symlink():
                try:
                    p.unlink()
                except OSError:
                    pass
        self._close_fds()

    def _close_fds(self):
        for fd in (self.slave_fd, self.master_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        self.master_fd = self.slave_fd = None

    # -- pty → WebSocket ----------------------------------------------------

    async def _drain_pty(self):
        """Always drain master_fd; broadcast to connected clients if any."""
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def on_readable():
            try:
                data = os.read(self.master_fd, 4096)
                if data:
                    loop.call_soon_threadsafe(queue.put_nowait, data)
            except OSError:
                pass

        loop.add_reader(self.master_fd, on_readable)
        try:
            while True:
                data = await queue.get()
                if self.clients:
                    await asyncio.gather(
                        *[c.send(data) for c in list(self.clients)],
                        return_exceptions=True,
                    )
        finally:
            loop.remove_reader(self.master_fd)

    # -- WebSocket handler --------------------------------------------------

    async def _ws_handler(self, ws):
        self.clients.add(ws)
        try:
            async for msg in ws:
                data = msg if isinstance(msg, bytes) else msg.encode()
                if self.master_fd is not None:
                    try:
                        os.write(self.master_fd, data)
                    except OSError:
                        pass
        finally:
            self.clients.discard(ws)

    # -- main run loop ------------------------------------------------------

    async def run(self, stop: asyncio.Event):
        try:
            server = await websockets.serve(self._ws_handler, "localhost", self.port)
        except OSError as e:
            sys.exit(f"Cannot bind WebSocket port {self.port}: {e}")

        drain = asyncio.create_task(self._drain_pty())
        try:
            await stop.wait()
        finally:
            drain.cancel()
            try:
                await drain
            except asyncio.CancelledError:
                pass
            server.close()
            await server.wait_closed()


# ── helpers ───────────────────────────────────────────────────────────────────

def available_name(base: str) -> str:
    """Return base if /dev/tty.base doesn't exist, else base0, base1, …"""
    if not Path(f"/dev/tty.{base}").exists():
        return base
    i = 0
    while Path(f"/dev/tty.{base}{i}").exists():
        i += 1
    return f"{base}{i}"


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="serial2ws",
        description="Virtual serial port ↔ WebSocket bridge  (requires root)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:  sudo serial2ws -s mydevice -p 9000",
    )
    parser.add_argument(
        "-s", "--serial", metavar="NAME", default=None,
        help=f"serial port name → /dev/tty.NAME  (default: {DEFAULT_NAME})",
    )
    parser.add_argument(
        "-p", "--port", type=int, default=DEFAULT_PORT,
        help=f"WebSocket port  (default: {DEFAULT_PORT})",
    )
    args = parser.parse_args()

    name   = available_name(args.serial if args.serial else DEFAULT_NAME)
    bridge = Bridge(name, args.port)

    try:
        bridge.setup()
    except PermissionError as e:
        sys.exit(f"Error: {e}")

    print(f"\n  serial port  /dev/tty.{name}")
    print(f"               /dev/cu.{name}")
    print(f"  websocket    ws://localhost:{args.port}")
    print(f"\n  ^C to stop\n")

    stop = asyncio.Event()

    def shutdown(sig, frame=None):
        stop.set()

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        asyncio.run(bridge.run(stop))
    finally:
        bridge.teardown()
        print("Stopped.")


if __name__ == "__main__":
    main()
