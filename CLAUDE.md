# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

`serial2ws` is a CLI tool that creates virtual serial ports (`/dev/tty.name`, `/dev/cu.name`) and bridges them bidirectionally to a WebSocket server. Any app that opens the virtual port communicates with whatever is connected via WebSocket, and vice versa.

## Usage

```bash
pip install -r requirements.txt

sudo python serial2ws.py                      # auto name + auto port
sudo python serial2ws.py -s mydevice          # /dev/tty.mydevice + /dev/cu.mydevice
sudo python serial2ws.py -p 9000              # WebSocket on port 9000
sudo python serial2ws.py -s mydevice -p 9000
```

Requires `sudo` — creating `/dev/tty.*` symlinks requires root on macOS.

## Architecture

Single file: `serial2ws.py`

```
main()
├── Parse -s / -p flags; auto-pick name if -s omitted
├── Bridge.setup()  →  pty.openpty(), create /dev/tty.name + /dev/cu.name
├── Print paths + ws:// URL to stdout
└── asyncio.run(bridge.run(stop_event))
       ├── websockets.serve() — WebSocket server
       ├── _drain_pty() task — always drains master_fd, broadcasts to clients
       ├── _ws_handler() — each client: WS messages → master_fd writes
       └── on stop_event: cancel drain task, close server, Bridge.teardown()

Bridge.teardown()
└── Unlink /dev/ symlinks, close master_fd + slave_fd
```

## Key Technical Decisions

- **`/dev/tty.*` naming**: Arduino IDE and most macOS serial tools enumerate by globbing `/dev/tty.*`. The raw pty slave (`/dev/ttys###`) doesn't match. Symlinks to `/dev/tty.name` and `/dev/cu.name` are required.
- **No `tty.setraw()` on slave**: We don't configure termios — the connecting app sets its own baud rate, parity, etc.
- **Master always drained**: `_drain_pty` runs regardless of WebSocket connections. Without this, pty write buffers fill and the external app's writes block.
- **Auto-naming**: If `-s` is omitted, defaults to `serial2ws`; increments suffix (`serial2ws0`, `serial2ws1`, …) if already in use.

## Platform Notes

- Requires `sudo` — `/dev/` symlink creation needs root. A clear error with the exact retry command is shown if not root.
- On Linux the slave appears as `/dev/pts/N`; symlinks also require root.
- Windows not supported (`pty` is Unix-only).
