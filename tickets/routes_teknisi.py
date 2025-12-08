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
from sqlalchemy import text, or_, func
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


# async def fetch_asset_from_api(token: str, asset_id: int):
#     async with aiohttp.ClientSession() as session:
#         async with session.get(
#             f"{ASSET_BASE}/asset-barang",
#             headers={"Authorization": f"Bearer {token}"}
#         ) as res:

#             if res.status != 200:
#                 text_err = await res.text()
#                 raise HTTPException(
#                     status_code=400,
#                     detail=f"Gagal ambil data asset dari ASET: {text_err}"
#                 )

#             data = await res.json()

#     assets = data.get("data", {}).get("data", [])

#     aset = next((item for item in assets if str(item.get("id")) == str(asset_id)), None)

#     if not aset:
#         raise HTTPException(status_code=404, detail="Asset tidak ditemukan di API ASET")

#     return aset



async def fetch_asset_from_api(token: str, asset_id: int):
    url = f"{ASSET_BASE}/asset-barang/{asset_id}"

    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            headers={"Authorization": f"Bearer {token}"}
        ) as res:

            if res.status == 404:
                raise HTTPException(
                    status_code=404,
                    detail=f"Asset ID {asset_id} tidak ditemukan di API ASET"
                )

            if res.status != 200:
                text = await res.text()
                raise HTTPException(
                    status_code=res.status,
                    detail=f"Error API ASET: {text}"
                )

            data = await res.json()
            return data.get("data")

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



# TEKNISI
@router.get("/tickets/teknisi")
def get_tickets_for_teknisi(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "teknisi":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya teknisi yang dapat melihat daftar tiket"
        )

    teknisi_opd_id = current_user.get("dinas_id")
    teknisi_user_id = current_user.get("id")

    if not teknisi_opd_id:
        raise HTTPException(
            status_code=400,
            detail="User tidak memiliki OPD"
        )

    allowed_status = ["assigned to teknisi", "diproses"]

    tickets = (
        db.query(models.Tickets)
        .filter(models.Tickets.opd_id_tickets == teknisi_opd_id)
        .filter(models.Tickets.assigned_teknisi_id == teknisi_user_id)
        .filter(models.Tickets.status.in_(allowed_status))
        .order_by(models.Tickets.created_at.desc())
        .all()
    )

    attachments = tickets.attachments if hasattr(tickets, "attachments") else []


    return {
        "total": len(tickets),
        "data": [
            {
                "ticket_id": str(t.ticket_id),
                "ticket_code": t.ticket_code,
                "title": t.title,
                "description": t.description,
                "status": t.status,
                "priority": t.priority,
                "created_at": t.created_at,
                "ticket_source": t.ticket_source,
                "status_ticket_pengguna": t.status_ticket_pengguna,
                "status_ticket_seksi": t.status_ticket_seksi,
                "status_ticket_teknisi": t.status_ticket_teknisi,
                "pengerjaan_awal": t.pengerjaan_awal,
                "pengerjaan_akhir": t.pengerjaan_akhir,
                "pengerjaan_awal_teknisi": t.pengerjaan_awal_teknisi,
                "pengerjaan_akhir_teknisi": t.pengerjaan_akhir_teknisi,

                "kategori_risiko_id_asset": t.kategori_risiko_id_asset,
                "kategori_risiko_nama_asset": t.kategori_risiko_nama_asset,
                "kategori_risiko_selera_negatif": t.kategori_risiko_selera_negatif,
                "kategori_risiko_selera_positif": t.kategori_risiko_selera_positif,
                "area_dampak_id_asset": t.area_dampak_id_asset,
                "area_dampak_nama_asset": t.area_dampak_nama_asset,
                "deskripsi_pengendalian_bidang": t.deskripsi_pengendalian_bidang,

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
            for t in tickets
        ]
    }


@router.get("/tickets/teknisi/{ticket_id}")
def get_ticket_detail_for_teknisi(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "teknisi":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya teknisi yang dapat mengakses detail tiket."
        )

    teknisi_opd_id = current_user.get("dinas_id")
    teknisi_user_id = current_user.get("id")

    if not teknisi_opd_id:
        raise HTTPException(
            status_code=400,
            detail="User tidak memiliki OPD"
        )

    ticket = (
        db.query(models.Tickets)
        .filter(models.Tickets.ticket_id == ticket_id)
        .first()
    )

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket tidak ditemukan")

    if ticket.opd_id_tickets != teknisi_opd_id:
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Tiket ini bukan dari OPD teknisi."
        )

    if str(ticket.assigned_teknisi_id) != str(teknisi_user_id):
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Tiket tidak diassign ke teknisi ini."
        )

    allowed_status = ["assigned to teknisi"]
    if ticket.status not in allowed_status:
        raise HTTPException(
            status_code=403,
            detail="Tiket ini belum siap dikerjakan atau statusnya tidak valid untuk teknisi."
        )

    attachments = ticket.attachments if hasattr(ticket, "attachments") else []

    return {
        "ticket_id": str(ticket.ticket_id),
        "ticket_code": ticket.ticket_code,
        "title": ticket.title,
        "description": ticket.description,
        "priority": ticket.priority,
        "status": ticket.status,
        "created_at": ticket.created_at,
        "lokasi_kejadian": ticket.lokasi_kejadian,
        "pengerjaan_awal": ticket.pengerjaan_awal,
        "pengerjaan_akhir": ticket.pengerjaan_akhir,
        "expected_resolution": ticket.expected_resolution,

        "kategori_risiko_id_asset": t.kategori_risiko_id_asset,
        "kategori_risiko_nama_asset": t.kategori_risiko_nama_asset,
        "kategori_risiko_selera_negatif": t.kategori_risiko_selera_negatif,
        "kategori_risiko_selera_positif": t.kategori_risiko_selera_positif,
        "area_dampak_id_asset": t.area_dampak_id_asset,
        "area_dampak_nama_asset": t.area_dampak_nama_asset,
        "deskripsi_pengendalian_bidang": t.deskripsi_pengendalian_bidang,

        "status_ticket_pengguna": ticket.status_ticket_pengguna,
        "status_ticket_seksi": ticket.status_ticket_seksi,
        "status_ticket_teknisi": ticket.status_ticket_teknisi,

        "creator": {
            "user_id": str(ticket.creates_id) if ticket.creates_id else None,
            "full_name": ticket.creates_user.full_name if ticket.creates_user else None,
            "email": ticket.creates_user.email if ticket.creates_user else None,
            "profile": ticket.creates_user.profile_url if ticket.creates_user else None,
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


@router.put("/tickets/teknisi/{ticket_id}/process")
async def teknisi_start_processing(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "teknisi":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya teknisi yang dapat memproses tiket."
        )

    teknisi_opd_id = current_user.get("dinas_id")
    teknisi_user_id = current_user.get("id")

    if not teknisi_opd_id:
        raise HTTPException(status_code=400, detail="User tidak memiliki OPD.")

    ticket = (
        db.query(models.Tickets)
        .filter(models.Tickets.ticket_id == ticket_id)
        .first()
    )

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket tidak ditemukan.")

    old_status = ticket.status

    if ticket.opd_id_tickets != teknisi_opd_id:
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Tiket ini bukan dari OPD teknisi."
        )

    if str(ticket.assigned_teknisi_id) != str(teknisi_user_id):
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Tiket tidak diassign ke teknisi ini."
        )

    if ticket.status != "assigned to teknisi":
        raise HTTPException(
            status_code=400,
            detail="Tiket belum siap diproses oleh teknisi."
        )

    ticket.status = "diproses"
    ticket.status_ticket_pengguna = "proses pengerjaan teknisi"
    ticket.status_ticket_seksi = "diproses"
    ticket.status_ticket_teknisi = "diproses"
    ticket.pengerjaan_awal_teknisi = datetime.utcnow()

    ticket.pengerjaan_awal = datetime.utcnow() 

    db.commit()
    db.refresh(ticket)

    add_ticket_history(
        db=db,
        ticket=ticket,
        old_status=old_status,
        new_status=ticket.status, 
        updated_by=UUID(current_user["id"]),
        extra={"notes": "Tiket dibuat melalui pelaporan online"}
    )

    await update_ticket_status(
        db=db,
        ticket=ticket,
        new_status="Proses Pengerjaan Teknisi",
        updated_by=current_user["id"]
    )

    return {
        "message": "Tiket berhasil diperbarui menjadi diproses oleh teknisi.",
        "ticket_id": str(ticket.ticket_id),
        "status": ticket.status,
        "status_ticket_pengguna": ticket.status_ticket_pengguna,
        "status_ticket_seksi": ticket.status_ticket_seksi,
        "status_ticket_teknisi": ticket.status_ticket_teknisi,
        "pengerjaan_awal": ticket.pengerjaan_awal
    }


@router.put("/tickets/teknisi/{ticket_id}/complete")
async def teknisi_complete_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "teknisi":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya teknisi yang dapat menyelesaikan tiket."
        )

    teknisi_opd_id = current_user.get("dinas_id")
    teknisi_user_id = current_user.get("id")

    if not teknisi_opd_id:
        raise HTTPException(status_code=400, detail="User tidak memiliki OPD.")

    ticket = (
        db.query(models.Tickets)
        .filter(models.Tickets.ticket_id == ticket_id)
        .first()
    )

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket tidak ditemukan.")

    old_status = ticket.status

    if ticket.opd_id_tickets != teknisi_opd_id:
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Tiket ini bukan dari OPD teknisi."
        )

    if str(ticket.assigned_teknisi_id) != str(teknisi_user_id):
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Tiket tidak diassign ke teknisi ini."
        )

    if ticket.status != "diproses":
        raise HTTPException(
            status_code=400,
            detail="Tiket belum bisa diselesaikan karena tidak dalam status 'diproses'."
        )

    ticket.status = "selesai"
    ticket.status_ticket_pengguna = "selesai"
    ticket.status_ticket_seksi = "normal"
    ticket.status_ticket_teknisi = "selesai"
    ticket.pengerjaan_akhir_teknisi = datetime.utcnow()


    teknisi = db.query(Users).filter(Users.id == teknisi_user_id).first()

    if teknisi:
        teknisi.teknisi_kuota_terpakai -= 1
        if teknisi.teknisi_kuota_terpakai < 0:
            teknisi.teknisi_kuota_terpakai = 0

    db.commit()
    db.refresh(ticket)

    add_ticket_history(
        db=db,
        ticket=ticket,
        old_status=old_status,
        new_status=ticket.status, 
        updated_by=UUID(current_user["id"]),
        extra={"notes": "Tiket dibuat melalui pelaporan online"}
    )

    await update_ticket_status(
        db=db,
        ticket=ticket,
        new_status="Selesai",
        updated_by=current_user["id"]
    )

    return {
        "message": "Tiket berhasil diselesaikan oleh teknisi.",
        "ticket_id": str(ticket.ticket_id),
        "status": ticket.status,
        "status_ticket_pengguna": ticket.status_ticket_pengguna,
        "status_ticket_seksi": ticket.status_ticket_seksi,
        "status_ticket_teknisi": ticket.status_ticket_teknisi,
        "pengerjaan_akhir_teknisi": ticket.pengerjaan_akhir_teknisi
    }

@router.get("/teknisi/ratings")
def get_ratings_for_teknisi(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "teknisi":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya seksi yang dapat melihat data rating."
        )

    teknisi_id = current_user.get("id")
    opd_id_user = current_user.get("dinas_id")

    tickets = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.assigned_teknisi_id == teknisi_id,
            models.Tickets.opd_id_tickets == opd_id_user
        )
        .order_by(models.Tickets.created_at.desc())
        .all()
    )

    results = []
    for t in tickets:

        rating = (
            db.query(models.TicketRatings)
            .filter(models.TicketRatings.ticket_id == t.ticket_id)
            .first()
        )

        if not rating:
            continue

        attachments = t.attachments if hasattr(t, "attachments") else []

        results.append({
            "ticket_id": str(t.ticket_id),
            "ticket_code": t.ticket_code,
            "title": t.title,
            "status": t.status,
            "verified_seksi_id": t.verified_seksi_id,
            "assigned_teknisi_id": t.assigned_teknisi_id,
            "opd_id": t.opd_id_tickets,

            "rating": rating.rating if rating else None,
            "comment": rating.comment if rating else None,
            "rated_at": rating.created_at if rating else None,

            "description": t.description,
            "priority": t.priority,
            "lokasi_kejadian": t.lokasi_kejadian,
            "expected_resolution": t.expected_resolution,
            "pengerjaan_awal": t.pengerjaan_awal,
            "pengerjaan_akhir": t.pengerjaan_akhir,
            "pengerjaan_awal_teknisi": t.pengerjaan_awal_teknisi,
            "pengerjaan_akhir_teknisi": t.pengerjaan_akhir_teknisi,

            "kategori_risiko_id_asset": t.kategori_risiko_id_asset,
            "kategori_risiko_nama_asset": t.kategori_risiko_nama_asset,
            "kategori_risiko_selera_negatif": t.kategori_risiko_selera_negatif,
            "kategori_risiko_selera_positif": t.kategori_risiko_selera_positif,
            "area_dampak_id_asset": t.area_dampak_id_asset,
            "area_dampak_nama_asset": t.area_dampak_nama_asset,
            "deskripsi_pengendalian_bidang": t.deskripsi_pengendalian_bidang,

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
            },

            "files": [
                {
                    "attachment_id": str(a.attachment_id),
                    "file_path": a.file_path,
                    "uploaded_at": a.uploaded_at
                }
                for a in attachments
            ]
        })

    return {
        "total": len(results),
        "data": results
    }


@router.get("/teknisi/ratings/{ticket_id}")
def get_rating_detail_for_teknisi(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "teknisi":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya seksi yang dapat melihat data rating."
        )

    teknisi_id = current_user.get("id")
    opd_id_user = current_user.get("dinas_id")

    ticket = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.ticket_id == ticket_id,
            models.Tickets.assigned_teknisi_id == teknisi_id,
            models.Tickets.opd_id_tickets == opd_id_user
        )
        .first()
    )

    if not ticket:
        raise HTTPException(
            status_code=404,
            detail="Tiket tidak ditemukan atau Anda tidak memiliki akses."
        )

    rating = (
        db.query(models.TicketRatings)
        .filter(models.TicketRatings.ticket_id == ticket.ticket_id)
        .first()
    )

    if not rating:
        return {
            "ticket_id": str(ticket.ticket_id),
            "ticket_code": ticket.ticket_code,
            "rating": None,
            "comment": None,
            "rated_at": None
        }


    attachments = ticket.attachments if hasattr(ticket, "attachments") else []

    return {
        "ticket_id": str(ticket.ticket_id),
        "ticket_code": ticket.ticket_code,
        "title": ticket.title,
        "status": ticket.status,
        "verified_seksi_id": ticket.verified_seksi_id,
        "assigned_teknisi_id": ticket.assigned_teknisi_id,
        "opd_id": ticket.opd_id_tickets,

        "rating": rating.rating if rating else None,
        "comment": rating.comment if rating else None,
        "rated_at": rating.created_at if rating else None,

        "description": ticket.description,
        "priority": ticket.priority,
        "lokasi_kejadian": ticket.lokasi_kejadian,
        "expected_resolution": ticket.expected_resolution,
        "pengerjaan_awal": ticket.pengerjaan_awal,
        "pengerjaan_akhir": ticket.pengerjaan_akhir,
        "pengerjaan_awal_teknisi": ticket.pengerjaan_awal_teknisi,
        "pengerjaan_akhir_teknisi": ticket.pengerjaan_akhir_teknisi,

        "kategori_risiko_id_asset": t.kategori_risiko_id_asset,
        "kategori_risiko_nama_asset": t.kategori_risiko_nama_asset,
        "kategori_risiko_selera_negatif": t.kategori_risiko_selera_negatif,
        "kategori_risiko_selera_positif": t.kategori_risiko_selera_positif,
        "area_dampak_id_asset": t.area_dampak_id_asset,
        "area_dampak_nama_asset": t.area_dampak_nama_asset,
        "deskripsi_pengendalian_bidang": t.deskripsi_pengendalian_bidang,

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
