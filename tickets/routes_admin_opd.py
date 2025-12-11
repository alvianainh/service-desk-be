import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Response, Query
from sqlalchemy.orm import Session
from datetime import datetime, time
from . import models, schemas
from auth.database import get_db
from auth.auth import get_current_user, get_user_by_email, get_current_user_masyarakat, get_current_user_universal
from tickets import models, schemas
from tickets.models import Tickets, TicketAttachment, TicketCategories, TicketUpdates, TeknisiTags, TeknisiLevels, TicketRatings, WarRoom, WarRoomOPD, WarRoomSeksi, TicketServiceRequests
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
    updated_by: UUID,
    extra: dict = None
):
    history = models.TicketHistory(
        ticket_id=ticket.ticket_id,
        old_status=ticket.status,
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


@router.get("/admin-opd/ratings")
def get_ratings_for_admin_opd(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin OPD yang dapat melihat data rating."
        )

    opd_id_user = current_user.get("dinas_id")

    tickets = (
        db.query(models.Tickets)
        .filter(models.Tickets.opd_id_tickets == opd_id_user)
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
            "priority": t.priority,
            "lokasi_kejadian": t.lokasi_kejadian,
            "created_at": t.created_at,
            "pengerjaan_awal": t.pengerjaan_awal,
            "pengerjaan_akhir": t.pengerjaan_akhir,
            "pengerjaan_awal_teknisi": t.pengerjaan_awal_teknisi,
            "pengerjaan_akhir_teknisi": t.pengerjaan_akhir_teknisi,


            "rating": rating.rating,
            "comment": rating.comment,
            "rated_at": rating.created_at,

            "user": {
                "user_id": str(t.creates_id) if t.creates_id else None,
                "full_name": t.creates_user.full_name if t.creates_user else None,
                "email": t.creates_user.email if t.creates_user else None,
                "profile": t.creates_user.profile_url if t.creates_user else None,
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

@router.get("/admin-opd/ratings/{ticket_id}")
def get_rating_detail_for_admin_opd(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin OPD yang dapat melihat detail rating."
        )

    opd_id_user = current_user.get("dinas_id")

    ticket = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.ticket_id == ticket_id,
            models.Tickets.opd_id_tickets == opd_id_user
        )
        .first()
    )

    if not ticket:
        raise HTTPException(
            status_code=404,
            detail="Tiket tidak ditemukan atau tidak berasal dari OPD Anda."
        )

    rating = (
        db.query(models.TicketRatings)
        .filter(models.TicketRatings.ticket_id == ticket.ticket_id)
        .first()
    )

    if not rating:
        raise HTTPException(
            status_code=404,
            detail="Tiket ini belum memiliki rating."
        )

    attachments = ticket.attachments if hasattr(ticket, "attachments") else []

    return {
        "ticket_id": str(ticket.ticket_id),
        "ticket_code": ticket.ticket_code,
        "title": ticket.title,
        "status": ticket.status,
        "priority": ticket.priority,
        "lokasi_kejadian": ticket.lokasi_kejadian,
        "created_at": ticket.created_at,
        "pengerjaan_awal": ticket.pengerjaan_awal,
        "pengerjaan_akhir": ticket.pengerjaan_akhir,
        "pengerjaan_awal_teknisi": ticket.pengerjaan_awal_teknisi,
        "pengerjaan_akhir_teknisi": ticket.pengerjaan_akhir_teknisi,

        "rating": rating.rating,
        "comment": rating.comment,
        "rated_at": rating.created_at,

        "user": {
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
                "uploaded_at": a.uploaded_at
            }
            for a in attachments
        ]
    }

@router.get("/war-room/invitations/opd")
def get_war_room_invitation_opd(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    opd_id = current_user["dinas_id"]

    war_rooms = (
        db.query(WarRoom)
        .join(WarRoomOPD, WarRoomOPD.war_room_id == WarRoom.id)
        .filter(WarRoomOPD.opd_id == opd_id)
        .all()
    )

    return war_rooms



@router.get("/admin-opd/statistik/pelaporan-online")
def get_ratings_pelaporan_online(
    source: Optional[str] = Query(None, description="Filter ticket_source: masyarakat / pegawai"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin OPD yang dapat melihat data rating."
        )

    opd_id_user = current_user.get("dinas_id")

    query = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.opd_id_tickets == opd_id_user,
            models.Tickets.request_type == "pelaporan_online"
        )
    )

    if source in ["Masyarakat", "Pegawai"]:
        query = query.filter(models.Tickets.ticket_source == source)

    tickets = query.order_by(models.Tickets.created_at.desc()).all()
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
            "priority": t.priority,
            "lokasi_kejadian": t.lokasi_kejadian,
            "created_at": t.created_at,
            "ticket_source": t.ticket_source,
            "pengerjaan_awal": t.pengerjaan_awal,
            "pengerjaan_akhir": t.pengerjaan_akhir,
            "pengerjaan_awal_teknisi": t.pengerjaan_awal_teknisi,
            "pengerjaan_akhir_teknisi": t.pengerjaan_akhir_teknisi,

            "rating": rating.rating,
            "comment": rating.comment,
            "rated_at": rating.created_at,

            "user": {
                "user_id": str(t.creates_id) if t.creates_id else None,
                "full_name": t.creates_user.full_name if t.creates_user else None,
                "email": t.creates_user.email if t.creates_user else None,
                "profile": t.creates_user.profile_url if t.creates_user else None,
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
        "filter_source": source if source else "all",
        "data": results
    }


@router.get("/admin-opd/statistik/pelaporan-online/kategori")
def get_statistik_kategori_pelaporan_online(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    # Hanya admin opd
    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin OPD."
        )

    opd_id_user = current_user.get("dinas_id")

    # Ambil semua tiket pelaporan online (tanpa filter source dulu)
    tickets = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.opd_id_tickets == opd_id_user,
            models.Tickets.request_type == "pelaporan_online"
        )
        .all()
    )

    total_all = len(tickets)
    total_masyarakat = 0
    total_pegawai = 0

    # Statistik kategori (khusus pegawai)
    kategori_stats = {}

    for t in tickets:

        # Hitung masyarakat vs pegawai
        if t.ticket_source == "Masyarakat":
            total_masyarakat += 1
        elif t.ticket_source == "Pegawai":
            total_pegawai += 1

            # Pegawai → hitung kategori asset
            if t.subkategori_id_asset:
                kategori_name = t.subkategori_nama_asset

                if kategori_name not in kategori_stats:
                    kategori_stats[kategori_name] = {
                        "subkategori": kategori_name,
                        "count": 0,
                        "tickets": []
                    }

                kategori_stats[kategori_name]["count"] += 1
                kategori_stats[kategori_name]["tickets"].append(str(t.ticket_id))

    return {
        "total_pelaporan_online": total_all,
        "total_masyarakat": total_masyarakat,
        "total_pegawai": total_pegawai,
        "kategori_asset_stats": list(kategori_stats.values())
    }


@router.get("/admin-opd/statistik/pelaporan-online/priority")
def get_statistik_priority_pelaporan_online(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    # Hanya admin opd
    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin OPD."
        )

    opd_id_user = current_user.get("dinas_id")

    # Ambil semua tiket pelaporan online
    tickets = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.opd_id_tickets == opd_id_user,
            models.Tickets.request_type == "pelaporan_online"
        )
        .all()
    )

    # Priority groups
    priorities = ["Low", "Medium", "High", "Critical"]

    priority_stats = {
        p: {
            "priority": p,
            "count": 0,
            "tickets": []
        }
        for p in priorities
    }

    for t in tickets:
        p = t.priority if t.priority else None

        if p in priority_stats:
            priority_stats[p]["count"] += 1
            priority_stats[p]["tickets"].append(str(t.ticket_id))

    return {
        "total_pelaporan_online": len(tickets),
        "priority_stats": list(priority_stats.values())
    }

@router.get("/admin-opd/statistik/pengajuan-pelayanan")
def get_statistik_pengajuan_pelayanan(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    # Hanya admin OPD
    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin OPD yang dapat melihat data pengajuan pelayanan."
        )

    opd_id_user = current_user.get("dinas_id")

    # Ambil semua tiket pengajuan pelayanan untuk OPD tersebut
    tickets = (
        db.query(models.Tickets)
        .join(models.TicketServiceRequests, models.TicketServiceRequests.ticket_id == models.Tickets.ticket_id)
        .filter(
            models.Tickets.opd_id_tickets == opd_id_user,
            models.Tickets.request_type == "pengajuan_pelayanan"
        )
        .order_by(models.Tickets.created_at.desc())
        .all()
    )

    results = []

    for t in tickets:

        # Karena relationship masih one-to-many (list)
        sr = t.service_request[0] if t.service_request else None

        attachments = t.attachments if hasattr(t, "attachments") else []

        results.append({
            "ticket_id": str(t.ticket_id),
            "ticket_code": t.ticket_code,
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "created_at": t.created_at,
            "ticket_source": t.ticket_source,
            "request_type": t.request_type,

            # Detail pengerjaan
            "pengerjaan_awal": t.pengerjaan_awal,
            "pengerjaan_akhir": t.pengerjaan_akhir,
            "pengerjaan_awal_teknisi": t.pengerjaan_awal_teknisi,
            "pengerjaan_akhir_teknisi": t.pengerjaan_akhir_teknisi,

            # Detail user
            "user": {
                "user_id": str(t.creates_id) if t.creates_id else None,
                "full_name": t.creates_user.full_name if t.creates_user else None,
                "email": t.creates_user.email if t.creates_user else None,
                "profile": t.creates_user.profile_url if t.creates_user else None,
            },

            # Detail pengajuan pelayanan (form)
            "pengajuan_pelayanan": {
                "unit_kerja_id": sr.unit_kerja_id if sr else None,
                "unit_kerja_nama": sr.unit_kerja_nama if sr else None,
                "lokasi_id": sr.lokasi_id if sr else None,
                "nama_aset_baru": sr.nama_aset_baru if sr else None,
                "kategori_aset": sr.kategori_aset if sr else None,
                "subkategori_id": sr.subkategori_id if sr else None,
                "subkategori_nama": sr.subkategori_nama if sr else None,
                "id_asset": sr.id_asset if sr else None,
                "extra_metadata": sr.extra_metadata if sr else None,
                "created_at": sr.created_at if sr else None
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
