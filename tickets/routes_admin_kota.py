import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Response
from sqlalchemy.orm import Session
from datetime import datetime, time
from . import models, schemas
from auth.database import get_db
from auth.auth import get_current_user, get_user_by_email, get_current_user_masyarakat, get_current_user_universal
from tickets import models, schemas
from tickets.models import Tickets, TicketAttachment, TicketCategories, TicketUpdates, TeknisiTags, TeknisiLevels, TicketRatings, WarRoom, WarRoomOPD, WarRoomSeksi
from tickets.schemas import TicketCreateSchema, TicketResponseSchema, TicketCategorySchema, TicketForSeksiSchema, TicketTrackResponse, UpdatePriority, ManualPriority, RejectReasonSeksi, RejectReasonBidang, AssignTeknisiSchema, WarRoomCreate
import uuid
from auth.models import Opd, Dinas, Roles, Users
import os
from supabase import create_client, Client
from sqlalchemy import text, or_, func
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
    current_user: dict = Depends(get_current_user)
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
    current_user: dict = Depends(get_current_user)
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
                    current_user: dict = Depends(get_current_user)):

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

