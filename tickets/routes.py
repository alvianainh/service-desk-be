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
    action: str = Form("submit"),
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

    action_lower = action.lower()
    if action_lower == "draft":
        status_val = "Draft"
        stage_val = "user_draft"
    elif action_lower == "submit":
        status_val = "Open"
        stage_val = "user_submit"
    else:
        raise HTTPException(status_code=400, detail="Aksi tidak valid. Gunakan 'draft' atau 'submit'.")

    new_ticket = Tickets(
        ticket_id=uuid.uuid4(),
        description=description,
        status=status_val,
        opd_id=UUID(opd_id),
        category_id=UUID(category_id),
        creates_id=UUID(current_user["id"]),
        ticket_source="masyarakat",
        additional_info=additional_info,
        ticket_stage=stage_val,
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
            if not isinstance(file_url, str):
                file_url = None

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

    message = (
        "Laporan disimpan sebagai draft. Anda dapat mengirimkannya nanti."
        if action_lower == "draft"
        else "Laporan berhasil dikirim dan sedang menunggu verifikasi dari seksi."
    )

    return {
        "message": message,
        "ticket_id": str(new_ticket.ticket_id),
        "status": new_ticket.status,
        "ticket_stage": new_ticket.ticket_stage,
        "file_url": file_url
    }


@router.get("/pelaporan-online/draft")
async def get_user_drafts(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    roles = current_user.get("roles", [])
    if "masyarakat" not in roles:
        raise HTTPException(status_code=403, detail="Unauthorized: Only masyarakat can access drafts")

    user_id = current_user["id"]

    drafts = db.execute(
        text("""
            SELECT ticket_id, description, additional_info, opd_id, category_id, status, ticket_stage, created_at
            FROM tickets
            WHERE creates_id = :user_id
              AND status = 'Draft'
              AND ticket_stage = 'user_draft'
            ORDER BY created_at DESC
        """),
        {"user_id": user_id}
    ).mappings().all()

    return {"drafts": [dict(row) for row in drafts]}



@router.put("/pelaporan-online/submit/{ticket_id}")
async def submit_draft_ticket(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    roles = current_user.get("roles", [])
    if "masyarakat" not in roles:
        raise HTTPException(status_code=403, detail="Unauthorized: Only masyarakat can submit tickets")

    ticket = db.execute(
        text("""
            SELECT * FROM tickets
            WHERE ticket_id = :ticket_id
              AND creates_id = :user_id
        """),
        {"ticket_id": str(ticket_id), "user_id": current_user["id"]}
    ).mappings().first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Tiket tidak ditemukan atau bukan milik Anda")

    if ticket["status"] != "Draft" or ticket["ticket_stage"] != "user_draft":
        raise HTTPException(status_code=400, detail="Tiket ini sudah dikirim atau bukan draft")

    missing_fields = []
    if not ticket["description"]:
        missing_fields.append("description")
    if not ticket["category_id"]:
        missing_fields.append("category_id")
    if not ticket["opd_id"]:
        missing_fields.append("opd_id")

    if missing_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Tiket belum lengkap. Harap isi kolom: {', '.join(missing_fields)}"
        )

    db.execute(
        text("""
            UPDATE tickets
            SET status = 'Open',
                ticket_stage = 'user_submit',
                updated_at = NOW()
            WHERE ticket_id = :ticket_id
        """),
        {"ticket_id": str(ticket_id)}
    )
    db.commit()

    return {"message": "Tiket berhasil dikirim dari draft", "ticket_id": str(ticket_id)}


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

    tickets = (
        db.query(Tickets)
        .filter(
            Tickets.opd_id == opd_id,
            Tickets.ticket_stage.in_(["user_submit", "seksi_draft", "seksi_submit", "bidang_draft", "bidang_submit"])
        )
        .all()
    )

    return tickets

@router.get("/tickets/seksi/draft", response_model=list[TicketForSeksiSchema])
async def get_draft_tickets_seksi(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get semua draft tickets yang dibuat oleh Seksi"""
    if "seksi" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Access denied: only seksi can view this data")

    user = db.query(Users).filter(Users.id == current_user["id"]).first()
    opd_id = user.opd_id if user else None

    draft_tickets = db.query(Tickets).filter(
        Tickets.opd_id == opd_id,
        Tickets.ticket_stage == "seksi_draft"  # Hanya draft yang dibuat seksi
    ).order_by(Tickets.updated_at.desc()).all()

    return draft_tickets

@router.get("/tickets/seksi/{ticket_id}", response_model=TicketForSeksiSchema)
async def get_ticket_detail_seksi(
    ticket_id: str,  
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if "seksi" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Access denied: only seksi can view this data")

    user = db.query(Users).filter(Users.id == current_user["id"]).first()
    opd_id = user.opd_id if user else None

    ticket = db.query(Tickets).filter(
        Tickets.ticket_id == ticket_id, 
        Tickets.opd_id == opd_id
    ).first()
    
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found or access denied")

    response_data = {
        "ticket_id": ticket.ticket_id,
        "title": ticket.title, 
        "description": ticket.description, 
        "priority": ticket.priority,  
        "status": ticket.status,
        "ticket_stage": ticket.ticket_stage,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "closed_at": ticket.closed_at,
        "opd_id": ticket.opd_id,
        "category_id": ticket.category_id,
        "creates_id": ticket.creates_id,
        "ticket_source": ticket.ticket_source,
        "additional_info": ticket.additional_info,  
        "request_type": ticket.request_type,
        "assigned_to_id": ticket.assigned_to_id,
        "creator_name": None,  
        "category_name": None, 
        "attachments": []     
    }

    if ticket.creator:
        response_data["creator_name"] = f"{ticket.creator.first_name or ''} {ticket.creator.last_name or ''}".strip()

    if ticket.category:
        response_data["category_name"] = ticket.category.category_name

    if ticket.attachments:
        response_data["attachments"] = [attachment.file_path for attachment in ticket.attachments]

    return TicketForSeksiSchema(**response_data)

@router.post("/tickets/seksi/verify/{ticket_id}", response_model=TicketResponseSchema)
async def verify_ticket_seksi(
    ticket_id: UUID,
    priority: str = Form(...),
    category_id: Optional[UUID] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Verifikasi tiket langsung oleh Seksi (tanpa simpan draft dulu):
    - Status ticket = "Open" 
    - Stage = "seksi_submit"
    - Priority dan Category di-set
    - Dikirim ke Bidang
    """
    if "seksi" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: only seksi can verify tickets"
        )

    if priority not in PRIORITY_OPTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid priority, must be one of {PRIORITY_OPTIONS}"
        )

    user = db.query(Users).filter(Users.id == current_user["id"]).first()
    if not user or not user.opd_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Seksi tidak memiliki OPD yang terkait"
        )
    opd_id = user.opd_id

    ticket = db.query(Tickets).filter(
        Tickets.ticket_id == ticket_id,
        Tickets.opd_id == opd_id,
        Tickets.ticket_stage.in_(["user_submit", "seksi_draft"])  # Bisa dari user_submit atau seksi_draft
    ).first()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found, already processed, or access denied"
        )

    if category_id:
        category = db.query(TicketCategories).filter(
            TicketCategories.category_id == category_id,
            TicketCategories.opd_id == opd_id
        ).first()
        if not category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid category for this OPD"
            )
        ticket.category_id = category_id

    try:
        ticket.priority = priority
        ticket.status = "Open"                    # Status utama = Open
        ticket.ticket_stage = "seksi_submit"      # Stage = seksi_submit (ke Bidang)
        ticket.verified_id = current_user["id"]   # Catat siapa yang verifikasi
        ticket.updated_at = datetime.utcnow()

        update = TicketUpdates(
            status_change="Open",  # Status change di log = Open
            notes=notes or f"Ticket verified by Seksi with priority {priority}",
            update_time=datetime.utcnow(),
            makes_by_id=current_user["id"],
            ticket_id=ticket.ticket_id
        )
        db.add(update)
        
        db.commit()
        
        db.refresh(ticket)

        logger.info(
            f"Ticket {ticket_id} verified by seksi {current_user['id']} - "
            f"Status: {ticket.status}, Stage: {ticket.ticket_stage}, "
            f"Priority: {ticket.priority}"
        )

        return TicketResponseSchema(
            message=f"Ticket {ticket_id} verified successfully and sent to Bidang",
            ticket_id=ticket_id,
            status=ticket.status,
            ticket_stage=ticket.ticket_stage
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Error verifying ticket {ticket_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify ticket: {str(e)}"
        )

@router.post("/tickets/seksi/draft/{ticket_id}", response_model=TicketResponseSchema)
async def save_ticket_draft_seksi(
    ticket_id: UUID,
    priority: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Simpan tiket sebagai draft Seksi: Status = 'Draft', Stage = 'seksi_draft'"""
    if "seksi" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Access denied: only seksi can save drafts")

    user = db.query(Users).filter(Users.id == current_user["id"]).first()
    opd_id = user.opd_id if user else None

    ticket = db.query(Tickets).filter(
        Tickets.ticket_id == ticket_id,
        Tickets.opd_id == opd_id,
        Tickets.ticket_stage.in_(["user_submit", "seksi_draft"])  # Bisa dari user_submit atau update draft
    ).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found or access denied")

    # Update fields jika ada
    if priority:
        if priority not in PRIORITY_OPTIONS:
            raise HTTPException(status_code=400, detail=f"Invalid priority, must be one of {PRIORITY_OPTIONS}")
        ticket.priority = priority

    # Update ticket sebagai draft
    ticket.status = "Draft"
    ticket.ticket_stage = "seksi_draft"  # Tetap sebagai draft
    ticket.updated_at = datetime.utcnow()

    # Create update log
    update = TicketUpdates(
        status_change="Draft",
        update_time=datetime.utcnow(),
        makes_by_id=current_user["id"],
        ticket_id=ticket.ticket_id
    )
    db.add(update)
    db.commit()

    logger.info(f"Ticket {ticket_id} saved as draft by seksi")

    return TicketResponseSchema(
        message=f"Ticket {ticket_id} saved as draft successfully",
        ticket_id=ticket_id,
        status=ticket.status,
        ticket_stage=ticket.ticket_stage
    )

@router.post("/tickets/seksi/draft/{ticket_id}/submit", response_model=TicketResponseSchema)
async def submit_draft_seksi(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Submit draft Seksi ke Bidang: Status = 'Open', Stage = 'seksi_submit'"""
    if "seksi" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Access denied: only seksi can submit drafts")

    user = db.query(Users).filter(Users.id == current_user["id"]).first()
    opd_id = user.opd_id if user else None

    ticket = db.query(Tickets).filter(
        Tickets.ticket_id == ticket_id,
        Tickets.opd_id == opd_id,
        Tickets.ticket_stage == "seksi_draft"  # Hanya dari draft seksi
    ).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Draft ticket not found or access denied")

    # Validasi: pastikan required fields sudah diisi
    if not ticket.priority:
        raise HTTPException(status_code=400, detail="Priority must be set before submitting draft")

    # Update ticket dari draft ke submit
    ticket.status = "Open"
    ticket.ticket_stage = "seksi_submit"  # Submit ke Bidang
    ticket.verified_id = current_user["id"]
    ticket.updated_at = datetime.utcnow()

    # Create update log
    update = TicketUpdates(
        status_change="Open",
        update_time=datetime.utcnow(),
        makes_by_id=current_user["id"],
        ticket_id=ticket.ticket_id
    )
    db.add(update)
    db.commit()

    logger.info(f"Draft ticket {ticket_id} submitted to Bidang by seksi")

    return TicketResponseSchema(
        message=f"Draft ticket {ticket_id} submitted to Bidang successfully",
        ticket_id=ticket_id,
        status=ticket.status,
        ticket_stage=ticket.ticket_stage
    )

#Bidang
@router.get("/tickets/bidang", response_model=list[TicketForSeksiSchema])
async def get_tickets_for_bidang(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    roles = current_user.get("roles", [])
    if "bidang" not in roles:
        raise HTTPException(status_code=403, detail="Access denied: only bidang can view this data")

    opd_id = current_user.get("opd_id")
    if not opd_id:
        raise HTTPException(status_code=400, detail="Invalid token: opd_id missing")

    # Hanya tiket yang sudah diverifikasi seksi
    tickets = (
        db.query(Tickets)
        .filter(
            Tickets.opd_id == opd_id,
            Tickets.status == "Verified by Seksi"
        )
        .all()
    )

    return tickets

#verifikasi bidang
@router.post("/tickets/bidang/verify")
async def create_bidang_verification(
    ticket_id: UUID = Form(...),
    notes: str = Form(None),
    action: str = Form("submit"),
    is_revisi: bool = Form(False),
    is_reject: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        roles = {str(r).lower() for r in current_user.get("roles", [])}
        if "bidang" not in roles:
            raise HTTPException(status_code=403, detail="Akses ditolak: hanya Bidang yang dapat memverifikasi tiket.")

        opd_id = current_user.get("opd_id")
        if not opd_id:
            raise HTTPException(status_code=400, detail="Token tidak valid: opd_id hilang")

        user_id = current_user.get("id")
        if not user_id:
            raise HTTPException(status_code=400, detail="Token tidak valid: id pengguna hilang")
        verified_uuid = UUID(str(user_id))

        # --- Ambil tiket (harus sudah diverifikasi Seksi atau masih draft bidang) ---
        ticket = db.query(Tickets).filter(
            Tickets.ticket_id == ticket_id,
            Tickets.opd_id == opd_id,
            Tickets.status.in_(["Verified by Seksi", "Draft"])
        ).first()

        if not ticket:
            raise HTTPException(status_code=404, detail="Tiket tidak ditemukan atau belum diverifikasi oleh Seksi.")

        now = datetime.utcnow()
        action = action.lower().strip()

        # --- Tentukan status dan stage baru ---
        if action == "draft":
            new_status = "Draft"
            new_stage = "bidang_draft"
            msg = "Draft verifikasi Bidang disimpan."
        elif action == "submit":
            if is_reject:
                new_status = "Rejected by Bidang"
                new_stage = "bidang_rejected"
                msg = "Tiket ditolak oleh Bidang dan dikembalikan ke Seksi."
            elif is_revisi:
                new_status = "In Progress"
                new_stage = "seksi_revisi"
                msg = "Tiket dikembalikan ke Seksi untuk revisi."
            else:
                new_status = "Verified by Bidang"
                new_stage = "bidang_verified"
                msg = "Tiket diverifikasi oleh Bidang."
        else:
            raise HTTPException(status_code=400, detail="Aksi tidak valid. Gunakan 'draft' atau 'submit'.")

        # --- Update tiket utama ---
        ticket.status = new_status
        ticket.ticket_stage = new_stage
        ticket.verified_id = verified_uuid
        ticket.updated_at = now

        # --- Simpan histori ---
        notes_detail = notes or msg
        if is_reject:
            notes_detail += " (rejected=True)"
        if is_revisi:
            notes_detail += " (revisi=True)"

        update = TicketUpdates(
            status_change=new_status,
            notes=notes_detail,
            update_time=now,
            has_calendar_id=ticket.opd_id,
            makes_by_id=verified_uuid,
            ticket_id=ticket.ticket_id,
        )

        db.add(update)
        db.commit()
        db.refresh(ticket)

        return {
            "message": msg,
            "ticket_id": str(ticket.ticket_id),
            "status": ticket.status,
            "is_reject": is_reject,
            "is_revisi": is_revisi,
        }

    except Exception as e:
        db.rollback()
        logger.exception("Error in create_bidang_verification:")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get("/tickets/bidang/draft")
async def get_bidang_drafts(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    roles = {str(r).lower() for r in current_user.get("roles", [])}
    if "bidang" not in roles:
        raise HTTPException(status_code=403, detail="Akses ditolak: hanya Bidang yang dapat melihat draft verifikasi.")

    opd_id = current_user.get("opd_id")
    if not opd_id:
        raise HTTPException(status_code=400, detail="Token tidak valid: opd_id hilang")

    drafts = db.execute(
        text("""
            SELECT 
                ticket_id, description, additional_info, opd_id, category_id, status, 
                created_at, updated_at
            FROM tickets
            WHERE opd_id = :opd_id
              AND status = 'Draft'
              AND ticket_stage = 'bidang_draft'
            ORDER BY updated_at DESC
        """),
        {"opd_id": str(opd_id)}
    ).mappings().all()

    return {"drafts": [dict(row) for row in drafts]}

#submit draft verifikasi
@router.put("/tickets/bidang/submit/{ticket_id}")
async def submit_bidang_draft(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        roles = {str(r).lower() for r in current_user.get("roles", [])}
        if "bidang" not in roles:
            raise HTTPException(status_code=403, detail="Akses ditolak: hanya Bidang yang dapat mengirim draft verifikasi.")

        opd_id = current_user.get("opd_id")
        if not opd_id:
            raise HTTPException(status_code=400, detail="Token tidak valid: opd_id hilang")

        ticket = db.query(Tickets).filter(
            Tickets.ticket_id == ticket_id,
            Tickets.opd_id == opd_id,
            Tickets.status == "Draft",
            Tickets.ticket_stage == "bidang_draft"
        ).first()

        if not ticket:
            raise HTTPException(status_code=404, detail="Draft tiket tidak ditemukan atau bukan milik OPD Anda.")

        now = datetime.utcnow()
        ticket.status = "Verified by Bidang"
        ticket.ticket_stage = "bidang_verified"
        ticket.updated_at = now

        update = TicketUpdates(
            status_change="Verified by Bidang",
            notes="Draft diverifikasi dan dikirim ke Seksi.",
            update_time=now,
            has_calendar_id=ticket.opd_id,
            makes_by_id=UUID(str(current_user["id"])),
            ticket_id=ticket.ticket_id,
        )

        db.add(update)
        db.commit()
        db.refresh(ticket)

        return {
            "message": "Draft verifikasi Bidang berhasil dikirim.",
            "ticket_id": str(ticket.ticket_id),
            "status": ticket.status
        }

    except Exception as e:
        db.rollback()
        logger.exception("Error in submit_bidang_draft:")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

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
    current_user: dict = Depends(get_current_user) 
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