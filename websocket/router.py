# websocket/router.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from .manager import manager

router = APIRouter()

@router.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)



# from fastapi import APIRouter, WebSocket, Query, WebSocketDisconnect
# from websocket.manager import manager
# from auth.auth import get_current_user_universal
# from fastapi import Depends
# from auth.database import get_db

# router = APIRouter()

# @router.websocket("/ws/notifications")
# async def websocket_notifications(websocket: WebSocket, token: str = Query(...), db=Depends(get_db)):
#     try:
#         current_user = await get_current_user_universal_from_token(token, db)
#         if not current_user:
#             await websocket.close(code=1008)
#             return

#         await manager.connect(websocket, user_info=current_user)

#         while True:
#             await websocket.receive_text()  # keep-alive
#     except WebSocketDisconnect:
#         manager.disconnect(websocket)
#     except Exception:
#         manager.disconnect(websocket)

