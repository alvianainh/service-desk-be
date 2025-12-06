# websocket/notifier.py

from websocket.manager import manager
import json

async def push_notification(payload: dict):
    await manager.broadcast(payload)
