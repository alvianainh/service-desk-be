from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import joinedload
import uuid
import aiohttp
import os
import mimetypes
from io import BytesIO

from auth.database import get_db
from auth.auth import get_current_user 
from .models import Chat, ChatMessage 

router = APIRouter(tags=["chat"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_BUCKET = "docs_chat" 


@router.post("/chat/send")
async def send_message(
    opd_id: UUID = Form(...),
    message: str = Form(""),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    user_id = UUID(current_user["id"])

    chat = db.query(Chat).filter(
        Chat.opd_id == opd_id,
        Chat.user_id == user_id
    ).first()

    if not chat:
        chat = Chat(
            opd_id=opd_id,
            user_id=user_id
        )
        db.add(chat)
        db.commit()
        db.refresh(chat)

    file_url, file_type = None, None

    if file:
        file_ext = file.filename.split(".")[-1]
        file_path = f"{chat.chat_id}/{uuid.uuid4()}.{file_ext}"

        async with aiohttp.ClientSession() as session:
            upload_url = (
                f"{SUPABASE_URL}/storage/v1/object/"
                f"{SUPABASE_BUCKET}/{file_path}"
            )

            headers = {
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": file.content_type
            }

            file_bytes = await file.read()

            async with session.put(upload_url, headers=headers, data=file_bytes) as res:
                if res.status >= 300:
                    detail = await res.text()
                    raise HTTPException(
                        status_code=500,
                        detail=f"Gagal upload file ke Supabase: {detail}"
                    )

        file_url = (
            f"{SUPABASE_URL}/storage/v1/object/public/"
            f"{SUPABASE_BUCKET}/{file_path}"
        )
        file_type = file.content_type

    new_message = ChatMessage(
        chat_id=chat.chat_id,
        sender_id=user_id,
        message=message,
        file_url=file_url,
        file_type=file_type,
        role="user"
    )

    db.add(new_message)
    chat.last_message_at = datetime.utcnow()
    db.commit()

    return {
        "message": "Pesan berhasil dikirim",
        "chat_id": str(chat.chat_id),
        "user": current_user
    }



@router.post("/chat/{chat_id}/send")
async def send_reply_from_user(
    chat_id: UUID,
    message: str = Form(""),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    roles = current_user.get("roles", [])
    if not any(role in roles for role in ["masyarakat", "pegawai"]):
        raise HTTPException(status_code=403, detail="Hanya masyarakat atau pegawai yang dapat mengirim pesan")

    user_id = UUID(current_user["id"])
    chat = db.query(Chat).filter(Chat.chat_id == chat_id, Chat.user_id == user_id).first()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat tidak ditemukan atau bukan milik Anda")

    file_url, file_type = None, None

    if file:
        file_ext = file.filename.split(".")[-1]
        file_path = f"{chat.chat_id}/{uuid.uuid4()}.{file_ext}"

        async with aiohttp.ClientSession() as session:
            upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{file_path}"
            headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": file.content_type}
            file_bytes = await file.read()
            async with session.put(upload_url, headers=headers, data=file_bytes) as res:
                if res.status >= 300:
                    detail = await res.text()
                    raise HTTPException(status_code=500, detail=f"Gagal upload file ke Supabase: {detail}")

        file_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{file_path}"
        file_type = file.content_type

    new_message = ChatMessage(
        chat_id=chat.chat_id,
        sender_id=user_id,
        message=message,
        file_url=file_url,
        file_type=file_type,
        role="user"
    )

    db.add(new_message)
    chat.last_message_at = datetime.utcnow()
    db.commit()

    return {"message": "Balasan berhasil dikirim", "chat_id": str(chat.chat_id)}


@router.get("/chat/history/{chat_id}")
async def get_chat_history_for_user(
    chat_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    roles = current_user.get("roles", [])

    if not any(role in ["masyarakat", "pegawai"] for role in roles):
        raise HTTPException(status_code=403, detail="Hanya masyarakat atau pegawai yang dapat melihat riwayat chat")

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
                "sent_at": msg.sent_at,
                "file_url": msg.file_url,
                "file_type": msg.file_type,
                "role": msg.role
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
                "sent_at": msg.sent_at,
                "file_url": msg.file_url,
                "file_type": msg.file_type,
                "role": msg.role
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
    message: str = Form(""),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if "seksi" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Hanya seksi yang bisa membalas pesan")

    sender_id = UUID(current_user["id"])
    chat = db.query(Chat).filter(Chat.chat_id == chat_id).first()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat tidak ditemukan")

    file_url = None
    file_type = None

    if file:
        try:
            file_bytes = await file.read()
            file_ext = os.path.splitext(file.filename)[1]
            file_name = f"{chat_id}_{uuid.uuid4()}{file_ext}"
            content_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"

            upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{file_name}"
            headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": content_type}

            async with aiohttp.ClientSession() as session:
                async with session.post(upload_url, data=BytesIO(file_bytes), headers=headers) as res:
                    if res.status >= 400:
                        error_text = await res.text()
                        raise Exception(f"Gagal upload: {error_text}")

            file_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{file_name}"
            file_type = content_type

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Gagal upload file: {str(e)}")

    new_message = ChatMessage(
        chat_id=chat.chat_id,
        sender_id=sender_id,
        message=message,
        file_url=file_url,
        file_type=file_type,
        role="seksi"
    )
    db.add(new_message)

    chat.last_message_at = datetime.utcnow()
    db.commit()

    return {
        "message": "Balasan berhasil dikirim",
        "chat_id": str(chat.chat_id),
        "file_url": file_url,
        "file_type": file_type,
        "role": "seksi"
    }