# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

`serial2ws` creates virtual serial ports (`/dev/tty.name`, `/dev/cu.name`) and bridges them bidirectionally to a WebSocket. Any app (Arduino IDE, screen, etc.) that opens the virtual port communicates with whatever is connected via WebSocket. The browser page is a control panel and optional monitor — the port works independently of whether the browser is connected.

## Running the App

```bash
pip install -r requirements.txt

# Must run as root — creating /dev/tty.* symlinks requires it
sudo python main.py
# open http://localhost:8765
```

## Architecture

```
main.py  (entry point)
├── Serves static/index.html at http://localhost:8765
├── WebSocket endpoint at ws://localhost:8765/ws  (optional monitor)
├── POST /port   →  creates pty pair + /dev/ symlinks, returns paths
└── DELETE /port →  tears down pty, removes symlinks, disconnects WebSockets

static/index.html  (single-file frontend, vanilla JS)
├── Name input + Create Port / Close Port  (port lifecycle)
├── Start Monitor / Stop Monitor  (WebSocket is decoupled from port)
├── Port paths shown as click-to-copy badges (/dev/tty.name + /dev/cu.name)
├── Terminal: green = rx from serial, blue = tx injected from browser
└── Send input (active only while monitoring)

bridge.py  (async pty ↔ WebSocket bridge)
├── pty.openpty() → master_fd (Python) + slave_fd (/dev/ttys###)
├── Symlinks /dev/tty.{name} and /dev/cu.{name} → slave device (requires root)
├── Raises PermissionError with sudo hint if not root
├── master_fd is ALWAYS drained (prevents external app write-blocking)
├── loop.add_reader on master_fd → broadcasts to WebSocket clients (if any)
└── teardown(): cancel tasks, close WebSockets, unlink /dev/ symlinks, close fds
```

## Key Technical Decisions

- **`/dev/tty.*` naming**: Arduino IDE and most macOS serial tools enumerate ports by globbing `/dev/tty.*`. The raw pty slave (`/dev/ttys###`) doesn't match this pattern. Symlinks to `/dev/tty.name` and `/dev/cu.name` are required, which needs root.
- **No `tty.setraw()` on slave**: We don't set terminal modes on the slave before an external app opens it. Doing so corrupts the termios state that the app expects to configure itself (baud rate, parity, etc.).
- **Master always drained**: `_read_pty_loop` runs regardless of WebSocket connections. Without this, the pty write buffer fills and the external app's writes block — appearing as a "seized" port.
- **WebSocket is optional monitor**: Port lifecycle (POST/DELETE /port) is independent of WebSocket connections. Clients can connect/disconnect at any time without affecting the serial port.
- **Framework**: FastAPI + uvicorn — single process handles HTTP, REST, and WebSocket via asyncio.

## Platform Notes

- Requires `sudo` on macOS — `/dev/` symlinks need root. The UI shows a clear error with the sudo command if not root.
- On Linux the slave appears as `/dev/pts/N`. Symlinks to `/dev/tty.name` also require root there.
- Windows not supported (`pty` is Unix-only).
