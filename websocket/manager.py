# websocket/manager.py

from fastapi import WebSocket
from datetime import datetime

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        message["timestamp"] = datetime.utcnow().isoformat() + "Z"
        
        for ws in list(self.active_connections):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws)

manager = ConnectionManager()


# # websocket/manager.py
# from fastapi import WebSocket
# from datetime import datetime

# class ConnectionManager:
#     def __init__(self):
#         self.active_connections: list[dict] = []  # simpan ws + info user

#     async def connect(self, websocket: WebSocket, user_info: dict):
#         await websocket.accept()
#         self.active_connections.append({
#             "ws": websocket,
#             "user_id": user_info["id"],
#             "role": user_info["role_name"],
#             "opd_id": user_info.get("dinas_id")
#         })

#     def disconnect(self, websocket: WebSocket):
#         self.active_connections = [
#             c for c in self.active_connections if c["ws"] != websocket
#         ]

#     async def broadcast(self, message: dict, target_roles: list[str] = None, target_opd: int = None):
#         message["timestamp"] = datetime.utcnow().isoformat() + "Z"
        
#         for conn in list(self.active_connections):
#             if target_roles and conn["role"] not in target_roles:
#                 continue
#             if target_opd and conn["opd_id"] != target_opd:
#                 continue
#             try:
#                 await conn["ws"].send_json(message)
#             except Exception:
#                 self.disconnect(conn["ws"])

# manager = ConnectionManager()
