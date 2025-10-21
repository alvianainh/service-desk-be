import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from datetime import datetime
from . import models, schemas
from auth.database import get_db
from auth.auth import get_current_user, get_user_by_email
from tickets import models, schemas
from tickets.models import Tickets, TicketAttachment, TicketCategories, TicketUpdates
from tickets.schemas import TicketCreateSchema, TicketResponseSchema, TicketCategorySchema, TicketForSeksiSchema, TicketTrackResponse
import uuid
from auth.models import Opd
import os
from supabase import create_client, Client
from sqlalchemy import text
import mimetypes
from uuid import UUID

router = APIRouter()
logger = logging.getLogger(__name__)


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET_NAME = "docs"
PRIORITY_OPTIONS = ["Low", "Medium", "High", "Critical"]

@router.post("/pelaporan-online")
async def create_public_report(
    opd_id: str = Form(...),
    category_id: str = Form(...),
    description: str = Form(...),
    additional_info: str = Form(None),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    roles = current_user.get("roles", [])
    if "masyarakat" not in roles:
        raise HTTPException(status_code=403, detail="Unauthorized: Only masyarakat can create reports")

    opd_exists = db.execute(text("SELECT 1 FROM opd WHERE opd_id = :id"), {"id": opd_id}).first()
    category_exists = db.execute(text("SELECT 1 FROM ticket_categories WHERE category_id = :id"), {"id": category_id}).first()

    if not opd_exists or not category_exists:
        raise HTTPException(status_code=404, detail="Invalid OPD or category ID")

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

            content_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"

            file_bytes = await file.read()

            res = supabase.storage.from_("docs").upload(
                file_name,
                file_bytes,
                {"content-type": content_type}
            )

            if hasattr(res, "error") and res.error:
                raise Exception(res.error.message)
            if isinstance(res, dict) and res.get("error"):
                raise Exception(res["error"])

            file_url = supabase.storage.from_("docs").get_public_url(file_name)

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

    return {
        "message": "Laporan berhasil dikirim",
        "ticket_id": str(new_ticket.ticket_id),
        "status": new_ticket.status,
        "file_url": file_url
    }


@router.get("/ticket-categories", response_model=list[TicketCategorySchema])
async def get_ticket_categories(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):


    opd_id = current_user.get("opd_id")

    if not opd_id:
        raise HTTPException(status_code=400, detail="Invalid token: opd_id missing")

    categories = db.query(TicketCategories).filter(TicketCategories.opd_id == opd_id).all()

    return categories


@router.post("/pengajuan-pelayanan")
async def create_ticket_pegawai(
    request_type: str = Form(...),             
    description: str = Form(...),
    additional_info: str = Form(None),
    opd_id: str = Form(...),
    creates_id: str = Form(...),
    priority: str = Form("Medium"),
    file: UploadFile = None
):
    try:
        file_path = None
        if file:
            ext = os.path.splitext(file.filename)[1]
            filename = f"{uuid.uuid4()}{ext}"
            full_path = f"pegawai/{filename}"

            res = supabase.storage.from_(BUCKET_NAME).upload(
                full_path, await file.read(), {"content-type": file.content_type}
            )

            if res.get("error"):
                raise HTTPException(status_code=500, detail=f"File upload failed: {res['error']['message']}")

            file_path = f"{BUCKET_NAME}/{full_path}"

        new_ticket = {
            "title": request_type.replace("_", " ").title(),
            "description": description,
            "priority": priority,
            "status": "Open",
            "ticket_source": "pegawai",
            "request_type": request_type,
            "creates_id": creates_id,
            "opd_id": opd_id,
            "additional_info": additional_info,
            "created_at": datetime.utcnow().isoformat()
        }

        ticket_res = supabase.table("tickets").insert(new_ticket).execute()
        if not ticket_res.data:
            raise HTTPException(status_code=500, detail="Ticket creation failed")

        ticket_id = ticket_res.data[0]["ticket_id"]

        if file_path:
            supabase.table("ticket_attachment").insert({
                "uploaded_at": datetime.utcnow().isoformat(),
                "file_path": file_path,
                "has_id": ticket_id
            }).execute()

        return {
            "ticket_id": ticket_id,
            "message": "Ticket created successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



#SEKSI
@router.get("/tickets/seksi", response_model=list[TicketForSeksiSchema])
async def get_tickets_for_seksi(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    roles = current_user.get("roles", [])
    if "seksi" not in roles:
        raise HTTPException(status_code=403, detail="Access denied: only seksi can view this data")

    opd_id = current_user.get("opd_id")
    if not opd_id:
        raise HTTPException(status_code=400, detail="Invalid token: opd_id missing")

    tickets = db.query(Tickets).filter(Tickets.opd_id == opd_id).all()
    return tickets


@router.get("/tickets/seksi/{ticket_id}", response_model=TicketForSeksiSchema)
async def get_ticket_detail_seksi(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if "seksi" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Access denied: only seksi can view this data")

    opd_id = current_user.get("opd_id")
    ticket = db.query(Tickets).filter(Tickets.ticket_id == ticket_id, Tickets.opd_id == opd_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found or access denied")

    return ticket


@router.post("/tickets/seksi/verify/{ticket_id}")
async def verify_ticket_seksi(
    ticket_id: str,
    priority: str = Form(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if "seksi" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Access denied: only seksi can verify tickets")

    if priority not in PRIORITY_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid priority, must be one of {PRIORITY_OPTIONS}")

    opd_id = current_user.get("opd_id")
    ticket = db.query(Tickets).filter(Tickets.ticket_id == ticket_id, Tickets.opd_id == opd_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found or access denied")

    ticket.priority = priority
    ticket.status = "Verified by Seksi"
    ticket.updated_at = datetime.utcnow()
    db.add(ticket)

    update = TicketUpdates(
        status_change=ticket.status,
        notes=f"Verified by Seksi with priority {priority}",
        update_time=datetime.utcnow(),
        has_calendar_id=ticket.opd_id,
        makes_by_id=current_user["id"],
        ticket_id=ticket.ticket_id
    )
    db.add(update)
    db.commit()

    return {
        "message": f"Ticket {ticket_id} verified successfully",
        "ticket_id": ticket_id,
        "status": ticket.status,
        "priority": ticket.priority
    }

# Tracking tiket
@router.get(
    "/track/{ticket_id}",
    tags=["tickets"],
    summary="Track Ticket Status",
    response_model=schemas.TicketTrackResponse
)
async def track_ticket(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)  # ⬅️ tambahkan ini
):
    ticket = (
        db.query(Tickets)
        .join(TicketCategories, Tickets.category_id == TicketCategories.category_id)
        .join(Opd, Tickets.opd_id == Opd.opd_id)
        .filter(Tickets.ticket_id == ticket_id)
        .first()
    )

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return schemas.TicketTrackResponse(
        ticket_id=ticket.ticket_id,
        status=ticket.status,
        jenis_laporan=ticket.category.category_name if ticket.category else None,
        opd=ticket.opd.opd_name if ticket.opd else None,
    )
