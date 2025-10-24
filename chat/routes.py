from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import joinedload

from auth.database import get_db
from auth.auth import get_current_user 
from .models import Chat, ChatMessage 

router = APIRouter(tags=["Chat"])

@router.post("/chat/send")
async def send_message(
    opd_id: UUID = Form(...),
    message: str = Form(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    user_id = UUID(current_user["id"])
    roles = current_user.get("roles", [])

    if "masyarakat" not in roles:
        raise HTTPException(status_code=403, detail="Hanya masyarakat yang dapat memulai chat")

    chat = db.query(Chat).filter(Chat.opd_id == opd_id, Chat.user_id == user_id).first()

    if not chat:
        chat = Chat(opd_id=opd_id, user_id=user_id)
        db.add(chat)
        db.commit()
        db.refresh(chat)

    new_message = ChatMessage(chat_id=chat.chat_id, sender_id=user_id, message=message)
    db.add(new_message)
    db.commit()

    return {"message": "Pesan berhasil dikirim", "chat_id": str(chat.chat_id)}


@router.post("/chat/{chat_id}/send")
async def send_reply_from_user(
    chat_id: UUID,
    message: str = Form(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    roles = current_user.get("roles", [])
    if "masyarakat" not in roles:
        raise HTTPException(status_code=403, detail="Hanya masyarakat yang dapat mengirim pesan")

    user_id = UUID(current_user["id"])
    chat = db.query(Chat).filter(Chat.chat_id == chat_id, Chat.user_id == user_id).first()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat tidak ditemukan atau bukan milik Anda")

    new_message = ChatMessage(chat_id=chat.chat_id, sender_id=user_id, message=message)
    db.add(new_message)

    chat.last_message_at = datetime.utcnow()
    db.commit()

    return {"message": "Pesan berhasil dikirim", "chat_id": str(chat.chat_id)}


@router.get("/chat/history/{chat_id}")
async def get_chat_history_for_user(
    chat_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if "masyarakat" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Hanya masyarakat yang dapat melihat riwayat chat")

    user_id = UUID(current_user["id"])
    chat = (
        db.query(Chat)
        .options(joinedload(Chat.messages))
        .filter(Chat.chat_id == chat_id, Chat.user_id == user_id)
        .first()
    )

    if not chat:
        raise HTTPException(status_code=404, detail="Chat tidak ditemukan atau bukan milik Anda")

    return {
        "chat_id": str(chat.chat_id),
        "opd_id": str(chat.opd_id),
        "messages": [
            {
                "message_id": str(msg.message_id),
                "message": msg.message,
                "sender_id": str(msg.sender_id),
                "sent_at": msg.sent_at
            }
            for msg in chat.messages
        ]
    }


#SEKSI
@router.get("/chat/opd")
async def get_chats_for_opd(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if "seksi" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Hanya seksi yang bisa melihat chat ini")

    opd_id = current_user.get("opd_id")
    chats = (
        db.query(Chat)
        .options(joinedload(Chat.messages)) 
        .filter(Chat.opd_id == opd_id)
        .order_by(Chat.last_message_at.desc())
        .all()
    )
    return chats


@router.get("/chat/opd/history/{chat_id}")
async def get_chat_history_for_seksi(
    chat_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if "seksi" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Hanya seksi yang dapat melihat riwayat chat")

    opd_id = current_user.get("opd_id")
    chat = (
        db.query(Chat)
        .options(joinedload(Chat.messages))
        .filter(Chat.chat_id == chat_id, Chat.opd_id == opd_id)
        .first()
    )

    if not chat:
        raise HTTPException(status_code=404, detail="Chat tidak ditemukan untuk OPD Anda")

    return {
        "chat_id": str(chat.chat_id),
        "user_id": str(chat.user_id),
        "messages": [
            {
                "message_id": str(msg.message_id),
                "message": msg.message,
                "sender_id": str(msg.sender_id),
                "sent_at": msg.sent_at
            }
            for msg in chat.messages
        ]
    }


# @router.get("/chat/opd/list")
# async def list_active_chats_for_seksi(
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user)
# ):
#     if "seksi" not in current_user.get("roles", []):
#         raise HTTPException(status_code=403, detail="Hanya seksi yang bisa melihat daftar chat")

#     opd_id = current_user.get("opd_id")

#     chats = (
#         db.query(Chat)
#         .options(joinedload(Chat.messages))
#         .filter(Chat.opd_id == opd_id)
#         .order_by(Chat.last_message_at.desc())
#         .all()
#     )

#     return [
#         {
#             "chat_id": str(chat.chat_id),
#             "user_id": str(chat.user_id),
#             "last_message": chat.messages[-1].message if chat.messages else None,
#             "last_sender": str(chat.messages[-1].sender_id) if chat.messages else None,
#             "last_time": chat.messages[-1].sent_at if chat.messages else None
#         }
#         for chat in chats
#     ]


@router.post("/chat/{chat_id}/reply")
async def reply_to_chat(
    chat_id: UUID,
    message: str = Form(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if "seksi" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Hanya seksi yang bisa membalas pesan")

    sender_id = UUID(current_user["id"])
    chat = db.query(Chat).filter(Chat.chat_id == chat_id).first()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat tidak ditemukan")

    new_message = ChatMessage(chat_id=chat.chat_id, sender_id=sender_id, message=message)
    db.add(new_message)

    chat.last_message_at = datetime.utcnow()
    db.commit()

    return {"message": "Balasan berhasil dikirim"}
