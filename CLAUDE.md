# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

`serial2ws` is a CLI tool that creates virtual serial ports (`/dev/tty.name`, `/dev/cu.name`) and bridges them bidirectionally to a WebSocket server. Any app that opens the virtual port communicates with whatever is connected via WebSocket, and vice versa.

## Usage

```bash
pip install -r requirements.txt

python serial2ws.py                      # auto name, port 8765
python serial2ws.py -s mydevice          # named /tmp/tty.mydevice
python serial2ws.py -p 9000              # WebSocket on port 9000
python serial2ws.py -s mydevice -p 9000
```

No root required.

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

- **`/dev/` is read-only on macOS**: macOS `devfs` blocks all writes to `/dev/` — even root cannot create symlinks there. Named symlinks live in `/tmp/tty.{name}` instead. The underlying pty slave is already in `/dev/` as `/dev/ttys###` and is shown alongside the symlink path on startup.
- **No `tty.setraw()` on slave**: We don't configure termios — the connecting app sets its own baud rate, parity, etc.
- **Master always drained**: `_drain_pty` runs regardless of WebSocket connections. Without this, pty write buffers fill and the external app's writes block.
- **Auto-naming**: If `-s` is omitted, defaults to `serial2ws`; increments suffix (`serial2ws0`, `serial2ws1`, …) if already in use.

## Platform Notes

- No root required. Named symlinks go to `/tmp/` which is world-writable.
- On Linux the slave appears as `/dev/pts/N`. Behavior is identical.
- Windows not supported (`pty` is Unix-only).
