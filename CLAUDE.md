# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

`serial2ws` is a shell script that creates a virtual serial port and bridges it bidirectionally to a WebSocket server. It uses `socat` to create the PTY device and `websocat` to handle the WebSocket side, connected via a local TCP relay.

## Dependencies

```bash
brew install socat websocat
```

## Usage

```bash
./serial2ws                        # auto name, port 8765
./serial2ws -s mydevice            # named /tmp/tty.mydevice
./serial2ws -p 9000                # WebSocket on port 9000
./serial2ws -s mydevice -p 9000
```

Output on startup:
```
  serial port  /dev/ttys005
  symlink      /tmp/tty.mydevice
  websocket    ws://localhost:8765

  ^C to stop
```

## Architecture

```
socat  ──  pty,link=/tmp/tty.NAME  ──  tcp-l:PORT+1 (relay)
                                              │
websocat  ──  ws-l:PORT  ──  tcp:PORT+1 (relay)
```

- **socat** creates the PTY slave (lands at `/dev/ttysN`, symlinked to `/tmp/tty.NAME`) and bridges it to a local TCP relay port
- **websocat** listens for WebSocket connections and bridges each to the TCP relay (`-E` flag loops across disconnects)
- The TCP relay on `PORT+1` (loopback only) decouples the two processes cleanly

## Platform Notes

- macOS `devfs` makes `/dev/` read-only even for root — named symlinks live in `/tmp/` instead. The underlying PTY slave (`/dev/ttysN`) is shown on startup; this is a real tty device usable by any tool that accepts an explicit path.
- For apps like Arduino IDE that enumerate ports via IOKit (kernel-level serial device registry), the PTY won't appear in the dropdown — enter the `/dev/ttysN` path manually or use `arduino-cli --port /dev/ttysN`.
- On Linux the slave appears as `/dev/pts/N`. Symlinks can go anywhere.
- Windows not supported (PTY is Unix-only).
