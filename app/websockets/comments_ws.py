from fastapi import WebSocket, WebSocketDisconnect
from app.database import comments_collection
from bson import ObjectId
from datetime import datetime, timezone
import json
import asyncio
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

@router.websocket("/ws/projects/{project_id}/comments")
async def websocket_endpoint(websocket: WebSocket, project_id: int):
    await manager.connect(websocket, project_id)
    try:
        while True:
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        await manager.disconnect(websocket, project_id)
