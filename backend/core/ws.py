import jwt
from fastapi import APIRouter, WebSocket

from core.security import JWT_SECRET, JWT_ALGORITHM


class ConnectionManager:
    def __init__(self):
        self.connections = {}  # email -> set of websockets
        self.missed_events = {}

    async def connect(self, websocket: WebSocket, email: str):
        await websocket.accept()
        self.connections.setdefault(email, set()).add(websocket)
        
        if email in self.missed_events and self.missed_events[email]:
            try:
                await websocket.send_json({
                    "event": "sync_recovery",
                    "missed_events": self.missed_events[email]
                })
                self.missed_events[email] = []
            except Exception:
                pass

    def disconnect(self, websocket: WebSocket, email: str):
        conns = self.connections.get(email)
        if conns:
            conns.discard(websocket)
            if not conns:
                self.connections.pop(email, None)

    async def broadcast(self, message: dict):
        active_emails = list(self.connections.keys())
        all_emails = list(set(active_emails + list(self.missed_events.keys())))
        for email in all_emails:
            conns = self.connections.get(email, set())
            if not conns:
                self.missed_events.setdefault(email, []).append(message)
                if len(self.missed_events[email]) > 50:
                    self.missed_events[email] = self.missed_events[email][-50:]
            else:
                for ws in list(conns):
                    try:
                        await ws.send_json(message)
                    except Exception:
                        pass

    async def send_to_user(self, email: str, message: dict):
        for ws in list(self.connections.get(email, set())):
            try:
                await ws.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()

ws_router = APIRouter()


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = ""):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        email = payload.get("email")
    except Exception:
        await websocket.close(code=4401)
        return
    if not email:
        await websocket.close(code=4401)
        return
    await manager.connect(websocket, email)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        manager.disconnect(websocket, email)
