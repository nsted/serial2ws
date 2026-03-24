import asyncio
import fcntl
import os
import pty
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import WebSocket


@dataclass
class PortPaths:
    tty: str    # /dev/tty.name  — appears in Arduino, screen, etc.
    cu: str     # /dev/cu.name   — call-out variant (what most apps use)
    slave: str  # underlying /dev/ttys### device


class Bridge:
    def __init__(self):
        self.master_fd: Optional[int] = None
        self.slave_fd: Optional[int] = None
        self.ports: Optional[PortPaths] = None
        self.websockets: set = set()
        self._read_task: Optional[asyncio.Task] = None
        self.active = False

    async def create(self, name: str) -> PortPaths:
        """
        Create a virtual serial port pair.
        Creates /dev/tty.{name} and /dev/cu.{name} symlinks — requires root.
        Raises PermissionError with a helpful message if not running as root.
        """
        if self.active:
            await self.teardown()

        self.master_fd, self.slave_fd = pty.openpty()
        slave_path = os.ttyname(self.slave_fd)

        # Do NOT set raw mode here — let the connecting app (Arduino, screen, etc.)
        # configure termios itself. Mangling slave settings before they open it
        # causes "port in use" / garbled comms.

        # Non-blocking master so loop.add_reader drives reads without stalling
        flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
        fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        tty_path = Path(f"/dev/tty.{name}")
        cu_path  = Path(f"/dev/cu.{name}")
        try:
            for p in (tty_path, cu_path):
                if p.is_symlink() or p.exists():
                    p.unlink()
                p.symlink_to(slave_path)
        except PermissionError:
            for fd in (self.slave_fd, self.master_fd):
                try:
                    os.close(fd)
                except OSError:
                    pass
            self.master_fd = self.slave_fd = None
            raise PermissionError(
                "Creating /dev/tty.* symlinks requires root. "
                "Restart with:  sudo python main.py"
            )

        self.ports = PortPaths(tty=str(tty_path), cu=str(cu_path), slave=slave_path)
        self.active = True
        self._read_task = asyncio.create_task(self._read_pty_loop())
        return self.ports

    async def _read_pty_loop(self):
        """
        Always drain master_fd regardless of WebSocket connections.
        If no clients are connected data is discarded — this prevents the
        pty write buffer from filling up and blocking the external app.
        """
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
            while self.active:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=1.0)
                    await self._broadcast(data)   # no-op if no clients connected
                except asyncio.TimeoutError:
                    continue
        finally:
            loop.remove_reader(self.master_fd)

    async def _broadcast(self, data: bytes):
        disconnected = set()
        for ws in list(self.websockets):
            try:
                await ws.send_bytes(data)
            except Exception:
                disconnected.add(ws)
        self.websockets -= disconnected

    async def write_to_pty(self, data: bytes):
        if self.master_fd is not None and self.active:
            try:
                os.write(self.master_fd, data)
            except OSError:
                pass

    def add_websocket(self, ws: WebSocket):
        self.websockets.add(ws)

    def remove_websocket(self, ws: WebSocket):
        self.websockets.discard(ws)

    async def teardown(self):
        """Destroy the port: cancel tasks, close WebSockets, remove /dev/ symlinks, close fds."""
        self.active = False

        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None

        for ws in list(self.websockets):
            try:
                await ws.close()
            except Exception:
                pass
        self.websockets.clear()

        if self.ports:
            for path_str in (self.ports.tty, self.ports.cu):
                p = Path(path_str)
                if p.is_symlink():
                    try:
                        p.unlink()
                    except OSError:
                        pass
            self.ports = None

        for fd in (self.slave_fd, self.master_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

        self.master_fd = None
        self.slave_fd = None
