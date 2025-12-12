import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Response
from sqlalchemy.orm import Session
from datetime import datetime, time
from . import models, schemas
from auth.database import get_db
from auth.auth import get_current_user, get_user_by_email, get_current_user_masyarakat, get_current_user_universal
from tickets import models, schemas
from tickets.models import Tickets, TicketAttachment, TicketCategories, TicketUpdates, TeknisiTags, TeknisiLevels, TicketRatings, Notifications
from tickets.schemas import TicketCreateSchema, TicketResponseSchema, TicketCategorySchema, TicketForSeksiSchema, TicketTrackResponse, UpdatePriority, ManualPriority, RejectReasonSeksi, RejectReasonBidang, AssignTeknisiSchema
import uuid
from auth.models import Opd, Dinas, Roles, Users
import os
from supabase import create_client, Client
from sqlalchemy import text, or_
import mimetypes
from uuid import UUID, uuid4
from typing import Optional, List
import aiohttp, os, mimetypes, json
import asyncio
from websocket.notifier import push_notification




# from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
# from reportlab.lib.styles import getSampleStyleSheet
# from reportlab.lib.pagesizes import A4
# from reportlab.lib.units import cm
# from reportlab.lib.enums import TA_CENTER
# from reportlab.lib import colors
# from io import BytesIO


# def generate_ticket_pdf(ticket):
#     buffer = BytesIO()

#     doc = SimpleDocTemplate(
#         buffer,
#         pagesize=A4,
#         leftMargin=2 * cm,
#         rightMargin=2 * cm,
#         topMargin=2 * cm,
#         bottomMargin=2 * cm,
#     )

#     styles = getSampleStyleSheet()
#     title_style = styles['Heading1']
#     title_style.alignment = TA_CENTER

#     normal = styles['Normal']
#     h2 = styles['Heading2']

#     elements = []

#     elements.append(Paragraph("Laporan Tiket Pelaporan", title_style))
#     elements.append(Spacer(1, 0.5 * cm))

#     elements.append(Paragraph(f"<b>Kode Tiket:</b> {ticket['ticket_code']}", normal))
#     elements.append(Paragraph(f"<b>Judul:</b> {ticket['title']}", normal))
#     elements.append(Paragraph(f"<b>Deskripsi:</b> {ticket['description']}", normal))
#     elements.append(Paragraph(f"<b>Status:</b> {ticket['status']}", normal))
#     elements.append(Paragraph(f"<b>Prioritas:</b> {ticket['priority']}", normal))
#     elements.append(Spacer(1, 0.3 * cm))

#     elements.append(Paragraph("<hr/>", normal))
#     elements.append(Spacer(1, 0.3 * cm))

#     elements.append(Paragraph("Informasi Pelapor", h2))
#     elements.append(Paragraph(f"<b>Nama:</b> {ticket['creator']['full_name']}", normal))
#     elements.append(Paragraph(f"<b>Email:</b> {ticket['creator']['email']}", normal))
#     elements.append(Spacer(1, 0.3 * cm))

#     elements.append(Paragraph("Detail Asset", h2))
#     elements.append(Paragraph(f"<b>Nama Asset:</b> {ticket['asset']['nama_asset']}", normal))
#     elements.append(Paragraph(f"<b>Kode BMD:</b> {ticket['asset']['kode_bmd']}", normal))
#     elements.append(Paragraph(f"<b>Jenis Asset:</b> {ticket['asset']['jenis_asset']}", normal))

#     doc.build(elements)

#     pdf = buffer.getvalue()
#     buffer.close()
#     return pdf


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


def add_ticket_history(
    db,
    ticket,
    new_status: str,
    old_status: str, 
    updated_by: UUID,
    extra: dict = None
):
    history = models.TicketHistory(
        ticket_id=ticket.ticket_id,
        old_status=old_status,
        new_status=new_status,
        updated_by_user_id=updated_by,
        pengerjaan_awal=ticket.pengerjaan_awal,
        pengerjaan_akhir=ticket.pengerjaan_akhir,
        pengerjaan_awal_teknisi=ticket.pengerjaan_awal_teknisi,
        pengerjaan_akhir_teknisi=ticket.pengerjaan_akhir_teknisi,
        extra_data=extra or {}
    )

    db.add(history)
    db.commit()
    db.refresh(history)

    return history

async def update_ticket_status(db, ticket, new_status, updated_by):
    old = ticket.status_ticket_pengguna
    ticket.status_ticket_pengguna = new_status
    db.commit()

    notif = Notifications(
        user_id=ticket.creates_id,
        ticket_id=ticket.ticket_id,
        status=new_status,
        message=f"Status tiket {ticket.ticket_code} berubah dari {old} ke {new_status}"
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    payload = {
        "id": str(notif.id),
        "ticket_id": str(ticket.ticket_id),
        "ticket_code": ticket.ticket_code,
        "old_status": old,
        "new_status": new_status,
        "message": notif.message,
        "user_id": str(ticket.creates_id)
    }

    asyncio.create_task(push_notification(payload))




#MASYARAKAT
@router.get("/tickets/masyarakat/finished")
def get_finished_tickets_for_masyarakat(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    user_id = current_user.get("id")

    tickets = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.creates_id == user_id,
            or_(
                models.Tickets.status == "selesai",
                models.Tickets.status == "rejected",
            ),
            models.Tickets.request_type.in_(["pelaporan_online", "pengajuan_pelayanan"])
        )
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
                "priority": t.priority,
                "status": t.status,
                "rejection_reason_seksi": t.rejection_reason_seksi,
                "created_at": t.created_at,
                "pengerjaan_awal": t.pengerjaan_awal,
                "pengerjaan_akhir": t.pengerjaan_akhir,
                "pengerjaan_awal_teknisi": t.pengerjaan_awal_teknisi,
                "pengerjaan_akhir_teknisi": t.pengerjaan_akhir_teknisi,
                "status_ticket_pengguna": t.status_ticket_pengguna,
                "status_ticket_seksi": t.status_ticket_seksi,
                "status_ticket_teknisi": t.status_ticket_teknisi,
                "nik": (
                    db.query(Users)
                    .filter(Users.id == t.creates_id)
                    .first()
                ).nik
                if db.query(Users).filter(Users.id == t.creates_id).first()
                else None,

                "rating": (
                    lambda r: {
                        "rating": r.rating,
                        "comment": r.comment,
                        "created_at": r.created_at,
                    } if r else None
                )(
                    db.query(models.TicketRatings)
                    .filter(models.TicketRatings.ticket_id == t.ticket_id)
                    .first()
                ),
            }
            for t in tickets
        ]
    }



@router.get("/tickets/masyarakat/{ticket_id}")
def get_ticket_detail_for_pengguna(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    user_id = current_user.get("id")

    ticket = (
        db.query(models.Tickets)
        .filter(models.Tickets.ticket_id == ticket_id)
        .first()
    )

    if not ticket:
        raise HTTPException(status_code=404, detail="Tiket tidak ditemukan.")

    if str(ticket.creates_id) != str(user_id):
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Anda bukan pembuat tiket ini."
        )

    allowed_status = ["selesai", "rejected"]

    if ticket.status not in allowed_status:
        raise HTTPException(
            status_code=400,
            detail="Tiket belum selesai atau ditolak. Tidak dapat ditampilkan di halaman pengguna."
        )

    rating = (
        db.query(models.TicketRatings)
        .filter(models.TicketRatings.ticket_id == ticket_id)
        .first()
    )

    attachments = ticket.attachments if hasattr(ticket, "attachments") else []

    return {
        "ticket_id": str(ticket.ticket_id),
        "ticket_code": ticket.ticket_code,
        "title": ticket.title,
        "description": ticket.description,
        "priority": ticket.priority,
        "status": ticket.status,
        "rejection_reason_seksi": ticket.rejection_reason_seksi,
        "created_at": ticket.created_at,
        "lokasi_kejadian": ticket.lokasi_kejadian,
        "expected_resolution": ticket.expected_resolution,

        "pengerjaan_awal": ticket.pengerjaan_awal,
        "pengerjaan_akhir": ticket.pengerjaan_akhir_teknisi,  

        "status_ticket_pengguna": ticket.status_ticket_pengguna,
        "status_ticket_seksi": ticket.status_ticket_seksi,
        "status_ticket_teknisi": ticket.status_ticket_teknisi,

        "rating": {
            "rating": rating.rating if rating else None,
            "comment": rating.comment if rating else None,
            "created_at": rating.created_at if rating else None,
        },

        "creator": {
            "user_id": str(ticket.creates_id),
            "full_name": current_user.get("full_name"),
            "email": current_user.get("email"),
            "profile": current_user.get("profile_url"),
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
                "uploaded_at": a.uploaded_at,
            }
            for a in attachments
        ]
    }


@router.post("/tickets/{ticket_id}/rating")
def give_ticket_rating(
    ticket_id: str,
    rating: int = Form(...),
    comment: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    user_id = current_user.get("id")

    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating harus 1 sampai 5.")

    ticket = db.query(models.Tickets).filter(models.Tickets.ticket_id == ticket_id).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Tiket tidak ditemukan.")

    if str(ticket.creates_id) != str(user_id):
        raise HTTPException(status_code=403, detail="Anda bukan pembuat tiket ini.")

    if ticket.status not in ["selesai"]:
        raise HTTPException(status_code=400, detail="Tiket ditolak, tidak bisa diberi rating.")

    existing_rating = (
        db.query(models.TicketRatings)
        .filter(models.TicketRatings.ticket_id == ticket_id)
        .first()
    )

    if existing_rating:
        raise HTTPException(status_code=400, detail="Tiket sudah diberi rating.")

    new_rating = models.TicketRatings(
        ticket_id=ticket_id,
        user_id=user_id,
        rating=rating,
        comment=comment
    )

    db.add(new_rating)
    db.commit()
    db.refresh(new_rating)

    return {
        "status": "success",
        "message": "Rating berhasil disimpan",
        "data": {
            "rating_id": str(new_rating.rating_id),
            "ticket_id": ticket_id,
            "rating": rating,
            "comment": comment,
            "created_at": new_rating.created_at
        }
    }




#PEGAWAI
@router.get("/tickets/pegawai/finished")
def get_finished_tickets_for_user(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    user_id = current_user.get("id")

    tickets = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.creates_id == user_id,
            or_(
                models.Tickets.status == "selesai",
                models.Tickets.status == "rejected",
            ),
            models.Tickets.request_type.in_(["pelaporan_online", "pengajuan_pelayanan"])
        )
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
                "priority": t.priority,
                "status": t.status,
                "rejection_reason_seksi": t.rejection_reason_seksi,
                "created_at": t.created_at,
                "pengerjaan_awal": t.pengerjaan_awal,
                "pengerjaan_akhir": t.pengerjaan_akhir,
                "pengerjaan_awal_teknisi": t.pengerjaan_awal_teknisi,
                "pengerjaan_akhir_teknisi": t.pengerjaan_akhir_teknisi,
                "status_ticket_pengguna": t.status_ticket_pengguna,
                "status_ticket_seksi": t.status_ticket_seksi,
                "status_ticket_teknisi": t.status_ticket_teknisi,

                "rating": (
                    lambda r: {
                        "rating": r.rating,
                        "comment": r.comment,
                        "created_at": r.created_at,
                    } if r else None
                )(
                    db.query(models.TicketRatings)
                    .filter(models.TicketRatings.ticket_id == t.ticket_id)
                    .first()
                ),
            }
            for t in tickets
        ]
    }



@router.get("/tickets/pegawai/{ticket_id}")
def get_ticket_detail_for_pengguna(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    user_id = current_user.get("id")

    ticket = (
        db.query(models.Tickets)
        .filter(models.Tickets.ticket_id == ticket_id)
        .first()
    )

    if not ticket:
        raise HTTPException(status_code=404, detail="Tiket tidak ditemukan.")

    if str(ticket.creates_id) != str(user_id):
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Anda bukan pembuat tiket ini."
        )

    allowed_status = ["selesai", "rejected"]

    if ticket.status not in allowed_status:
        raise HTTPException(
            status_code=400,
            detail="Tiket belum selesai atau ditolak. Tidak dapat ditampilkan di halaman pengguna."
        )
    attachments = ticket.attachments if hasattr(ticket, "attachments") else []

    return {
        "ticket_id": str(ticket.ticket_id),
        "ticket_code": ticket.ticket_code,
        "title": ticket.title,
        "description": ticket.description,
        "priority": ticket.priority,
        "status": ticket.status,
        "rejection_reason_seksi": ticket.rejection_reason_seksi,
        "created_at": ticket.created_at,
        "lokasi_kejadian": ticket.lokasi_kejadian,
        "expected_resolution": ticket.expected_resolution,

        "pengerjaan_awal": ticket.pengerjaan_awal,
        "pengerjaan_akhir": ticket.pengerjaan_akhir_teknisi,  

        "status_ticket_pengguna": ticket.status_ticket_pengguna,
        "status_ticket_seksi": ticket.status_ticket_seksi,
        "status_ticket_teknisi": ticket.status_ticket_teknisi,
        "rejection_reason_seksi": ticket.rejection_reason_seksi,

        "creator": {
            "user_id": str(ticket.creates_id),
            "full_name": current_user.get("full_name"),
            "email": current_user.get("email"),
            "profile": current_user.get("profile_url"),
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
                "uploaded_at": a.uploaded_at,
            }
            for a in attachments
        ]
    }


@router.get("/track-ticket/{ticket_code}")
async def track_ticket(
    ticket_code: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    user_id = current_user.get("id")


    ticket = (
        db.query(models.Tickets)
        .filter(models.Tickets.ticket_code == ticket_code)
        .first()
    )

    if not ticket:
        raise HTTPException(status_code=404, detail="Tiket tidak ditemukan.")

    if str(ticket.creates_id) != str(user_id):
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Anda bukan pembuat tiket ini."
        )

    opd = (
        db.query(Dinas)
        .filter(Dinas.id == ticket.opd_id_tickets)
        .first()
    )

    opd_name = opd.nama if opd else None

    return {
        "ticket_code": ticket.ticket_code,
        "status_ticket_pengguna": ticket.status_ticket_pengguna,
        "request_type": ticket.request_type,
        "opd_id": ticket.opd_id_tickets,
        "opd_name": opd_name,
    }



@router.post("/tickets/{ticket_id}/rating")
def give_ticket_rating(
    ticket_id: str,
    rating: int = Form(...),
    comment: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    user_id = current_user.get("id")

    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating harus 1 sampai 5.")

    ticket = db.query(models.Tickets).filter(models.Tickets.ticket_id == ticket_id).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Tiket tidak ditemukan.")

    if str(ticket.creates_id) != str(user_id):
        raise HTTPException(status_code=403, detail="Anda bukan pembuat tiket ini.")

    if ticket.status not in ["selesai"]:
        raise HTTPException(status_code=400, detail="Tiket ditolak, tidak bisa diberi rating.")

    existing_rating = (
        db.query(models.TicketRatings)
        .filter(models.TicketRatings.ticket_id == ticket_id)
        .first()
    )

    if existing_rating:
        raise HTTPException(status_code=400, detail="Tiket sudah diberi rating.")

    new_rating = models.TicketRatings(
        ticket_id=ticket_id,
        user_id=user_id,
        rating=rating,
        comment=comment
    )

    db.add(new_rating)
    db.commit()
    db.refresh(new_rating)

    return {
        "status": "success",
        "message": "Rating berhasil disimpan",
        "data": {
            "rating_id": str(new_rating.rating_id),
            "ticket_id": ticket_id,
            "rating": rating,
            "comment": comment,
            "created_at": new_rating.created_at
        }
    }

@router.patch("/tickets/reopen/{ticket_id}")
async def reopen_ticket(
    ticket_id: str,
    alasan_reopen: str = Form(...),
    expected_resolution: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    user_id = current_user.get("id")

    ticket = (
        db.query(models.Tickets)
        .filter(models.Tickets.ticket_id == ticket_id)
        .first()
    )

    if not ticket:
        raise HTTPException(404, "Tiket tidak ditemukan")

    if str(ticket.creates_id) != str(user_id):
        raise HTTPException(403, "Anda tidak berhak membuka ulang tiket ini")

    if ticket.status not in ["selesai"]:
        raise HTTPException(
            400,
            f"Tiket dengan status '{ticket.status}' tidak dapat diajukan kembali"
        )

    old_status = ticket.status

    ticket.status_ticket_seksi = "Draft"
    ticket.assigned_teknisi_id = None
    ticket.status_ticket_teknisi = "Reopen"
    ticket.pengerjaan_awal = None
    ticket.pengerjaan_akhir = None
    ticket.pengerjaan_awal_teknisi = None
    ticket.pengerjaan_akhir_teknisi = None


    ticket.status = "Reopen"
    ticket.ticket_stage = "reopen-draft"
    ticket.status_ticket_pengguna = "Diajukan Kembali"
    ticket.alasan_reopen = alasan_reopen
    ticket.expected_resolution = expected_resolution
    ticket.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(ticket)


    add_ticket_history(
        db=db,
        ticket=ticket,
        old_status=old_status,
        new_status=ticket.status,
        updated_by=UUID(current_user["id"]),
        extra={
            "notes": "Tiket diajukan kembali oleh pengguna",
            "alasan": alasan_reopen
        }
    )

    # new_update = models.TicketUpdates(
    #     status_change=ticket.status,
    #     notes=alasan_reopen,
    #     makes_by_id=UUID(current_user["id"]),
    #     ticket_id=ticket.ticket_id
    # )

    # db.add(new_update)
    db.commit()

    await update_ticket_status(
        db=db,
        ticket=ticket,
        new_status="Menunggu Diproses",
        updated_by=current_user["id"]
    )

    uploaded_files = []
    if files:
        for file in files:
            try:
                file_url = upload_supabase_file("docs", ticket.ticket_id, file)
                new_attach = models.TicketAttachment(
                    attachment_id=uuid4(),
                    has_id=ticket.ticket_id,
                    uploaded_at=datetime.utcnow(),
                    file_path=file_url
                )
                db.add(new_attach)
                db.commit()
                uploaded_files.append(file_url)
            except Exception as e:
                raise HTTPException(500, f"Gagal upload file {file.filename}: {e}")

    return {
        "message": "Tiket berhasil diajukan kembali",
        "ticket_id": str(ticket.ticket_id),
        "ticket_code": ticket.ticket_code,
        "status": ticket.status,
        "uploaded_files": uploaded_files
    }


@router.get("/notifications")
def get_notifications(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    user_id = current_user["id"]

    notifications = (
        db.query(
            Notifications.id.label("notification_id"),
            Notifications.ticket_id,
            Notifications.message,
            Notifications.status,           
            Notifications.is_read,
            Notifications.created_at,
            Tickets.rejection_reason_seksi,
            Tickets.ticket_code,
            Tickets.request_type,
            Tickets.opd_id_tickets.label("opd_id_tiket"),
            Tickets.status_ticket_pengguna,
            Dinas.nama.label("nama_dinas")
        )
        .join(Tickets, Tickets.ticket_id == Notifications.ticket_id)
        .join(Dinas, Dinas.id == Tickets.opd_id_tickets)
        .filter(Notifications.user_id == user_id)
        .order_by(Notifications.created_at.desc())
        .all()
    )

    return {
        "status": "success",
        "count": len(notifications),
        "data": [
            {
                "notification_id": str(n.notification_id),
                "ticket_id": str(n.ticket_id) if n.ticket_id else None,
                "ticket_code": n.ticket_code,
                "request_type": n.request_type,
                "opd_id_tiket": str(n.opd_id_tiket),
                "nama_dinas": n.nama_dinas,
                "rejection_reason_seksi": n.rejection_reason_seksi,
                "status_ticket_pengguna": n.status,
                "message": n.message,
                "is_read": n.is_read,
                "created_at": n.created_at
            }
            for n in notifications
        ]
    }

@router.get("/notifications/{notification_id}")
def get_notification_by_id(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    user_id = current_user["id"]

    notif = (
        db.query(
            Notifications.id.label("notification_id"),
            Notifications.ticket_id,
            Notifications.message,
            Notifications.status,
            Notifications.is_read,
            Notifications.created_at,
            Tickets.rejection_reason_seksi,
            Tickets.ticket_code,
            Tickets.request_type,
            Tickets.opd_id_tickets.label("opd_id_tiket"),
            Tickets.status_ticket_pengguna,
            Dinas.nama.label("nama_dinas")
        )
        .join(Tickets, Tickets.ticket_id == Notifications.ticket_id)
        .join(Dinas, Dinas.id == Tickets.opd_id_tickets)
        .filter(
            Notifications.id == notification_id,
            Notifications.user_id == user_id     
        )
        .first()
    )

    if not notif:
        raise HTTPException(
            status_code=404,
            detail="Notification tidak ditemukan atau tidak milik Anda"
        )

    return {
        "status": "success",
        "data": {
            "notification_id": str(notif.notification_id),
            "ticket_id": str(notif.ticket_id) if notif.ticket_id else None,
            "ticket_code": notif.ticket_code,
            "request_type": notif.request_type,
            "opd_id_tiket": str(notif.opd_id_tiket),
            "nama_dinas": notif.nama_dinas,
            "rejection_reason_seksi": notif.rejection_reason_seksi,
            "status_ticket_pengguna": notif.status,
            "message": notif.message,
            "is_read": notif.is_read,
            "created_at": notif.created_at
        }
    }

@router.delete("/notifications/{notification_id}")
def delete_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    user_id = current_user["id"]

    notif = db.query(Notifications).filter(
        Notifications.id == notification_id,
        Notifications.user_id == user_id
    ).first()

    if not notif:
        raise HTTPException(
            status_code=404,
            detail="Notification tidak ditemukan atau tidak milik Anda"
        )

    db.delete(notif)
    db.commit()

    return {
        "status": "success",
        "message": f"Notification {notification_id} berhasil dihapus"
    }


@router.patch("/notifications/{notification_id}/read")
def mark_notification_as_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    user_id = current_user["id"]

    notif = (
        db.query(Notifications)
        .filter(Notifications.id == notification_id)
        .first()
    )

    if not notif:
        raise HTTPException(
            status_code=404,
            detail="Notifikasi tidak ditemukan"
        )

    if str(notif.user_id) != str(user_id):
        raise HTTPException(
            status_code=403,
            detail="Anda tidak berhak mengakses notifikasi ini"
        )

    notif.is_read = True
    db.commit()
    db.refresh(notif)

    return {
        "status": "success",
        "message": "Notifikasi telah ditandai sebagai dibaca",
        "data": {
            "notification_id": str(notif.id),
            "is_read": notif.is_read
        }
    }


@router.patch("/notifications/read-all")
def mark_all_notifications_as_read(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    user_id = current_user["id"]

    updated = (
        db.query(Notifications)
        .filter(Notifications.user_id == user_id, Notifications.is_read == False)
        .update({Notifications.is_read: True})
    )

    db.commit()

    return {
        "status": "success",
        "message": f"{updated} notifications marked as read"
    }







# @router.get("/track-ticket/{ticket_code}")
# def track_ticket(
#     ticket_code: str,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user) 
# ):
#     user_id = current_user.get("id")


#     ticket = (
#         db.query(models.Tickets)
#         .filter(models.Tickets.ticket_code == ticket_code)
#         .first()
#     )

#     if not ticket:
#         raise HTTPException(status_code=404, detail="Tiket tidak ditemukan.")

#     if str(ticket.creates_id) != str(user_id):
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: Anda bukan pembuat tiket ini."
#         )

#     opd = (
#         db.query(Dinas)
#         .filter(Dinas.id == ticket.opd_id_tickets)
#         .first()
#     )

#     opd_name = opd.nama if opd else None

#     return {
#         "ticket_code": ticket.ticket_code,
#         "status_ticket_pengguna": ticket.status_ticket_pengguna,
#         "request_type": ticket.request_type,
#         "opd_id": ticket.opd_id_tickets,
#         "opd_name": opd_name,
#     }