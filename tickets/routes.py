import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from datetime import datetime
from . import models, schemas
from auth.database import get_db
from auth.auth import get_current_user, get_user_by_email
from tickets import models, schemas
from tickets.models import Tickets, TicketAttachment, TicketCategories
from tickets.schemas import TicketCreateSchema, TicketResponseSchema, TicketCategorySchema
import uuid
import os
from supabase import create_client, Client
from sqlalchemy import text
import mimetypes

router = APIRouter()
logger = logging.getLogger(__name__)


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@router.post("/report")
async def create_public_report(
    opd_id: str = Form(...),
    category_id: str = Form(...),
    description: str = Form(...),
    additional_info: str = Form(None),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    # Validasi role
    roles = current_user.get("roles", [])
    if "masyarakat" not in roles:
        raise HTTPException(status_code=403, detail="Unauthorized: Only masyarakat can create reports")

    # Cek validitas OPD & kategori
    opd_exists = db.execute(text("SELECT 1 FROM opd WHERE opd_id = :id"), {"id": opd_id}).first()
    category_exists = db.execute(text("SELECT 1 FROM ticket_categories WHERE category_id = :id"), {"id": category_id}).first()

    if not opd_exists or not category_exists:
        raise HTTPException(status_code=404, detail="Invalid OPD or category ID")

    # Buat tiket baru
    new_ticket = Tickets(
        ticket_id=uuid.uuid4(),
        description=description,
        status="Open",
        opd_id=opd_id,
        category_id=category_id,
        creates_id=current_user["id"],
        ticket_source="masyarakat",
        additional_info=additional_info,
        created_at=datetime.utcnow()
    )
    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)

    file_url = None
    if file:
        try:
            file_ext = os.path.splitext(file.filename)[1]
            file_name = f"{new_ticket.ticket_id}{file_ext}"

            # Tentukan MIME type otomatis
            content_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"

            # Baca file bytes
            file_bytes = await file.read()

            # Upload ke Supabase Storage dengan MIME type
            res = supabase.storage.from_("docs").upload(
                file_name,
                file_bytes,
                {"content-type": content_type}
            )

            # Tangani error upload
            if hasattr(res, "error") and res.error:
                raise Exception(res.error.message)
            if isinstance(res, dict) and res.get("error"):
                raise Exception(res["error"])

            # Dapatkan URL publik
            file_url = supabase.storage.from_("docs").get_public_url(file_name)

            # Simpan metadata file ke DB
            new_attachment = TicketAttachment(
                attachment_id=uuid.uuid4(),
                has_id=new_ticket.ticket_id,
                uploaded_at=datetime.utcnow(),
                file_path=file_url
            )
            db.add(new_attachment)
            db.commit()

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

    # Return hasil
    return {
        "message": "Laporan berhasil dikirim",
        "ticket_id": str(new_ticket.ticket_id),
        "status": new_ticket.status,
        "file_url": file_url
    }