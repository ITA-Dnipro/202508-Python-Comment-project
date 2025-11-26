from fastapi import WebSocket
from app.database import comments_collection

import aioredis

class ConnectionManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, websocket: WebSocket, project_id: int):
        await websocket.accept()
        self.active_connections.setdefault(project_id, []).append(websocket)

    async def disconnect(self, websocket: WebSocket, project_id: int):
        self.active_connections[project_id].remove(websocket)

    async def broadcast(self, project_id: int, message: dict):
        for ws in self.active_connections.get(project_id, []):
            await ws.send_json(message)

manager = ConnectionManager()