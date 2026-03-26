# serial2ws

A shell script that creates a virtual serial port and bridges it bidirectionally to a WebSocket server. Connect any serial-capable application to a WebSocket endpoint — and vice versa.

```
  serial port  /tmp/tty.mydevice  (→ /dev/ttys005)
  websocket    ws://localhost:8765

  screen /tmp/tty.mydevice 115200

  ^C to stop
```

## Use cases

- Bridge hardware connected to a WebSocket (e.g. a browser app) to a serial terminal
- Test serial firmware from a browser without physical hardware
- Let legacy serial software talk to a modern WebSocket-based service
- Pipe serial data to/from a remote WebSocket endpoint via a local virtual port

## Requirements

- macOS or Linux
- [socat](http://www.dest-unreach.org/socat/) and [websocat](https://github.com/vi/websocat)

```bash
brew install socat websocat          # macOS
sudo apt install socat && cargo install websocat   # Linux (websocat via cargo)
```

## Installation

```bash
git clone https://github.com/nsted/serial2ws.git
cd serial2ws
chmod +x serial2ws
sudo cp serial2ws /usr/local/bin/   # makes serial2ws available system-wide
```

## Usage

```
serial2ws [-s NAME] [-p PORT]

  -s NAME   name for the virtual serial port  (default: serial2ws)
  -p PORT   WebSocket port to listen on       (default: 8765)
  -h        show help
```

### Examples

```bash
# Defaults: /tmp/tty.serial2ws on port 8765
serial2ws

# Custom name and port
serial2ws -s mydevice -p 9000

# Multiple instances auto-increment: serial2ws, serial2ws0, serial2ws1, …
serial2ws &
serial2ws &
```

## Connecting

### From a serial terminal

Use the **symlink path** shown on startup — it stays consistent across runs:

```bash
screen /tmp/tty.serial2ws 115200
```

The startup output also prints the exact command to copy-paste.

### From a WebSocket client

Any WebSocket client can connect to `ws://localhost:PORT`. Data sent to the WebSocket is written to the serial port; data arriving on the serial port is forwarded to all connected WebSocket clients.

**Browser (JavaScript):**
```javascript
const ws = new WebSocket('ws://localhost:8765');
ws.binaryType = 'arraybuffer';

ws.onmessage = (e) => {
  const text = new TextDecoder().decode(new Uint8Array(e.data));
  console.log('serial →', text);
};

ws.send(new TextEncoder().encode('hello\n'));
```

**Python:**
```python
import asyncio, websockets

async def main():
    async with websockets.connect('ws://localhost:8765') as ws:
        await ws.send(b'hello\n')
        print(await ws.recv())

asyncio.run(main())
```

**wscat (CLI):**
```bash
npx wscat -c ws://localhost:8765
```

## How it works

```
[ serial app ]                          [ WebSocket client ]
      │                                          │
 /tmp/tty.NAME (symlink)               ws://localhost:PORT
      │                                          │
 /dev/ttysN  (PTY slave)                    websocat
      │                                          │
   socat ──── tcp://127.0.0.1:PORT+1 ────── websocat
  (PTY ↔ TCP relay)                   (WebSocket ↔ TCP relay)
```

- **socat** opens a PTY pair and exposes the slave via a named symlink in `/tmp/`. It then bridges the PTY master to a local TCP relay port.
- **websocat** listens for WebSocket connections and bridges each one to the TCP relay. The `-E` flag keeps it alive across disconnects.
- The TCP relay runs on `PORT+1` on loopback only and is an internal implementation detail.

## macOS note on port visibility

macOS manages `/dev/` through the kernel's IOKit framework — even root cannot create device entries there from userspace. The virtual serial port therefore lives at:

- **`/tmp/tty.NAME`** — the stable, named symlink to use in your application
- **`/dev/ttysN`** — the underlying PTY slave device (number changes each run)

Both paths work identically as serial ports. **Use the `/tmp/tty.NAME` path** since it stays consistent across runs.

**Arduino IDE** enumerates ports via IOKit and will not auto-list the virtual port. Use the path from the terminal output directly in [Arduino CLI](https://arduino.github.io/arduino-cli/):

```bash
arduino-cli upload -p /tmp/tty.serial2ws --fqbn arduino:avr:uno ./sketch
arduino-cli monitor -p /tmp/tty.serial2ws --config baudrate=115200
```

On **Linux**, the PTY slave appears as `/dev/pts/N` and symlinks can be placed anywhere.

## Cleanup

`serial2ws` removes the symlink and stops all child processes on exit (`^C`, `SIGTERM`, or normal exit). If a crash leaves a stale symlink:

```bash
rm /tmp/tty.serial2ws
```

## License

MIT
