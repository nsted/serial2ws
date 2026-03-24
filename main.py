import uvicorn
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from bridge import Bridge

bridge = Bridge()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await bridge.teardown()


app = FastAPI(lifespan=lifespan)


class PortRequest(BaseModel):
    name: str


@app.get("/")
async def get_index():
    return HTMLResponse(Path("static/index.html").read_text())


@app.post("/port")
async def create_port(req: PortRequest):
    name = req.name.strip() or "myport"
    try:
        ports = await bridge.create(name)
        return {"tty": ports.tty, "cu": ports.cu, "slave": ports.slave}
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"detail": str(e)})


@app.delete("/port")
async def delete_port():
    await bridge.teardown()
    return {"status": "closed"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Optional monitor connection — port works with or without this."""
    await ws.accept()
    bridge.add_websocket(ws)
    try:
        while True:
            data = await ws.receive_bytes()
            await bridge.write_to_pty(data)
    except WebSocketDisconnect:
        pass
    finally:
        bridge.remove_websocket(ws)


if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8765)
