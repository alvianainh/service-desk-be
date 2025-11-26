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
from uuid import UUID, uuid4
from typing import Optional, List
import aiohttp, os, mimetypes, json

router = APIRouter()
logger = logging.getLogger(__name__)


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET_NAME = "docs"
PRIORITY_OPTIONS = ["Low", "Medium", "High", "Critical"]

ASSET_BASE = "https://arise-app.my.id/api"

async def fetch_asset_from_api(token: str, asset_id: int):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{ASSET_BASE}/asset-barang",
            headers={"Authorization": f"Bearer {token}"}
        ) as res:

            if res.status != 200:
                text_err = await res.text()
                raise HTTPException(
                    status_code=400,
                    detail=f"Gagal ambil data asset dari ASET: {text_err}"
                )

            data = await res.json()

    assets = data.get("data", {}).get("data", [])

    aset = next((item for item in assets if str(item.get("id")) == str(asset_id)), None)

    if not aset:
        raise HTTPException(status_code=404, detail="Asset tidak ditemukan di API ASET")

    return aset

def upload_supabase_file(bucket_name: str, ticket_id: UUID, file: UploadFile):
    """Upload attachment ke Supabase Storage."""
    file_ext = os.path.splitext(file.filename)[1]
    file_name = f"{ticket_id}_{uuid4()}{file_ext}"
    content_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"

    file_bytes = file.file.read()

    res = supabase.storage.from_(bucket_name).upload(file_name, file_bytes, {
        "content-type": content_type
    })

    if isinstance(res, dict) and res.get("error"):
        raise Exception(res["error"])

    return supabase.storage.from_(bucket_name).get_public_url(file_name)


async def get_role_name_from_asset(role_id: int):
    url = f"{ASSET_BASE}/roles"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as res:
            if res.status != 200:
                raise HTTPException(
                    status_code=500,
                    detail="Gagal mengambil data roles dari API aset"
                )

            data = await res.json()

    roles = data.get("data", [])

    for role in roles:
        if role.get("id") == int(role_id):
            return role.get("name")

    return None


def map_role_to_ticket_source(role_name: str):
    if not role_name:
        return "masyarakat"

    role_name_lower = role_name.lower()

    if "pegawai" in role_name_lower:
        return "pegawai"

    return "masyarakat"

@router.post("/pelaporan-online")
async def create_public_report(
    id_aset_opd: int = Form(...),     
    asset_id: int = Form(...),      
    title: Optional[str] = Form(None),
    # category_id: str = Form(...),
    description: str = Form(...),
    desired_resolution: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),

    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    # local_opd = db.query(models.Opd).filter(
    #     models.Opd.id_aset == id_aset_opd
    # ).first()

    # if not local_opd:
    #     raise HTTPException(
    #         status_code=400,
    #         detail="OPD belum tersedia di sistem. Minta admin sync OPD atau upload icon."
    #     )

    role_asset_id = int(current_user.get("role_aset_id"))
    role_name = await get_role_name_from_asset(role_asset_id)
    ticket_source = role_name


    token = current_user.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Token SSO tidak tersedia")

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://arise-app.my.id/api/dinas/{id_aset_opd}",
            headers={"Authorization": f"Bearer {token}"}
        ) as res:
            if res.status != 200:
                raise HTTPException(400, "OPD tidak ditemukan di ASET")
            opd_aset = await res.json()

    opd_id_value = opd_aset.get("data", {}).get("id")
    if not opd_id_value:
        raise HTTPException(400, "Format response OPD dari API ASET tidak valid")

    aset = await fetch_asset_from_api(token, asset_id)

    asset_opd_id = (
        aset.get("dinas_id") or
        aset.get("dinas", {}).get("id") 
    )

    if str(asset_opd_id) != str(id_aset_opd):
        raise HTTPException(
            status_code=400,
            detail="Asset tidak berada di OPD yang dipilih"
        )


    asset_kode_bmd = aset.get("kode_bmd")
    asset_nomor_seri = aset.get("nomor_seri")
    asset_nama = aset.get("nama_asset") or aset.get("nama") or aset.get("asset_name")
    asset_kategori = aset.get("kategori")
    asset_subkategori_id = aset.get("asset_barang", {}).get("sub_kategori", {}).get("id")
    asset_jenis = aset.get("jenis_asset")
    asset_lokasi = aset.get("lokasi") 


    ticket_uuid = uuid4()

    new_ticket = models.Tickets(
        ticket_id=ticket_uuid,
        title=title,
        description=description,
        additional_info=desired_resolution,
        status="Open",
        created_at=datetime.utcnow(),
        # opd_id=local_opd.opd_id,
        # category_id=UUID(category_id),
        creates_id=UUID(current_user["id"]),
        ticket_source =ticket_source,
        ticket_stage="user_submit",
        opd_id_asset=opd_id_value,

        asset_aset_id=asset_id,
        asset_kode_bmd=asset_kode_bmd,
        asset_nomor_seri=asset_nomor_seri,
        asset_nama=asset_nama,
        asset_kategori=asset_kategori,
        asset_subkategori_id=asset_subkategori_id,
        asset_jenis=asset_jenis,
        asset_lokasi=asset_lokasi,     
        asset_snapshot=aset         
    )

    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)
    new_update = models.TicketUpdates(
        status_change=new_ticket.status,
        notes="Tiket dibuat melalui pelaporan online",
        makes_by_id=UUID(current_user["id"]),
        ticket_id=new_ticket.ticket_id
        # opd_id=None
    )
    db.add(new_update)
    db.commit()


    uploaded_files = []

    if files:
        for file in files:
            try:
                file_url = upload_supabase_file("docs", ticket_uuid, file)

                new_attach = models.TicketAttachment(
                    attachment_id=uuid4(),
                    has_id=ticket_uuid,
                    uploaded_at=datetime.utcnow(),
                    file_path=file_url
                )

                db.add(new_attach)
                db.commit()

                uploaded_files.append(file_url)

            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Gagal upload file {file.filename}: {str(e)}"
                )


    return {
        "message": "Laporan berhasil dibuat",
        "ticket_id": str(ticket_uuid),
        "status": "Open",
        "asset": aset,
        "opd_aset": opd_aset,
        "uploaded_files": uploaded_files
    }

# @router.post("/pelaporan-online")
# async def create_public_report(
#     opd_id: str = Form(...),
#     category_id: str = Form(...),
#     description: str = Form(...),
#     action: str = Form("submit"),
#     files: Optional[List[UploadFile]] = File(None),
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user)
# ):
#     roles = current_user.get("roles", [])
#     allowed_roles = {"masyarakat", "pegawai"}
#     if not any(role in allowed_roles for role in roles):
#         raise HTTPException(status_code=403, detail="Unauthorized: hanya masyarakat atau pegawai yang dapat membuat laporan")


#     opd_exists = db.execute(text("SELECT 1 FROM opd WHERE opd_id = :id"), {"id": opd_id}).first()
#     category_exists = db.execute(text("SELECT 1 FROM ticket_categories WHERE category_id = :id"), {"id": category_id}).first()

#     if not opd_exists or not category_exists:
#         raise HTTPException(status_code=404, detail="Invalid OPD atau kategori ID")

#     action_lower = action.lower()
#     if "masyarakat" in roles:
#         if action_lower == "draft":
#             status_val = "Draft"
#             stage_val = "user_draft"
#         elif action_lower == "submit":
#             status_val = "Open"
#             stage_val = "user_submit"
#         else:
#             raise HTTPException(status_code=400, detail="Aksi tidak valid. Gunakan 'draft' atau 'submit'.")
#     else:
#         status_val = "Open"
#         stage_val = "user_submit"

#     new_ticket = Tickets(
#         ticket_id=uuid4(),
#         description=description,
#         status=status_val,
#         opd_id=UUID(opd_id),
#         category_id=UUID(category_id),
#         creates_id=UUID(current_user["id"]),
#         ticket_source="pegawai" if "pegawai" in roles else "masyarakat",
#         ticket_stage=stage_val,
#         created_at=datetime.utcnow()
#     )

#     db.add(new_ticket)
#     db.commit()
#     db.refresh(new_ticket)

#     uploaded_files = [] 

#     if files:
#         for file in files:
#             try:
#                 file_ext = os.path.splitext(file.filename)[1]
#                 file_name = f"{new_ticket.ticket_id}_{uuid4()}{file_ext}"

#                 content_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
#                 file_bytes = await file.read()

#                 res = supabase.storage.from_("docs").upload(
#                     file_name,
#                     file_bytes,
#                     {"content-type": content_type}
#                 )

#                 if hasattr(res, "error") and res.error:
#                     raise Exception(res.error.message)
#                 if isinstance(res, dict) and res.get("error"):
#                     raise Exception(res["error"])

#                 file_url = supabase.storage.from_("docs").get_public_url(file_name)
#                 if not isinstance(file_url, str):
#                     file_url = None

#                 new_attachment = TicketAttachment(
#                     attachment_id=uuid4(),
#                     has_id=new_ticket.ticket_id,
#                     uploaded_at=datetime.utcnow(),
#                     file_path=file_url
#                 )
#                 db.add(new_attachment)
#                 db.commit()

#                 uploaded_files.append(file_url)

#             except Exception as e:
#                 raise HTTPException(status_code=500, detail=f"Gagal upload file {file.filename}: {str(e)}")

#     if "masyarakat" in roles and action_lower == "draft":
#         message = "Laporan disimpan sebagai draft. Anda dapat mengirimkannya nanti."
#     elif "masyarakat" in roles and action_lower == "submit":
#         message = "Laporan berhasil dikirim dan menunggu verifikasi dari seksi."
#     else:
#         message = "Laporan pegawai berhasil dibuat dan dikirim."

#     return {
#         "message": message,
#         "ticket_id": str(new_ticket.ticket_id),
#         "status": new_ticket.status,
#         "ticket_stage": new_ticket.ticket_stage,
#         "uploaded_files": uploaded_files 
#     }


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
async def create_ticket_pegawai_JANGAN_DIPAKE_DULU(
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
            Tickets.status != "Draft"
        )
        .all()
    )

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

    ticket = (
        db.query(Tickets)
        .filter(Tickets.ticket_id == ticket_id, Tickets.opd_id == opd_id)
        .first()
    )

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