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

## Installation

**macOS (Homebrew) — recommended:**
```bash
brew tap nsted/serial2ws
brew install serial2ws
```
This installs `socat`, `websocat`, and `serial2ws` in one step.

**Manual:**
```bash
git clone https://github.com/nsted/serial2ws.git
cd serial2ws
chmod +x serial2ws
sudo cp serial2ws /usr/local/bin/
```

Dependencies for manual install:
```bash
brew install socat websocat                        # macOS
sudo apt install socat && cargo install websocat   # Linux
```

## Usage

```
serial2ws [-s NAME] [-p PORT] [-w] [-c CERT] [-k KEY]

  -s NAME   name for the virtual serial port  (default: serial2ws)
  -p PORT   WebSocket port to listen on       (default: 8765)
  -w        use WSS (TLS); auto-generates a self-signed cert if -c/-k are omitted
  -c CERT   path to TLS certificate (PEM)
  -k KEY    path to TLS private key (PEM)
  -h        show help
```

### Examples

```bash
# Defaults: /tmp/tty.serial2ws on port 8765
serial2ws

# Custom name and port
serial2ws -s mydevice -p 9000

# WSS with auto-generated self-signed cert
serial2ws -w

# WSS with your own cert
serial2ws -w -c cert.pem -k key.pem

# Multiple instances auto-increment: serial2ws, serial2ws0, serial2ws1, …
serial2ws &
serial2ws &
```

## WS vs WSS

By default `serial2ws` listens on plain `ws://`. This is fine for **localhost-only** connections — browsers allow unencrypted WebSocket connections to `127.0.0.1` from any origin.

Use `-w` (WSS) when:
- your WebSocket client is running on a **different machine**, or
- your web app is served over **HTTPS** (browsers block mixed-content `ws://` from an `https://` page)

### Certificates

WSS requires a TLS certificate. Two options:

**Auto-generated (self-signed)** — simplest, no setup:
```bash
serial2ws -w
```
Self-signed certs will cause a browser security warning and be rejected by default. To use them in a browser you must add the cert to your system trust store, or use a tool like [mkcert](https://github.com/FiloSottile/mkcert) to generate a locally-trusted cert instead.

**Your own cert** — bring a cert already trusted by your clients:
```bash
serial2ws -w -c cert.pem -k key.pem
```

To generate a locally-trusted cert with `mkcert`:
```bash
brew install mkcert
mkcert -install          # one-time: adds mkcert CA to system trust store
mkcert localhost         # creates localhost.pem + localhost-key.pem
serial2ws -w -c localhost.pem -k localhost-key.pem
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
