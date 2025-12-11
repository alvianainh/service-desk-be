import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Response, Query
from sqlalchemy.orm import Session
from datetime import datetime, time
from . import models, schemas
from auth.database import get_db
from auth.auth import get_current_user, get_user_by_email, get_current_user_masyarakat, get_current_user_universal
from tickets import models, schemas
from tickets.models import Tickets, TicketAttachment, TicketCategories, TicketUpdates, TeknisiTags, TeknisiLevels, TicketRatings, WarRoom, WarRoomOPD, WarRoomSeksi, TicketServiceRequests
from tickets.schemas import TicketCreateSchema, TicketResponseSchema, TicketCategorySchema, TicketForSeksiSchema, TicketTrackResponse, UpdatePriority, ManualPriority, RejectReasonSeksi, RejectReasonBidang, AssignTeknisiSchema, WarRoomCreate
import uuid
from auth.models import Opd, Dinas, Roles, Users
import os
from supabase import create_client, Client
from sqlalchemy import text, or_, extract, func
import mimetypes
from uuid import UUID, uuid4
from typing import Optional, List
import aiohttp, os, mimetypes, json
from fastapi.responses import StreamingResponse, FileResponse
from openpyxl import Workbook
from io import BytesIO
from sqlalchemy import extract



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

@router.get("/admin-kota/tickets/critical")
def get_critical_tickets(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(403, "Akses ditolak: hanya admin kota.")

    tickets = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.priority == "Critical",
            models.Tickets.status == "critical - waiting war room"
        )
        .order_by(models.Tickets.created_at.desc())
        .all()
    )

    result = []
    for t in tickets:
        result.append({
            "ticket_id": str(t.ticket_id),
            "ticket_code": t.ticket_code,
            "title": t.title,
            "description": t.description,
            "created_at": t.created_at,
            "priority": t.priority,
            "status": t.status,

            "asset": {
                "asset_id": t.asset_id,
                "nama_asset": t.nama_asset,
                "kode_bmd": t.kode_bmd_asset,
                "lokasi_asset": t.lokasi_asset,
            }
        })

    return {
        "total": len(result),
        "data": result
    }

@router.get("/admin-kota/tickets/critical/{ticket_id}")
def get_critical_ticket_by_id(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(403, "Akses ditolak: hanya admin kota.")

    ticket = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.ticket_id == ticket_id,
            models.Tickets.priority == "Critical",
            models.Tickets.status == "critical - waiting war room"
        )
        .first()
    )

    if not ticket:
        raise HTTPException(
            status_code=404,
            detail="Tiket critical tidak ditemukan atau tidak sedang menunggu war room."
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
        "created_at": ticket.created_at,
        "priority": ticket.priority,

        "opd_id_tickets": ticket.opd_id_tickets,
        "lokasi_kejadian": ticket.lokasi_kejadian,
        "expected_resolution": ticket.expected_resolution,
        "ticket_source": ticket.ticket_source,
        "status_ticket_pengguna": ticket.status_ticket_pengguna,
        "status_ticket_seksi": ticket.status_ticket_seksi,
        
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

@router.get("/admin-opd/seksi/{opd_id}")
def get_seksi_by_opd(
    opd_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin kota (diskominfo) yang dapat melihat daftar seksi"
        )

    seksi_list = (
        db.query(Users.id, Users.full_name)
        .filter(
            Users.opd_id == opd_id,
            Users.role_id == 8
        )
        .distinct()
        .all()
    )

    return {
        "status": "success",
        "opd_id": opd_id,
        "total": len(seksi_list),
        "data": [
            {
                "seksi_id": str(s[0]), 
                "nama": s[1]            
            }
            for s in seksi_list
        ]
    }



@router.post("/war-room")
def create_war_room(payload: WarRoomCreate, 
                    db: Session = Depends(get_db),
                    current_user: dict = Depends(get_current_user_universal)):

    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(status_code=403, detail="Hanya admin kota yang dapat membuat war room.")

    war_room = WarRoom(
        ticket_id = payload.ticket_id,
        title = payload.title,
        link_meet = payload.link_meet,
        start_time = payload.start_time,
        end_time = payload.end_time,
        created_by = current_user["id"]
    )
    db.add(war_room)
    db.commit()
    db.refresh(war_room)

    for opd_id in payload.opd_ids:
        db.add(WarRoomOPD(war_room_id=war_room.id, opd_id=opd_id))

    for seksi_id in payload.seksi_ids:
        db.add(WarRoomSeksi(war_room_id=war_room.id, seksi_id=seksi_id))

    db.commit()

    return {
        "status": "success",
        "message": "War room berhasil dibuat",
        "war_room_id": war_room.id
    }


@router.get("/admin-kota/tickets/completed")
def get_completed_tickets_for_diskominfo(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin kota (diskominfo)."
        )

    tickets = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.status == "selesai",
            models.Tickets.request_type == "pelaporan_online"
        )
        .order_by(models.Tickets.created_at.desc())
        .all()
    )

    results = []

    for ticket in tickets:
        rating = (
            db.query(models.TicketRatings)
            .filter(models.TicketRatings.ticket_id == ticket.ticket_id)
            .first()
        )

        attachments = (
            db.query(models.TicketAttachment)
            .filter(models.TicketAttachment.has_id == ticket.ticket_id)
            .all()
        )

        results.append({
            "ticket_id": str(ticket.ticket_id),
            "ticket_code": ticket.ticket_code,
            "title": ticket.title,
            "status": ticket.status,
            "verified_seksi_id": ticket.verified_seksi_id,
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

            "creator": {
                "user_id": str(ticket.creates_id) if ticket.creates_id else None,
                "full_name": ticket.creates_user.full_name if ticket.creates_user else None,
                "profile": ticket.creates_user.profile_url if ticket.creates_user else None,
                "email": ticket.creates_user.email if ticket.creates_user else None,
                "user_id_asset": ticket.creates_user.user_id_asset if ticket.creates_user else None,
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
        })

    return {
        "total": len(results),
        "data": results
    }


@router.get("/admin-kota/tickets/finished/pegawai")
def get_completed_tickets_for_diskominfo_pegawai(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin kota (diskominfo)."
        )

    tickets = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.status == "selesai",
            models.Tickets.request_type == "pelaporan_online",
            models.Tickets.ticket_source == "Pegawai"  # filter tambahan
        )
        .order_by(models.Tickets.created_at.desc())
        .all()
    )

    results = []

    for ticket in tickets:
        rating = (
            db.query(models.TicketRatings)
            .filter(models.TicketRatings.ticket_id == ticket.ticket_id)
            .first()
        )

        attachments = (
            db.query(models.TicketAttachment)
            .filter(models.TicketAttachment.has_id == ticket.ticket_id)
            .all()
        )

        results.append({
            "ticket_id": str(ticket.ticket_id),
            "ticket_code": ticket.ticket_code,
            "title": ticket.title,
            "status": ticket.status,
            "verified_seksi_id": ticket.verified_seksi_id,
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

            "creator": {
                "user_id": str(ticket.creates_id) if ticket.creates_id else None,
                "full_name": ticket.creates_user.full_name if ticket.creates_user else None,
                "profile": ticket.creates_user.profile_url if ticket.creates_user else None,
                "email": ticket.creates_user.email if ticket.creates_user else None,
                "user_id_asset": ticket.creates_user.user_id_asset if ticket.creates_user else None,
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
        })

    return {
        "total": len(results),
        "data": results
    }


@router.get("/admin-kota/tickets/{ticket_id}")
def get_ticket_by_id_for_diskominfo(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin kota (diskominfo)."
        )

    ticket = db.query(models.Tickets).filter(models.Tickets.ticket_id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Tiket tidak ditemukan")

    rating = (
        db.query(models.TicketRatings)
        .filter(models.TicketRatings.ticket_id == ticket.ticket_id)
        .first()
    )

    attachments = (
        db.query(models.TicketAttachment)
        .filter(models.TicketAttachment.has_id == ticket.ticket_id)
        .all()
    )

    result = {
        "ticket_id": str(ticket.ticket_id),
        "ticket_code": ticket.ticket_code,
        "title": ticket.title,
        "status": ticket.status,
        "verified_seksi_id": ticket.verified_seksi_id,
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

        "creator": {
            "user_id": str(ticket.creates_id) if ticket.creates_id else None,
            "full_name": ticket.creates_user.full_name if ticket.creates_user else None,
            "profile": ticket.creates_user.profile_url if ticket.creates_user else None,
            "email": ticket.creates_user.email if ticket.creates_user else None,
            "user_id_asset": ticket.creates_user.user_id_asset if ticket.creates_user else None,
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

    return result

@router.get("/admin-kota/tickets/finished/pegawai/asset/{asset_id}")
def get_completed_tickets_by_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin kota (diskominfo)."
        )

    tickets = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.status == "selesai",
            models.Tickets.request_type == "pelaporan_online",
            models.Tickets.ticket_source == "Pegawai",
            models.Tickets.asset_id == asset_id  # filter by asset_id
        )
        .order_by(models.Tickets.created_at.desc())
        .all()
    )

    results = []

    for ticket in tickets:
        rating = (
            db.query(models.TicketRatings)
            .filter(models.TicketRatings.ticket_id == ticket.ticket_id)
            .first()
        )

        attachments = (
            db.query(models.TicketAttachment)
            .filter(models.TicketAttachment.has_id == ticket.ticket_id)
            .all()
        )

        results.append({
            "ticket_id": str(ticket.ticket_id),
            "ticket_code": ticket.ticket_code,
            "title": ticket.title,
            "status": ticket.status,
            "verified_seksi_id": ticket.verified_seksi_id,
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

            "creator": {
                "user_id": str(ticket.creates_id) if ticket.creates_id else None,
                "full_name": ticket.creates_user.full_name if ticket.creates_user else None,
                "profile": ticket.creates_user.profile_url if ticket.creates_user else None,
                "email": ticket.creates_user.email if ticket.creates_user else None,
                "user_id_asset": ticket.creates_user.user_id_asset if ticket.creates_user else None,
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
        })

    return {
        "total": len(results),
        "data": results
    }

@router.get("/admin-kota/statistik/pelaporan-online")
def get_ratings_pelaporan_online_admin_kota(
    source: Optional[str] = Query(None, description="Filter ticket_source: Masyarakat / Pegawai"),
    opd_id: Optional[int] = Query(None, description="Filter OPD tertentu (opsional)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    # Hanya admin kota (Diskominfo)
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin kota (Diskominfo) yang dapat melihat data rating."
        )

    # Base query: semua tiket pelaporan_online
    query = db.query(models.Tickets).filter(
        models.Tickets.request_type == "pelaporan_online"
    )

    # Optional filter sumber laporan
    if source in ["Masyarakat", "Pegawai"]:
        query = query.filter(models.Tickets.ticket_source == source)

    # Optional filter OPD
    if opd_id:
        query = query.filter(models.Tickets.opd_id_tickets == opd_id)

    tickets = query.order_by(models.Tickets.created_at.desc()).all()

    results = []

    for t in tickets:
        rating = db.query(models.TicketRatings).filter(
            models.TicketRatings.ticket_id == t.ticket_id
        ).first()

        # skip kalau belum ada rating
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
            "opd_id_tickets": t.opd_id_tickets,  # <-- ditambahkan

            "pengerjaan_awal": t.pengerjaan_awal,
            "pengerjaan_akhir": t.pengerjaan_akhir,
            "pengerjaan_awal_teknisi": t.pengerjaan_awal_teknisi,
            "pengerjaan_akhir_teknisi": t.pengerjaan_akhir_teknisi,

            # Rating
            "rating": rating.rating,
            "comment": rating.comment,
            "rated_at": rating.created_at,

            # User
            "user": {
                "user_id": str(t.creates_id) if t.creates_id else None,
                "full_name": t.creates_user.full_name if t.creates_user else None,
                "email": t.creates_user.email if t.creates_user else None,
                "profile": t.creates_user.profile_url if t.creates_user else None,
            },

            # Asset
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

            # Attachments
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
        "filter_opd": opd_id if opd_id else "all",
        "data": results
    }


@router.get("/admin-kota/statistik/pelaporan-online/kategori")
def get_statistik_kategori_pelaporan_online_admin_kota(
    opd_id: Optional[int] = Query(None, description="Filter OPD tertentu (opsional)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    # Hanya admin kota (Diskominfo)
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin kota (Diskominfo)."
        )

    # Base query: semua tiket pelaporan online
    query = db.query(models.Tickets).filter(
        models.Tickets.request_type == "pelaporan_online"
    )

    # Filter OPD jika ada
    if opd_id:
        query = query.filter(models.Tickets.opd_id_tickets == opd_id)

    tickets = query.all()

    total_all = len(tickets)
    total_masyarakat = 0
    total_pegawai = 0

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
                        "tickets": [],
                        "opd_ids": []  # <-- menampung OPD tiket
                    }

                kategori_stats[kategori_name]["count"] += 1
                kategori_stats[kategori_name]["tickets"].append(str(t.ticket_id))
                kategori_stats[kategori_name]["opd_ids"].append(t.opd_id_tickets)  # <-- simpan OPD

    return {
        "total_pelaporan_online": total_all,
        "total_masyarakat": total_masyarakat,
        "total_pegawai": total_pegawai,
        "filter_opd": opd_id if opd_id else "all",
        "kategori_asset_stats": list(kategori_stats.values())
    }


@router.get("/admin-kota/statistik/pelaporan-online/priority")
def get_statistik_priority_pelaporan_online_admin_kota(
    opd_id: Optional[int] = Query(None, description="Filter OPD tertentu (opsional)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    # Hanya admin kota (Diskominfo)
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin kota (Diskominfo)."
        )

    # Base query: semua tiket pelaporan online
    query = db.query(models.Tickets).filter(
        models.Tickets.request_type == "pelaporan_online"
    )

    # Filter OPD jika ada
    if opd_id:
        query = query.filter(models.Tickets.opd_id_tickets == opd_id)

    tickets = query.all()

    # Priority groups (fixed)
    priorities = ["Low", "Medium", "High", "Critical"]

    priority_stats = {
        p: {
            "priority": p,
            "count": 0,
            "tickets": [],
            "opd_ids": []  # <-- simpan OPD tiket
        }
        for p in priorities
    }

    # Hitung statistik
    for t in tickets:
        p = t.priority if t.priority else None

        if p in priority_stats:
            priority_stats[p]["count"] += 1
            priority_stats[p]["tickets"].append(str(t.ticket_id))
            priority_stats[p]["opd_ids"].append(t.opd_id_tickets)  # <-- tambahkan OPD

    return {
        "total_pelaporan_online": len(tickets),
        "filter_opd": opd_id if opd_id else "all",
        "priority_stats": list(priority_stats.values())
    }

@router.get("/admin-kota/statistik/pelaporan-online/filter")
def get_ratings_pelaporan_online_filter_admin_kota(
    month: Optional[int] = Query(None, ge=1, le=12, description="Filter bulan 1–12"),
    year: Optional[int] = Query(None, description="Filter tahun (YYYY)"),
    source: Optional[str] = Query(None, description="Filter ticket_source: Masyarakat / Pegawai"),
    opd_id: Optional[int] = Query(None, description="Filter berdasarkan OPD tertentu"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    # Hanya admin kota (Diskominfo)
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin kota (Diskominfo)."
        )

    # Base query (admin kota bisa lihat semua tiket)
    query = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.request_type == "pelaporan_online",
            models.Tickets.status == "selesai"
        )
    )

    # Filter optional
    if source in ["Masyarakat", "Pegawai"]:
        query = query.filter(models.Tickets.ticket_source == source)
    if year:
        query = query.filter(extract('year', models.Tickets.created_at) == year)
    if month:
        query = query.filter(extract('month', models.Tickets.created_at) == month)
    if opd_id:
        query = query.filter(models.Tickets.opd_id_tickets == opd_id)

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

            "opd_id_tickets": t.opd_id_tickets,  # <-- tambahkan OPD tiket

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
        "filter_month": month if month else "all",
        "filter_year": year if year else "all",
        "filter_source": source if source else "all",
        "filter_opd_id": opd_id if opd_id else "all",
        "data": results
    }


@router.get("/admin-kota/statistik/pelaporan-online/export")
def export_pelaporan_online_excel_kota(
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None),
    source: Optional[str] = Query(None),
    opd_id: Optional[int] = Query(None, description="Filter OPD tertentu"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    # Hanya admin kota (diskominfo)
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin kota (diskominfo) yang dapat mengexport data."
        )

    # Query utama
    query = db.query(models.Tickets).filter(
        models.Tickets.request_type == "pelaporan_online",
        models.Tickets.status == "selesai"
    )

    # Filter optional
    if source in ["Masyarakat", "Pegawai"]:
        query = query.filter(models.Tickets.ticket_source == source)
    if year:
        query = query.filter(extract("year", models.Tickets.created_at) == year)
    if month:
        query = query.filter(extract("month", models.Tickets.created_at) == month)
    if opd_id:
        query = query.filter(models.Tickets.opd_id_tickets == opd_id)

    tickets = query.order_by(models.Tickets.created_at.desc()).all()

    # Mulai buat Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Pelaporan Online"

    headers = [
        "ticket_id", "ticket_code", "title", "status", "priority",
        "lokasi_kejadian", "created_at", "ticket_source",
        "pengerjaan_awal", "pengerjaan_akhir",
        "pengerjaan_awal_teknisi", "pengerjaan_akhir_teknisi",
        "rating", "comment", "rated_at",
        "user_id", "full_name", "email", "profile",
        "asset_id", "nama_asset", "kode_bmd", "nomor_seri", "kategori",
        "subkategori_id", "subkategori_nama", "jenis_asset", "lokasi_asset",
        "opd_id_tickets",  # <-- tambahkan kolom OPD tiket
        "files"
    ]
    ws.append(headers)

    for t in tickets:
        rating = db.query(models.TicketRatings).filter(models.TicketRatings.ticket_id == t.ticket_id).first()
        if not rating:
            continue

        attachments = t.attachments if hasattr(t, "attachments") else []
        file_list = ", ".join([a.file_path for a in attachments]) if attachments else ""

        row = [
            str(t.ticket_id),
            t.ticket_code,
            t.title,
            t.status,
            t.priority,
            t.lokasi_kejadian,
            t.created_at,
            t.ticket_source,
            t.pengerjaan_awal,
            t.pengerjaan_akhir,
            t.pengerjaan_awal_teknisi,
            t.pengerjaan_akhir_teknisi,
            rating.rating,
            rating.comment,
            rating.created_at,
            str(t.creates_id) if t.creates_id else None,
            t.creates_user.full_name if t.creates_user else None,
            t.creates_user.email if t.creates_user else None,
            t.creates_user.profile_url if t.creates_user else None,
            t.asset_id,
            t.nama_asset,
            t.kode_bmd_asset,
            t.nomor_seri_asset,
            t.kategori_asset,
            t.subkategori_id_asset,
            t.subkategori_nama_asset,
            t.jenis_asset,
            t.lokasi_asset,
            t.opd_id_tickets,  # <-- tampilkan OPD tiket
            file_list
        ]

        ws.append(row)

    # Simpan file
    filename = f"pelaporan_online_export_kota_{uuid.uuid4()}.xlsx"
    filepath = os.path.join("exports", filename)

    os.makedirs("exports", exist_ok=True)
    wb.save(filepath)

    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename
    )

@router.get("/admin-kota/statistik/pengajuan-pelayanan")
def get_statistik_pengajuan_pelayanan_admin_kota(
    opd_id: Optional[int] = Query(None, description="Filter berdasarkan OPD"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    # Hanya admin kota (Diskominfo)
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin kota (Diskominfo) yang dapat melihat data pengajuan pelayanan."
        )

    # Base query semua OPD
    query = (
        db.query(models.Tickets)
        .join(models.TicketServiceRequests, models.TicketServiceRequests.ticket_id == models.Tickets.ticket_id)
        .filter(
            models.Tickets.request_type == "pengajuan_pelayanan",
            models.Tickets.status == "selesai",
        )
    )

    # Filter optional berdasarkan opd_id
    if opd_id:
        query = query.filter(models.Tickets.opd_id_tickets == opd_id)

    # Sort by opd_id dan created_at desc
    tickets = query.order_by(models.Tickets.opd_id_tickets.asc(), models.Tickets.created_at.desc()).all()

    results = []

    for t in tickets:
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

            # OPD tiket
            "opd_id_tickets": t.opd_id_tickets,

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

            # Attachments
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
        "filter_opd": opd_id if opd_id else "all",
        "data": results
    }



@router.get("/admin-kota/statistik/pengajuan-pelayanan/rekap")
def get_rekap_pengajuan_pelayanan_bulanan_admin_kota(
    year: Optional[int] = Query(None, description="Filter tahun (YYYY)"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Filter bulan (1-12)"),
    opd_id: Optional[int] = Query(None, description="Filter berdasarkan OPD"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    # Validasi role admin kota
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin kota (Diskominfo)."
        )

    # Default tahun sekarang
    if not year:
        year = datetime.now().year

    # Query semua tiket pengajuan pelayanan seluruh OPD
    query = (
        db.query(
            models.Tickets.opd_id_tickets.label("opd_id"),
            extract("month", models.Tickets.created_at).label("bulan"),
            func.count(models.Tickets.ticket_id).label("total")
        )
        .join(models.TicketServiceRequests,
              models.TicketServiceRequests.ticket_id == models.Tickets.ticket_id)
        .filter(
            models.Tickets.request_type == "pengajuan_pelayanan",
            models.Tickets.status == "selesai",
            extract("year", models.Tickets.created_at) == year
        )
    )

    # Filter OPD jika diberikan
    if opd_id:
        query = query.filter(models.Tickets.opd_id_tickets == opd_id)

    # Filter bulan jika diberikan
    if month:
        query = query.filter(extract("month", models.Tickets.created_at) == month)

    # Group by OPD + bulan
    raw_result = (
        query.group_by(models.Tickets.opd_id_tickets, extract("month", models.Tickets.created_at))
             .order_by(models.Tickets.opd_id_tickets.asc(), extract("month", models.Tickets.created_at).asc())
             .all()
    )

    # Map hasil query: {opd_id: {bulan: total}}
    rekap_map: dict[int, dict[int, int]] = {}
    for r in raw_result:
        if r.opd_id not in rekap_map:
            rekap_map[r.opd_id] = {}
        rekap_map[r.opd_id][int(r.bulan)] = r.total

    # Build response per OPD
    rekap_list = []
    for opd in sorted(rekap_map.keys()):
        bulan_list = []
        for b in range(1, 13):
            if month and b != month:
                continue
            bulan_list.append({
                "bulan": b,
                "total_tiket": rekap_map[opd].get(b, None)
            })
        rekap_list.append({
            "opd_id_tickets": opd,
            "rekap": bulan_list
        })

    return {
        "tahun": year,
        "filter_opd": opd_id if opd_id else "all",
        "filter_month": month if month else "all",
        "total_opd": len(rekap_list),
        "data": rekap_list
    }


@router.get("/admin-kota/statistik/pengajuan-pelayanan/subkategori")
def statistik_pengajuan_per_subkategori_admin_kota(
    opd_id: Optional[int] = Query(None, description="Filter berdasarkan OPD"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    # Validasi role admin kota
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin kota (Diskominfo)."
        )

    # Query semua tiket selesai pengajuan_pelayanan seluruh OPD
    query = (
        db.query(models.Tickets)
        .join(models.TicketServiceRequests, models.TicketServiceRequests.ticket_id == models.Tickets.ticket_id)
        .filter(
            models.Tickets.request_type == "pengajuan_pelayanan",
            models.Tickets.status == "selesai",
        )
    )

    # Filter OPD jika diberikan
    if opd_id:
        query = query.filter(models.Tickets.opd_id_tickets == opd_id)

    # Sort by opd_id naik
    tickets = query.order_by(models.Tickets.opd_id_tickets.asc()).all()

    # Map statistik per OPD
    statistik_per_opd: dict[int, dict[tuple[int, str], int]] = {}

    for t in tickets:
        sr = t.service_request[0] if t.service_request else None
        if not sr:
            continue

        opd = t.opd_id_tickets
        key = (sr.subkategori_id, sr.subkategori_nama)

        if opd not in statistik_per_opd:
            statistik_per_opd[opd] = {}

        if key not in statistik_per_opd[opd]:
            statistik_per_opd[opd][key] = 0

        statistik_per_opd[opd][key] += 1

    # Build response
    result_list = []
    for opd in sorted(statistik_per_opd.keys()):
        subkategori_list = [
            {
                "subkategori_id": sub_id,
                "subkategori_nama": sub_nama,
                "jumlah": count
            }
            for (sub_id, sub_nama), count in statistik_per_opd[opd].items()
        ]
        result_list.append({
            "opd_id_tickets": opd,
            "statistik_subkategori": subkategori_list
        })

    return {
        "total_tickets": len(tickets),
        "filter_opd": opd_id if opd_id else "all",
        "data": result_list
    }


@router.get("/admin-kota/statistik/pengajuan-pelayanan/priority")
def statistik_pengajuan_per_priority_admin_kota(
    opd_id: Optional[int] = Query(None, description="Filter berdasarkan OPD"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    # Validasi role admin kota
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin kota (Diskominfo)."
        )

    # Query semua tiket selesai pengajuan_pelayanan seluruh OPD
    query = (
        db.query(models.Tickets)
        .join(models.TicketServiceRequests, models.TicketServiceRequests.ticket_id == models.Tickets.ticket_id)
        .filter(
            models.Tickets.request_type == "pengajuan_pelayanan",
            models.Tickets.status == "selesai",
        )
    )

    # Filter OPD jika diberikan
    if opd_id:
        query = query.filter(models.Tickets.opd_id_tickets == opd_id)

    # Sort by opd_id naik
    tickets = query.order_by(models.Tickets.opd_id_tickets.asc()).all()

    # Statistik per OPD
    statistik_per_opd: dict[int, dict[str, int]] = {}

    for t in tickets:
        opd = t.opd_id_tickets
        key = t.priority or "unknown"

        if opd not in statistik_per_opd:
            statistik_per_opd[opd] = {}

        if key not in statistik_per_opd[opd]:
            statistik_per_opd[opd][key] = 0

        statistik_per_opd[opd][key] += 1

    # Build response
    result_list = []
    for opd in sorted(statistik_per_opd.keys()):
        priority_list = [
            {
                "priority": priority,
                "jumlah": count
            }
            for priority, count in statistik_per_opd[opd].items()
        ]
        result_list.append({
            "opd_id_tickets": opd,
            "statistik_priority": priority_list
        })

    return {
        "total_tickets": len(tickets),
        "filter_opd": opd_id if opd_id else "all",
        "data": result_list
    }


@router.get("/admin-kota/statistik/pengajuan-pelayanan/filter")
def get_statistik_pengajuan_pelayanan_filter_admin_kota(
    month: Optional[int] = Query(None, ge=1, le=12, description="Filter bulan (1-12)"),
    year: Optional[int] = Query(None, description="Filter tahun (YYYY)"),
    opd_id: Optional[int] = Query(None, description="Filter OPD tertentu"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    # Hanya admin kota
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin kota (Diskominfo)."
        )

    # Base Query (semua OPD)
    query = (
        db.query(models.Tickets)
        .join(models.TicketServiceRequests, models.TicketServiceRequests.ticket_id == models.Tickets.ticket_id)
        .filter(
            models.Tickets.request_type == "pengajuan_pelayanan",
            models.Tickets.status == "selesai"
        )
    )

    # Optional filter OPD
    if opd_id:
        query = query.filter(models.Tickets.opd_id_tickets == opd_id)

    # Filter berdasarkan tahun
    if year:
        query = query.filter(
            extract('year', models.Tickets.created_at) == year
        )

    # Filter berdasarkan bulan
    if month:
        query = query.filter(
            extract('month', models.Tickets.created_at) == month
        )

    # Sort berdasarkan opd_id
    tickets = query.order_by(models.Tickets.opd_id_tickets.asc(), models.Tickets.created_at.desc()).all()

    results = []

    for t in tickets:

        # Ambil pengajuan pelayanan (form data)
        sr = t.service_request[0] if t.service_request else None

        attachments = t.attachments if hasattr(t, "attachments") else []

        results.append({
            "ticket_id": str(t.ticket_id),
            "ticket_code": t.ticket_code,
            "opd_id_tickets": t.opd_id_tickets,  # <-- tambahan
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "created_at": t.created_at,
            "ticket_source": t.ticket_source,
            "request_type": t.request_type,

            # Pengerjaan
            "pengerjaan_awal": t.pengerjaan_awal,
            "pengerjaan_akhir": t.pengerjaan_akhir,
            "pengerjaan_awal_teknisi": t.pengerjaan_awal_teknisi,
            "pengerjaan_akhir_teknisi": t.pengerjaan_akhir_teknisi,

            # User
            "user": {
                "user_id": str(t.creates_id) if t.creates_id else None,
                "full_name": t.creates_user.full_name if t.creates_user else None,
                "email": t.creates_user.email if t.creates_user else None,
                "profile": t.creates_user.profile_url if t.creates_user else None,
            },

            # Detail Form Pengajuan Pelayanan
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
                "created_at": sr.created_at if sr else None,
            },

            # FILES
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
        "filter_month": month if month else "all",
        "filter_year": year if year else "all",
        "filter_opd": opd_id if opd_id else "all",
        "data": results
    }


@router.get("/admin-kota/statistik/pengajuan-pelayanan/export")
def export_pengajuan_pelayanan_excel_kota(
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None),
    opd_id: Optional[int] = Query(None, description="Filter OPD tertentu"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    # Hanya admin kota
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin kota (diskominfo)."
        )

    # Base query (semua OPD)
    query = (
        db.query(models.Tickets)
        .join(models.TicketServiceRequests, models.TicketServiceRequests.ticket_id == models.Tickets.ticket_id)
        .filter(
            models.Tickets.request_type == "pengajuan_pelayanan",
            models.Tickets.status == "selesai"
        )
    )

    # Optional filter OPD
    if opd_id:
        query = query.filter(models.Tickets.opd_id_tickets == opd_id)

    # Filter berdasarkan tahun
    if year:
        query = query.filter(extract("year", models.Tickets.created_at) == year)

    # Filter berdasarkan bulan
    if month:
        query = query.filter(extract("month", models.Tickets.created_at) == month)

    # Sort berdasarkan opd_id dan created_at
    tickets = query.order_by(models.Tickets.opd_id_tickets.asc(), models.Tickets.created_at.desc()).all()


    wb = Workbook()
    ws = wb.active
    ws.title = "Pengajuan Pelayanan"

    headers = [
        "ticket_id", "ticket_code", "opd_id_tickets", "title", "status", "priority",
        "created_at", "ticket_source", "request_type",
        "pengerjaan_awal", "pengerjaan_akhir",
        "pengerjaan_awal_teknisi", "pengerjaan_akhir_teknisi",
        "user_id", "user_full_name", "user_email", "user_profile",
        "unit_kerja_id", "unit_kerja_nama",
        "lokasi_id", "nama_aset_baru",
        "kategori_aset", "subkategori_id",
        "subkategori_nama", "id_asset",
        "extra_metadata", "form_created_at",
        # Files
        "file_paths"
    ]

    ws.append(headers)

    for t in tickets:
        sr = t.service_request[0] if t.service_request else None
        attachments = t.attachments if hasattr(t, "attachments") else []

        file_paths = ", ".join(a.file_path for a in attachments) if attachments else ""

        row = [
            str(t.ticket_id),
            t.ticket_code,
            t.opd_id_tickets, 
            t.title,
            t.status,
            t.priority,
            t.created_at,
            t.ticket_source,
            t.request_type,
            t.pengerjaan_awal,
            t.pengerjaan_akhir,
            t.pengerjaan_awal_teknisi,
            t.pengerjaan_akhir_teknisi,
            str(t.creates_id) if t.creates_id else None,
            t.creates_user.full_name if t.creates_user else None,
            t.creates_user.email if t.creates_user else None,
            t.creates_user.profile_url if t.creates_user else None,
            sr.unit_kerja_id if sr else None,
            sr.unit_kerja_nama if sr else None,
            sr.lokasi_id if sr else None,
            sr.nama_aset_baru if sr else None,
            sr.kategori_aset if sr else None,
            sr.subkategori_id if sr else None,
            sr.subkategori_nama if sr else None,
            sr.id_asset if sr else None,
            sr.extra_metadata if sr else None,
            sr.created_at if sr else None,
            file_paths
        ]

        ws.append(row)

    os.makedirs("exports", exist_ok=True)
    filename = f"pengajuan_pelayanan_export_kota_{uuid.uuid4()}.xlsx"
    filepath = os.path.join("exports", filename)

    wb.save(filepath)

    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename
    )


