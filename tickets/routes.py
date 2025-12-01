import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Response
from sqlalchemy.orm import Session
from datetime import datetime
from . import models, schemas
from auth.database import get_db
from auth.auth import get_current_user, get_user_by_email, get_current_user_masyarakat
from tickets import models, schemas
from tickets.models import Tickets, TicketAttachment, TicketCategories, TicketUpdates
from tickets.schemas import TicketCreateSchema, TicketResponseSchema, TicketCategorySchema, TicketForSeksiSchema, TicketTrackResponse, UpdatePriority, ManualPriority
import uuid
from auth.models import Opd, Dinas, Roles
import os
from supabase import create_client, Client
from sqlalchemy import text
import mimetypes
from uuid import UUID, uuid4
from typing import Optional, List
import aiohttp, os, mimetypes, json



from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from io import BytesIO


def generate_ticket_pdf(ticket):
    buffer = BytesIO()

    # Setup PDF
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    title_style.alignment = TA_CENTER

    normal = styles['Normal']
    h2 = styles['Heading2']

    elements = []

    # Judul
    elements.append(Paragraph("Laporan Tiket Pelaporan", title_style))
    elements.append(Spacer(1, 0.5 * cm))

    # Informasi tiket
    elements.append(Paragraph(f"<b>Kode Tiket:</b> {ticket['ticket_code']}", normal))
    elements.append(Paragraph(f"<b>Judul:</b> {ticket['title']}", normal))
    elements.append(Paragraph(f"<b>Deskripsi:</b> {ticket['description']}", normal))
    elements.append(Paragraph(f"<b>Status:</b> {ticket['status']}", normal))
    elements.append(Paragraph(f"<b>Prioritas:</b> {ticket['priority']}", normal))
    elements.append(Spacer(1, 0.3 * cm))

    elements.append(Paragraph("<hr/>", normal))
    elements.append(Spacer(1, 0.3 * cm))

    # Informasi Pelapor
    elements.append(Paragraph("Informasi Pelapor", h2))
    elements.append(Paragraph(f"<b>Nama:</b> {ticket['creator']['full_name']}", normal))
    elements.append(Paragraph(f"<b>Email:</b> {ticket['creator']['email']}", normal))
    elements.append(Spacer(1, 0.3 * cm))

    # Detail Asset
    elements.append(Paragraph("Detail Asset", h2))
    elements.append(Paragraph(f"<b>Nama Asset:</b> {ticket['asset']['nama_asset']}", normal))
    elements.append(Paragraph(f"<b>Kode BMD:</b> {ticket['asset']['kode_bmd']}", normal))
    elements.append(Paragraph(f"<b>Jenis Asset:</b> {ticket['asset']['jenis_asset']}", normal))

    # Build PDF
    doc.build(elements)

    pdf = buffer.getvalue()
    buffer.close()
    return pdf


router = APIRouter()
logger = logging.getLogger(__name__)


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET_NAME = "docs"
PRIORITY_OPTIONS = ["Low", "Medium", "High", "Critical"]

ASSET_BASE = "https://arise-app.my.id/api"



# @router.get("/tickets/seksi/{ticket_id}/download")
# async def download_ticket_pdf(
#     ticket_id: str,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user)
# ):

#     ticket_data = get_ticket_detail_seksi(ticket_id, db, current_user)

#     pdf_bytes = generate_ticket_pdf(ticket_data)

#     return Response(
#         content=pdf_bytes,
#         media_type="application/pdf",
#         headers={
#             "Content-Disposition": f"attachment; filename=tiket-{ticket_id}.pdf"
#         }
#     )


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

async def fetch_subkategori_name(subkategori_id: int):
    url = "https://arise-app.my.id/api/sub-kategori"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as res:
            if res.status != 200:
                return None
            
            data = await res.json()
            items = data.get("data", [])

            for item in items:
                if item.get("id") == subkategori_id:
                    return item.get("nama")

    return None


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
    # id_aset_opd: int = Form(...),
    asset_id: int = Form(...),
    title: Optional[str] = Form(None),
    lokasi_kejadian: Optional[str] = Form(None),
    description: str = Form(...),
    expected_resolution_resolution: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    token = current_user.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Token SSO tidak tersedia")

    role_id_asset = int(current_user["role_id"])
    role = db.query(Roles).filter(Roles.role_id == role_id_asset).first()
    role_name = role.role_name if role else "pegawai"

    # async with aiohttp.ClientSession() as session:
    #     async with session.get(
    #         f"https://arise-app.my.id/api/dinas/{id_aset_opd}",
    #         headers={"Authorization": f"Bearer {token}"}
    #     ) as res:
    #         if res.status != 200:
    #             raise HTTPException(400, "OPD tidak ditemukan di ASET")
    #         opd_aset = await res.json()

    aset = await fetch_asset_from_api(token, asset_id)

    opd_id_value = aset.get("dinas_id") or aset.get("dinas", {}).get("id")
    if not opd_id_value:
        raise HTTPException(400, "Asset tidak memiliki OPD")

    # if not opd_id_value:
    #     raise HTTPException(400, "Asset tidak memiliki OPD")

    # opd_id_value = opd_aset.get("data", {}).get("id")
    # if not opd_id_value:
    #     raise HTTPException(400, "Format response OPD dari API ASET tidak valid")

    # aset = await fetch_asset_from_api(token, asset_id)
    # asset_opd_id = aset.get("dinas_id") or aset.get("dinas", {}).get("id")

    # if str(asset_opd_id) != str(id_aset_opd):
    #     raise HTTPException(400, "Asset tidak berada di OPD yang dipilih")

    asset_kode_bmd = aset.get("kode_bmd")
    asset_nomor_seri = aset.get("nomor_seri")
    asset_nama = aset.get("nama_asset") or aset.get("nama") or aset.get("asset_name")
    asset_kategori = aset.get("kategori")
    asset_subkategori_id = aset.get("asset_barang", {}).get("sub_kategori", {}).get("id")
    asset_jenis = aset.get("jenis_asset")
    asset_lokasi = aset.get("lokasi")

    # asset_subkategori_id = aset.get("asset_barang", {}).get("sub_kategori", {}).get("id")
    subkategori_nama = await fetch_subkategori_name(asset_subkategori_id)

    ticket_uuid = uuid4()

    request_type = "pelaporan_online"

    latest_ticket = db.query(models.Tickets)\
        .filter(models.Tickets.request_type == request_type)\
        .order_by(models.Tickets.created_at.desc())\
        .first()

    if latest_ticket and latest_ticket.ticket_code:
        try:
            last_number = int(latest_ticket.ticket_code.split("-")[2])
        except:
            last_number = 0
        next_number = f"{last_number + 1:04d}"
    else:
        next_number = "0001"

    ticket_code = f"SVD-PO-{next_number}-PG"

    new_ticket = models.Tickets(
        ticket_id=ticket_uuid,
        title=title,
        description=description,
        expected_resolution=expected_resolution,
        status="Open",
        created_at=datetime.utcnow(),
        creates_id=UUID(current_user["id"]),
        ticket_stage="Draft",
        ticket_source="Pegawai",
        opd_id_asset=opd_id_value,
        opd_id_tickets=opd_id_value, 
        asset_id=asset_id,
        kode_bmd_asset=asset_kode_bmd,
        nomor_seri_asset=asset_nomor_seri,
        nama_asset=asset_nama,
        kategori_asset=asset_kategori,
        subkategori_id_asset=asset_subkategori_id,
        subkategori_nama_asset=subkategori_nama,
        jenis_asset=asset_jenis,
        lokasi_asset=asset_lokasi,
        lokasi_kejadian=lokasi_kejadian,
        metadata_asset=aset,
        role_id_source=role_id_asset,
        request_type=request_type,
        ticket_code=ticket_code 
    )
    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)

    new_update = models.TicketUpdates(
        status_change=new_ticket.status,
        notes="Tiket dibuat melalui pelaporan online",
        makes_by_id=UUID(current_user["id"]),
        ticket_id=new_ticket.ticket_id
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
        "ticket_code": new_ticket.ticket_code, 
        "status": "Open",
        "asset": aset,
        # "opd_aset": opd_aset,
        "uploaded_files": uploaded_files
    }


@router.post("/pelaporan-online-masyarakat")
async def create_public_report_masyarakat(
    title: Optional[str] = Form(None),
    id_opd: int = Form(...),
    description: str = Form(...),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_masyarakat)
):
    if current_user.get("role_name", "").lower() != "masyarakat":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hanya masyarakat yang dapat membuat laporan ini"
        )

    if not description.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kolom 'description' wajib diisi")

    dinas = db.query(Dinas).filter(Dinas.id == id_opd).first()
    if not dinas:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dinas tidak ditemukan di sistem")

    ticket_uuid = uuid4()

    request_type = "pelaporan_online"

    latest_ticket = db.query(models.Tickets)\
        .filter(models.Tickets.request_type == request_type)\
        .order_by(models.Tickets.created_at.desc())\
        .first()

    if latest_ticket and latest_ticket.ticket_code:
        try:
            last_number = int(latest_ticket.ticket_code.split("-")[2])
        except:
            last_number = 0
        next_number = f"{last_number + 1:04d}"
    else:
        next_number = "0001"

    ticket_code = f"SVD-PO-{next_number}-MA"

    new_ticket = Tickets(
        ticket_id=ticket_uuid,
        title=title,
        description=description,
        status="Open",
        ticket_source="Masyarakat",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        creates_id=current_user.get("id"),
        request_type=request_type,
        ticket_stage="Draft",
        opd_id_asset=None,                
        opd_id_tickets=dinas.id,        
        role_id_source=current_user.get("role_id"),
        ticket_code=ticket_code
    )
    db.add(new_ticket)

    new_update = TicketUpdates(
        status_change=new_ticket.status,
        notes="Tiket dibuat melalui pelaporan online masyarakat",
        makes_by_id=current_user.get("id"),
        ticket_id=new_ticket.ticket_id
    )
    db.add(new_update)

    db.commit()
    db.refresh(new_ticket)

    uploaded_files = []
    if files:
        for file in files:
            try:
                file_url = upload_supabase_file("docs", str(ticket_uuid), file)
                new_attach = TicketAttachment(
                    attachment_id=uuid4(),
                    has_id=ticket_uuid,
                    uploaded_at=datetime.utcnow(),
                    file_path=file_url
                )
                db.add(new_attach)
                uploaded_files.append(file_url)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Gagal upload file {file.filename}: {str(e)}"
                )
        db.commit()  

    return {
        "message": "Laporan berhasil dibuat",
        "ticket_id": str(ticket_uuid),
        "ticket_code": new_ticket.ticket_code, 
        "status": new_ticket.status,
        "uploaded_files": uploaded_files
    }



#SEKSI
@router.get("/tickets/seksi")
def get_tickets_for_seksi(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya seksi yang dapat melihat daftar tiket"
        )

    seksi_opd_id = current_user.get("dinas_id")
    if not seksi_opd_id:
        raise HTTPException(
            status_code=400,
            detail="User tidak memiliki OPD"
        )

    tickets = (
        db.query(models.Tickets)
        .filter(models.Tickets.opd_id_tickets == seksi_opd_id)
        .filter(models.Tickets.request_type == "pelaporan_online")   # ✅ filter khusus masyarakat
        .order_by(models.Tickets.created_at.desc())
        .all()
    )

    return {
        "total": len(tickets),
        "data": [
            {
                "ticket_id": str(t.ticket_id),
                "ticket_code": t.ticket_code,
                "title": t.title,
                "description": t.description,
                "status": t.status,
                "stage": t.ticket_stage,
                "created_at": t.created_at,
                "ticket_source": t.ticket_source,

                "opd_id_tickets": t.opd_id_tickets,
                "lokasi_kejadian": t.lokasi_kejadian,

                "creator": {
                    "user_id": str(t.creates_id) if t.creates_id else None,
                    "full_name": t.creates_user.full_name if t.creates_user else None,
                    "profile": t.creates_user.profile_url if t.creates_user else None,
                    "email": t.creates_user.email if t.creates_user else None,
                },

                "asset": {
                    "asset_id": t.asset_id,
                    "nama_asset": t.nama_asset,
                    "kode_bmd": t.kode_bmd_asset,
                    "nomor_seri": t.nomor_seri_asset,
                    "kategori": t.kategori_asset,
                    "subkategori_id": t.subkategori_id_asset,
                    "subkategori_nama": t.subkategori_nama_asset,
                    "jenis_asset": t.jenis_asset,
                    "lokasi_asset": t.lokasi_asset,
                    "opd_id_asset": t.opd_id_asset,
                }
            }
            for t in tickets
        ]
    }



# DETAIL SEKSI
@router.get("/tickets/seksi/{ticket_id}")
def get_ticket_detail_seksi(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya seksi yang dapat melihat detail tiket"
        )

    seksi_opd_id = current_user.get("dinas_id")
    if not seksi_opd_id:
        raise HTTPException(
            status_code=400,
            detail="User tidak memiliki OPD"
        )

    ticket = (
        db.query(models.Tickets)
        .filter(models.Tickets.ticket_id == ticket_id)
        .filter(models.Tickets.opd_id_tickets == seksi_opd_id)
        .filter(models.Tickets.request_type == "pelaporan_online")
        .first()
    )

    if not ticket:
        raise HTTPException(
            status_code=404,
            detail="Tiket tidak ditemukan atau tidak memiliki akses"
        )

    attachments = (
        db.query(models.TicketAttachment)
        .filter(models.TicketAttachment.has_id == ticket_id)
        .all()
    )

    return {
        "ticket_id": str(ticket.ticket_id),
        "ticket_code": ticket.ticket_code,
        "title": ticket.title,
        "description": ticket.description,
        "status": ticket.status,
        "stage": ticket.ticket_stage,
        "created_at": ticket.created_at,
        "priority": ticket.priority,

        "opd_id_tickets": ticket.opd_id_tickets,
        "lokasi_kejadian": ticket.lokasi_kejadian,
        "expected_resolution": ticket.expected_resolution,
        "ticket_source": ticket.ticket_source,
        
        "creator": {
            "user_id": str(ticket.creates_id) if ticket.creates_id else None,
            "full_name": ticket.creates_user.full_name if ticket.creates_user else None,
            "profile": ticket.creates_user.profile_url if ticket.creates_user else None,
            "email": ticket.creates_user.email if ticket.creates_user else None,
        },

        "asset": {
            "asset_id": ticket.asset_id,
            "nama_asset": ticket.nama_asset,
            "kode_bmd": ticket.kode_bmd_asset,
            "nomor_seri": ticket.nomor_seri_asset,
            "kategori": ticket.kategori_asset,
            "subkategori_id": ticket.subkategori_id_asset,
            "subkategori_nama": ticket.subkategori_nama_asset,
            "jenis_asset": ticket.jenis_asset,
            "lokasi_asset": ticket.lokasi_asset,
            "opd_id_asset": ticket.opd_id_asset,
        },
        "files": [
            {
                "attachment_id": str(a.attachment_id),
                "file_path": a.file_path,
                "uploaded_at": a.uploaded_at
            }
            for a in attachments
        ]
    }



@router.put("/tickets/{ticket_id}/priority")
def update_ticket_priority(
    ticket_id: str,
    payload: schemas.UpdatePriority,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya seksi yang dapat mengubah prioritas"
        )

    ticket = (
        db.query(models.Tickets)
        .filter(models.Tickets.ticket_id == ticket_id)
        .first()
    )

    if not ticket:
        raise HTTPException(404, "Tiket tidak ditemukan")


    if ticket.ticket_source != "Pegawai":
        raise HTTPException(
            status_code=400,
            detail="Tiket bukan berasal dari Pegawai, gunakan endpoint /priority/masyarakat."
        )

    if ticket.priority is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Prioritas sudah diset menjadi '{ticket.priority}' dan tidak dapat diubah lagi."
        )

    urgency = payload.urgency
    impact = payload.impact
    score = urgency * impact

    if score == 9:
        priority = "Critical"
    elif score == 6:
        priority = "High"
    elif score in (3, 4):
        priority = "Medium"
    elif score in (1, 2):
        priority = "Low"
    else:
        raise HTTPException(400, "Nilai urgensi * dampak tidak valid")


    ticket.priority = priority
    ticket.priority_score = score 
    
    ticket.ticket_stage = "pending"
    ticket.status = "verified by seksi"


    db.commit()
    db.refresh(ticket)

    return {
        "message": "Prioritas tiket berhasil ditetapkan",
        "ticket_id": ticket_id,
        "priority": ticket.priority,
        "score": score
    }


@router.put("/tickets/{ticket_id}/priority/masyarakat")
def set_priority_masyarakat(
    ticket_id: str,
    payload: schemas.ManualPriority,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya seksi yang dapat mengubah prioritas"
        )

    ticket = db.query(models.Tickets).filter_by(ticket_id=ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Tiket tidak ditemukan")

    if ticket.ticket_source != "Masyarakat":
        raise HTTPException(
            status_code=400,
            detail="Tiket bukan berasal dari masyarakat, gunakan endpoint matrix."
        )


    if ticket.priority is not None:
        raise HTTPException(
            400,
            f"Prioritas sudah ditetapkan menjadi '{ticket.priority}' dan tidak dapat diubah lagi."
        )

    valid_priorities = ["low", "medium", "high", "critical"]
    if payload.priority.lower() not in valid_priorities:
        raise HTTPException(
            400,
            "Prioritas tidak valid, harus salah satu: low, medium, high, critical."
        )

    ticket.priority = payload.priority.capitalize()  
    ticket.ticket_stage = "pending"
    ticket.status = "verified by seksi"

    db.commit()
    db.refresh(ticket)

    return {
        "message": "Prioritas tiket masyarakat berhasil ditetapkan",
        "ticket_id": ticket_id,
        "priority": ticket.priority
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
async def get_ticket_detail_seksi_temp(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if "admin dinas" not in current_user.get("roles", []):
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