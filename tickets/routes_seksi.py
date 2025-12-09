import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Response
from sqlalchemy.orm import Session
from datetime import datetime, time
from . import models, schemas
from auth.database import get_db
from auth.auth import get_current_user, get_user_by_email, get_current_user_masyarakat, get_current_user_universal
from tickets import models, schemas
from tickets.models import Tickets, TicketAttachment, TicketCategories, TicketUpdates, TeknisiTags, TeknisiLevels, TicketRatings, WarRoom, WarRoomOPD, WarRoomSeksi, Notifications
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
from sqlalchemy.orm import joinedload




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


#SEKSI
#TAMBAHIN PENGAJUAN PELAYANAN
@router.get("/dashboard/seksi")
def get_dashboard_seksi(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "seksi":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya seksi yang dapat mengakses dashboard ini"
        )

    seksi_opd_id = current_user.get("dinas_id")
    if not seksi_opd_id:
        raise HTTPException(
            status_code=400,
            detail="User tidak memiliki OPD"
        )

    # allowed_request_types = ["pelaporan_online", "pengajuan_pelayanan"]

    # total_tickets = db.query(func.count(models.Tickets.ticket_id)).filter(
    #     models.Tickets.opd_id_tickets == seksi_opd_id,
    #     models.Tickets.request_type.in_(allowed_request_types)
    # ).scalar()

    total_tickets = db.query(func.count(models.Tickets.ticket_id)).filter(
        models.Tickets.opd_id_tickets == seksi_opd_id,
        models.Tickets.request_type == "pelaporan_online"
    ).scalar()

    pending_tickets = db.query(func.count(models.Tickets.ticket_id)).filter(
        models.Tickets.opd_id_tickets == seksi_opd_id,
        models.Tickets.status_ticket_seksi == "pending",
        models.Tickets.request_type == "pelaporan_online"
    ).scalar()

    verified_tickets = db.query(func.count(models.Tickets.ticket_id)).filter(
        models.Tickets.opd_id_tickets == seksi_opd_id,
        models.Tickets.status == "verified by bidang",
        models.Tickets.request_type == "pelaporan_online"
    ).scalar()

    rejected_tickets = db.query(func.count(models.Tickets.ticket_id)).filter(
        models.Tickets.opd_id_tickets == seksi_opd_id,
        models.Tickets.status == "rejected",
        models.Tickets.request_type == "pelaporan_online"
    ).scalar()

    return {
        "total_tickets": total_tickets,
        "pending_tickets": pending_tickets,
        "verified_tickets": verified_tickets,
        "rejected_tickets": rejected_tickets
    }



@router.get("/tickets/seksi")
def get_tickets_for_seksi(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "seksi":
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

    allowed_status = [
        "Reopen",
        "Open",           
        "verified by seksi",   
        "rejected by bidang"   
    ]

    allowed_request_types = ["pelaporan_online", "pengajuan_pelayanan"]

    tickets = (
        db.query(models.Tickets)
        .filter(models.Tickets.opd_id_tickets == seksi_opd_id)
        .filter(models.Tickets.status.in_(allowed_status))
        .filter(models.Tickets.request_type.in_(allowed_request_types))  
        .order_by(models.Tickets.created_at.desc())
        .all()
    )

    ticket_ids = [t.ticket_id for t in tickets]

    attachments_all = (
        db.query(models.TicketAttachment)
        .filter(models.TicketAttachment.has_id.in_(ticket_ids))
        .all()
    )

    attachments_map = {}
    for a in attachments_all:
        attachments_map.setdefault(a.has_id, []).append(a)

    return {
        "total": len(tickets),
        "data": [
            {
                "ticket_id": str(t.ticket_id),
                "ticket_code": t.ticket_code,
                "title": t.title,
                "description": t.description,
                "status": t.status,
                "rejection_reason_bidang": t.rejection_reason_bidang,
                # "stage": t.ticket_stage,
                "priority": t.priority,
                "created_at": t.created_at,
                "ticket_source": t.ticket_source,
                "status_ticket_pengguna": t.status_ticket_pengguna,
                "status_ticket_seksi": t.status_ticket_seksi,
            

                "opd_id_tickets": t.opd_id_tickets,
                "lokasi_kejadian": t.lokasi_kejadian,
                ""

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
                    for a in attachments_map.get(t.ticket_id, [])
                ]

            }
            for t in tickets
        ]
    }



# DETAIL SEKSI
@router.get("/tickets/seksi/detail/{ticket_id}")
def get_ticket_detail_seksi(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "seksi":
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

    allowed_status = [
        "Reopen",
        "Open",           
        "verified by seksi",   
        "rejected by bidang"   
    ]

    ticket = (
        db.query(models.Tickets)
        .filter(models.Tickets.ticket_id == ticket_id)
        .filter(models.Tickets.opd_id_tickets == seksi_opd_id)
        .filter(models.Tickets.status.in_(allowed_status))
        .filter(models.Tickets.request_type == "pelaporan_online")
        .first()
    )

    if not ticket:
        raise HTTPException(
            status_code=404,
            detail="Tiket tidak ditemukan, sudah terverifikasi bidang atau tidak memiliki akses"
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
        "rejection_reason_bidang": tickets.rejection_reason_bidang,
        # "stage": ticket.ticket_stage,
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


@router.put("/tickets/{ticket_id}/priority")
async def update_ticket_priority(
    ticket_id: str,
    payload: schemas.UpdatePriority,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "seksi":
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

    old_status = ticket.status

    if ticket.ticket_source != "Pegawai":
        raise HTTPException(
            status_code=400,
            detail="Tiket bukan berasal dari Pegawai, gunakan endpoint /priority/masyarakat."
        )

    if ticket.status == "rejected":
        raise HTTPException(
            400,
            "Tiket sudah ditolak dan tidak dapat diproses lagi."
        )

    if ticket.priority is None and ticket.status != "rejected by bidang":
        pass

    elif ticket.status == "rejected by bidang":
        ticket.rejection_reason_bidang = None
        ticket.status_ticket_seksi = "pending"

    else:
        raise HTTPException(
            400,
            f"Tiket sudah memiliki prioritas '{ticket.priority}' dan tidak bisa diubah lagi."
        )

    # if ticket.priority is not None:
    #     raise HTTPException(
    #         status_code=400,
    #         detail=f"Prioritas sudah diset menjadi '{ticket.priority}' dan tidak dapat diubah lagi."
    #     )

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
    ticket.verified_seksi_id = current_user.get("id")

    if priority == "Critical":
        ticket.ticket_stage = "war-room-required"
        ticket.status = "critical - waiting war room"
        ticket.status_ticket_seksi = "done"
        ticket.status_ticket_pengguna = "menunggu war room"

    else:
        ticket.ticket_stage = "pending"
        ticket.status = "verified by seksi"
        ticket.status_ticket_seksi = "pending"
        ticket.status_ticket_pengguna = "proses verifikasi"

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
        new_status="Proses Verifikasi",
        updated_by=current_user["id"]
    )

    # db.commit()
    # db.refresh(ticket)

    return {
        "message": "Prioritas tiket berhasil ditetapkan",
        "ticket_id": ticket_id,
        "priority": ticket.priority,
        "score": score
    }


@router.put("/tickets/{ticket_id}/priority/masyarakat")
async def set_priority_masyarakat(
    ticket_id: str,
    payload: schemas.ManualPriority,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "seksi":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya seksi yang dapat mengubah prioritas"
        )

    ticket = db.query(models.Tickets).filter_by(ticket_id=ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Tiket tidak ditemukan")

    old_status = ticket.status

    if ticket.ticket_source != "Masyarakat":
        raise HTTPException(
            status_code=400,
            detail="Tiket bukan berasal dari masyarakat, gunakan endpoint matrix."
        )

    if ticket.status == "rejected":
        raise HTTPException(
            400,
            "Tiket sudah ditolak dan tidak dapat diproses lagi."
        )

    if ticket.priority is None and ticket.status != "rejected by bidang":
        pass

    elif ticket.status == "rejected by bidang":
        ticket.rejection_reason_bidang = None
        ticket.status_ticket_seksi = "pending"

    else:
        raise HTTPException(
            400,
            f"Tiket sudah memiliki prioritas '{ticket.priority}' dan tidak bisa diubah lagi."
        )

    # if ticket.priority is not None:
    #     raise HTTPException(
    #         400,
    #         f"Prioritas sudah ditetapkan menjadi '{ticket.priority}' dan tidak dapat diubah lagi."
    #     )

    valid_priorities = ["low", "medium", "high", "critical"]
    if payload.priority.lower() not in valid_priorities:
        raise HTTPException(
            400,
            "Prioritas tidak valid, harus salah satu: low, medium, high, critical."
        )

    ticket.priority = payload.priority.capitalize()  
    ticket.ticket_stage = "pending"
    ticket.status = "verified by seksi"
    ticket.status_ticket_seksi="pending"
    ticket.status_ticket_pengguna="proses verifikasi"
    ticket.verified_seksi_id=current_user.get("id")


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
        new_status="Proses Verifikasi",
        updated_by=current_user["id"]
    )

    return {
        "message": "Prioritas tiket masyarakat berhasil ditetapkan",
        "ticket_id": ticket_id,
        "priority": ticket.priority
    }


@router.put("/tickets/{ticket_id}/reject")
async def reject_ticket(
    ticket_id: str,
    payload: schemas.RejectReasonSeksi,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "seksi":
        raise HTTPException(
            403, "Akses ditolak: hanya seksi yang dapat menolak tiket"
        )

    ticket = db.query(models.Tickets).filter_by(ticket_id=ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Tiket tidak ditemukan")

    old_status = ticket.status

    if ticket.priority is not None or ticket.status == "rejected":
        raise HTTPException(
            400,
            "Tiket sudah diproses set prioritas dan tidak dapat diubah lagi."
        )

    ticket.status = "rejected"  
    ticket.ticket_stage = "done" 
    ticket.status_ticket_pengguna = "tiket ditolak"
    ticket.status_ticket_seksi = "rejected"
    ticket.rejection_reason_seksi = payload.reason

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
        new_status="Tiket Ditolak",
        updated_by=current_user["id"]
    )

    return {
        "message": "Tiket berhasil ditolak",
        "ticket_id": ticket_id,
        "status": ticket.status,
        "reason": ticket.rejection_reason_seksi
    }



@router.get("/tickets/seksi/verified-bidang")
def get_tickets_verified_by_bidang_for_seksi(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "seksi":
        raise HTTPException(
            403,
            "Akses ditolak: hanya seksi yang dapat mengakses daftar tiket ini"
        )

    seksi_opd_id = current_user.get("dinas_id")
    if not seksi_opd_id:
        raise HTTPException(400, "User tidak memiliki OPD")

    tickets = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.opd_id_tickets == seksi_opd_id,
            or_(
                models.Tickets.status == "verified by bidang",
                models.Tickets.status == "assigned to teknisi",
                models.Tickets.status == "diproses"
            ),
            models.Tickets.request_type == "pelaporan_online"
        )
        .order_by(models.Tickets.created_at.desc())
        .all()
    )

    result = []

    for t in tickets:
        attachments = t.attachments if hasattr(t, "attachments") else []

        result.append({
            "ticket_id": str(t.ticket_id),
            "ticket_code": t.ticket_code,
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "created_at": t.created_at,
            "ticket_source": t.ticket_source,
            "status_ticket_pengguna": t.status_ticket_pengguna,
            "status_ticket_seksi": t.status_ticket_seksi,

            "kategori_risiko_id_asset": t.kategori_risiko_id_asset,
            "kategori_risiko_nama_asset": t.kategori_risiko_nama_asset,
            "kategori_risiko_selera_negatif": t.kategori_risiko_selera_negatif,
            "kategori_risiko_selera_positif": t.kategori_risiko_selera_positif,
            "area_dampak_id_asset": t.area_dampak_id_asset,
            "area_dampak_nama_asset": t.area_dampak_nama_asset,
            "deskripsi_pengendalian_bidang": t.deskripsi_pengendalian_bidang,


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
        "total": len(result),
        "data": result
    }

@router.get("/tickets/seksi/verified-bidang/{ticket_id}")
def get_ticket_detail_verified_by_bidang_for_seksi(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "seksi":
        raise HTTPException(
            403,
            "Akses ditolak: hanya seksi yang dapat mengakses detail tiket ini"
        )

    seksi_opd_id = current_user.get("dinas_id")
    if not seksi_opd_id:
        raise HTTPException(400, "User tidak memiliki OPD")

    try:
        uuid_obj = uuid.UUID(ticket_id)
    except ValueError:
        raise HTTPException(400, "ticket_id tidak valid (bukan UUID)")

    ticket = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.ticket_id == uuid_obj,
            models.Tickets.opd_id_tickets == seksi_opd_id,
            models.Tickets.status == "verified by bidang",
            models.Tickets.request_type == "pelaporan_online"
        )
        .first()
    )

    if not ticket:
        raise HTTPException(404, "Tiket tidak ditemukan atau tidak memiliki akses")

    attachments = ticket.attachments if hasattr(ticket, "attachments") else []

    return {
        "ticket_id": str(ticket.ticket_id),
        "ticket_code": ticket.ticket_code,
        "title": ticket.title,
        "description": ticket.description,
        "priority": ticket.priority,
        "status": ticket.status,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,

        "lokasi_kejadian": ticket.lokasi_kejadian,
        "opd_id_tickets": ticket.opd_id_tickets,

        "kategori_risiko_id_asset": ticket.kategori_risiko_id_asset,
        "kategori_risiko_nama_asset": ticket.kategori_risiko_nama_asset,
        "kategori_risiko_selera_negatif": ticket.kategori_risiko_selera_negatif,
        "kategori_risiko_selera_positif": ticket.kategori_risiko_selera_positif,
        "area_dampak_id_asset": ticket.area_dampak_id_asset,
        "area_dampak_nama_asset": ticket.area_dampak_nama_asset,
        "deskripsi_pengendalian_bidang": ticket.deskripsi_pengendalian_bidang,

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




@router.get("/teknisi/seksi")
def get_technicians_for_seksi(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "seksi":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya seksi yang dapat melihat daftar teknisi"
        )

    seksi_opd_id = current_user.get("dinas_id")
    if not seksi_opd_id:
        raise HTTPException(
            status_code=400,
            detail="User tidak memiliki OPD"
        )

    technicians = (
        db.query(Users)
        .filter(Users.role_id == 6) 
        .filter(Users.opd_id == seksi_opd_id)
        .all()
    )

    result = []

    for tech in technicians:
        level = tech.teknisi_level_obj  
        tag = tech.teknisi_tag_obj  

        quota = level.quota if level else 0
        used = tech.teknisi_kuota_terpakai or 0
        remaining_quota = quota - used

        result.append({
            "id": str(tech.id),
            "full_name": tech.full_name,
            "profile_url": tech.profile_url,
            "email": tech.email,

            "tag": tag.name if tag else None,
            "tag_id": tag.id if tag else None,

            "level": level.name if level else None,
            "level_id": level.id if level else None,
            "quota": quota,

            "current_load": used,
            "remaining_quota": remaining_quota
        })

    return {
        "total": len(result),
        "data": result
    }


@router.put("/tickets/{ticket_id}/assign-teknisi")
async def assign_teknisi(
    ticket_id: str,
    payload: AssignTeknisiSchema,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "seksi":
        raise HTTPException(status_code=403, detail="Akses ditolak")

    ticket = db.query(Tickets).filter(Tickets.ticket_id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket tidak ditemukan")

    old_status = ticket.status

    if ticket.assigned_teknisi_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Tiket ini sudah pernah di-assign ke teknisi. Tidak boleh assign ulang."
        )

    if ticket.status != "verified by bidang":
        raise HTTPException(status_code=400, detail="Ticket belum diverifikasi bidang")

    teknisi = db.query(Users).filter(Users.id == payload.teknisi_id).first()
    if not teknisi:
        raise HTTPException(status_code=400, detail="Teknisi tidak ditemukan")

    if teknisi.role_id != 6:
        raise HTTPException(status_code=400, detail="User ini bukan teknisi")


    if teknisi.opd_id != current_user.get("dinas_id"):
        raise HTTPException(status_code=403, detail="Teknisi bukan dari OPD yang sama")

    level = teknisi.teknisi_level_obj
    if (teknisi.teknisi_kuota_terpakai or 0) >= level.quota:
        raise HTTPException(status_code=400, detail="Kuota teknisi penuh")

    now_time = datetime.now().time()
    pengerjaan_awal = datetime.combine(payload.pengerjaan_awal, now_time)
    pengerjaan_akhir = datetime.combine(payload.pengerjaan_akhir, now_time)

    ticket.assigned_teknisi_id = payload.teknisi_id
    ticket.pengerjaan_awal = pengerjaan_awal
    ticket.pengerjaan_akhir = pengerjaan_akhir
    ticket.status = "assigned to teknisi"
    ticket.status_ticket_teknisi = "Draft"
    ticket.status_ticket_pengguna = "proses penugasan teknisi"
    ticket.status_ticket_seksi = "diproses"

    teknisi.teknisi_kuota_terpakai += 1


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
        new_status="Proses Penugasan Teknisi",
        updated_by=current_user["id"]
    )

    return {"message": "Teknisi berhasil diassign", "ticket_id": ticket_id}


@router.get("/tickets/seksi/assigned")
def get_assigned_tickets_for_seksi(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "seksi":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya seksi yang dapat melihat tiket assigned."
        )

    seksi_opd_id = current_user.get("dinas_id")

    tickets = (
        db.query(
            Tickets.ticket_id,
            Tickets.ticket_code,
            Tickets.title,
            Tickets.assigned_teknisi_id,
            Tickets.pengerjaan_awal,
            Tickets.pengerjaan_akhir,
            Tickets.status,
            Users.full_name.label("nama_teknisi"),
            Tickets.request_type,
            Tickets.created_at
        )
        .join(Users, Users.id == Tickets.assigned_teknisi_id)
        .filter(
            Tickets.opd_id_tickets == seksi_opd_id,
            Tickets.assigned_teknisi_id.isnot(None)  # sudah diassign teknisi
        )
        .order_by(Tickets.created_at.desc())
        .all()
    )

    return {
        "status": "success",
        "count": len(tickets),
        "data": [
            {
                "ticket_id": str(t.ticket_id),
                "ticket_code": t.ticket_code,
                "title": t.title,
                "assigned_teknisi_id": str(t.assigned_teknisi_id),
                "nama_teknisi": t.nama_teknisi,
                "pengerjaan_awal": t.pengerjaan_awal,
                "pengerjaan_akhir": t.pengerjaan_akhir,
                "status": t.status,
                "request_type": t.request_type,
                "created_at": t.created_at
            }
            for t in tickets
        ]
    }


@router.get("/tickets/seksi/assigned/{teknisi_id}")
def get_assigned_tickets_by_teknisi(
    teknisi_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "seksi":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya seksi yang dapat melihat tiket assigned."
        )

    seksi_opd_id = current_user.get("dinas_id")

    tickets = (
        db.query(
            Tickets.ticket_id,
            Tickets.ticket_code,
            Tickets.title,
            Tickets.assigned_teknisi_id,
            Tickets.pengerjaan_awal,
            Tickets.pengerjaan_akhir,
            Tickets.status,
            Users.full_name.label("nama_teknisi"),
            Tickets.request_type,
            Tickets.created_at
        )
        .join(Users, Users.id == Tickets.assigned_teknisi_id)
        .filter(
            Tickets.opd_id_tickets == seksi_opd_id, 
            Tickets.assigned_teknisi_id == teknisi_id
        )
        .order_by(Tickets.created_at.desc())
        .all()
    )

    return {
        "status": "success",
        "count": len(tickets),
        "data": [
            {
                "ticket_id": str(t.ticket_id),
                "ticket_code": t.ticket_code,
                "title": t.title,
                "assigned_teknisi_id": str(t.assigned_teknisi_id),
                "nama_teknisi": t.nama_teknisi,
                "pengerjaan_awal": t.pengerjaan_awal,
                "pengerjaan_akhir": t.pengerjaan_akhir,
                "status": t.status,
                "request_type": t.request_type,
                "created_at": t.created_at
            }
            for t in tickets
        ]
    }


@router.get("/tickets/seksi/assigned/teknisi/{ticket_id}")
def get_ticket_detail_assigned_to_teknisi_for_seksi(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "seksi":
        raise HTTPException(
            403,
            "Akses ditolak: hanya seksi yang dapat mengakses detail tiket ini"
        )

    seksi_opd_id = current_user.get("dinas_id")
    if not seksi_opd_id:
        raise HTTPException(400, "User tidak memiliki OPD")

    try:
        uuid_obj = uuid.UUID(ticket_id)
    except ValueError:
        raise HTTPException(400, "ticket_id tidak valid (bukan UUID)")

    ticket = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.ticket_id == uuid_obj,
            models.Tickets.opd_id_tickets == seksi_opd_id,
            models.Tickets.assigned_teknisi_id.isnot(None)  # sudah diassign teknisi
        )
        .first()
    )

    if not ticket:
        raise HTTPException(404, "Tiket tidak ditemukan atau tidak memiliki akses")

    attachments = ticket.attachments if hasattr(ticket, "attachments") else []

    return {
        "ticket_id": str(ticket.ticket_id),
        "ticket_code": ticket.ticket_code,
        "title": ticket.title,
        "description": ticket.description,
        "priority": ticket.priority,
        "status": ticket.status,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "status_ticket_seksi": ticket.status_ticket_seksi,

        "lokasi_kejadian": ticket.lokasi_kejadian,
        "opd_id_tickets": ticket.opd_id_tickets,

        "kategori_risiko_id_asset": ticket.kategori_risiko_id_asset,
        "kategori_risiko_nama_asset": ticket.kategori_risiko_nama_asset,
        "kategori_risiko_selera_negatif": ticket.kategori_risiko_selera_negatif,
        "kategori_risiko_selera_positif": ticket.kategori_risiko_selera_positif,
        "area_dampak_id_asset": ticket.area_dampak_id_asset,
        "area_dampak_nama_asset": ticket.area_dampak_nama_asset,
        "deskripsi_pengendalian_bidang": ticket.deskripsi_pengendalian_bidang,


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





@router.get("/seksi/ratings")
def get_ratings_for_seksi(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "seksi":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya seksi yang dapat melihat data rating."
        )

    seksi_id = current_user.get("id")
    opd_id_user = current_user.get("dinas_id")

    tickets = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.verified_seksi_id == seksi_id,
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
            "opd_id": t.opd_id_tickets,

            "rating": rating.rating if rating else None,
            "comment": rating.comment if rating else None,
            "rated_at": rating.created_at if rating else None,

            "kategori_risiko_id_asset": t.kategori_risiko_id_asset,
            "kategori_risiko_nama_asset": t.kategori_risiko_nama_asset,
            "kategori_risiko_selera_negatif": t.kategori_risiko_selera_negatif,
            "kategori_risiko_selera_positif": t.kategori_risiko_selera_positif,
            "area_dampak_id_asset": t.area_dampak_id_asset,
            "area_dampak_nama_asset": t.area_dampak_nama_asset,
            "deskripsi_pengendalian_bidang": t.deskripsi_pengendalian_bidang,


            "description": t.description,
            "priority": t.priority,
            "lokasi_kejadian": t.lokasi_kejadian,
            "expected_resolution": t.expected_resolution,
            "pengerjaan_awal": t.pengerjaan_awal,
            "pengerjaan_akhir": t.pengerjaan_akhir,
            "pengerjaan_awal_teknisi": t.pengerjaan_awal_teknisi,
            "pengerjaan_akhir_teknisi": t.pengerjaan_akhir_teknisi,

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


@router.get("/seksi/ratings/{ticket_id}")
def get_rating_detail_for_seksi(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "seksi":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya seksi yang dapat melihat data rating."
        )

    seksi_id = current_user.get("id")
    opd_id_user = current_user.get("dinas_id")

    ticket = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.ticket_id == ticket_id,
            models.Tickets.verified_seksi_id == seksi_id,
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

        "kategori_risiko_id_asset": ticket.kategori_risiko_id_asset,
        "kategori_risiko_nama_asset": ticket.kategori_risiko_nama_asset,
        "kategori_risiko_selera_negatif": ticket.kategori_risiko_selera_negatif,
        "kategori_risiko_selera_positif": ticket.kategori_risiko_selera_positif,
        "area_dampak_id_asset": ticket.area_dampak_id_asset,
        "area_dampak_nama_asset": ticket.area_dampak_nama_asset,
        "deskripsi_pengendalian_bidang": ticket.deskripsi_pengendalian_bidang,

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


@router.get("/tickets/seksi/finished")
def get_finished_tickets_for_seksi(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "seksi":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya seksi OPD yang dapat melihat daftar tiket selesai."
        )

    seksi_opd_id = current_user.get("dinas_id")

    # masyarakat_tickets = (
    #     db.query(models.Tickets)
    #     .filter(
    #         models.Tickets.status == "selesai",
    #         models.Tickets.opd_id_tickets == seksi_opd_id,
    #         models.Tickets.asset_id.is_(None)
    #     )
    #     .order_by(models.Tickets.created_at.desc())
    #     .all()
    # )

    # masyarakat_result = [
    #     {
    #         "ticket_id": t.ticket_id,
    #         "ticket_code": t.ticket_code,
    #         "title": t.title,
    #         "description": t.description,
    #         "status": t.status,
    #         "latest_report_date": t.created_at,
    #         "asset": None,
    #         "intensitas_laporan": None
    #     }
    #     for t in masyarakat_tickets
    # ]

    subquery = (
        db.query(
            models.Tickets.asset_id,
            func.max(models.Tickets.created_at).label("latest_date")
        )
        .filter(
            models.Tickets.opd_id_tickets == seksi_opd_id,
            models.Tickets.status == "selesai",
            models.Tickets.asset_id.isnot(None)
        )
        .group_by(models.Tickets.asset_id)
        .subquery()
    )

    latest_tickets = (
        db.query(models.Tickets)
        .join(
            subquery,
            (models.Tickets.asset_id == subquery.c.asset_id) &
            (models.Tickets.created_at == subquery.c.latest_date)
        )
        .order_by(models.Tickets.created_at.desc())
        .all()
    )

    asset_ids = {t.asset_id for t in latest_tickets}

    intensitas_map = (
        db.query(models.Tickets.asset_id, func.count(models.Tickets.ticket_id))
        .filter(
            models.Tickets.asset_id.in_(asset_ids),
            models.Tickets.status == "selesai"
        )
        .group_by(models.Tickets.asset_id)
        .all()
    )
    intensitas_dict = {asset_id: count for asset_id, count in intensitas_map}

    aset_result = []
    for t in latest_tickets:
        aset_result.append({
            "ticket_id": t.ticket_id,
            "ticket_code": t.ticket_code,
            "latest_report_date": t.created_at,
            "title": t.title,
            "description": t.description,
            "status": t.status,

            "intensitas_laporan": intensitas_dict.get(t.asset_id, 0),

            "asset": {
                "asset_id": t.asset_id,
                "nama_asset": t.nama_asset,
                "kode_bmd": t.kode_bmd_asset,
                "nomor_seri": t.nomor_seri_asset,
                "kategori": t.kategori_asset,
                "subkategori_nama": t.subkategori_nama_asset,
                "jenis_asset": t.jenis_asset,
                "lokasi_asset": t.lokasi_asset,
            }
        })

    # combined = masyarakat_result + aset_result

    # combined_sorted = sorted(combined, key=lambda x: x["latest_report_date"], reverse=True)

    return {
        "total_tickets": len(aset_result),
        "data": aset_result
    }


@router.get("/tickets/seksi/finished/{asset_id}")
def get_finished_tickets_by_asset_id(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "seksi":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya seksi OPD yang dapat melihat detail tiket."
        )

    seksi_opd_id = current_user.get("dinas_id")

    tickets = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.opd_id_tickets == seksi_opd_id,
            models.Tickets.status == "selesai",
            models.Tickets.asset_id == asset_id
        )
        .order_by(models.Tickets.created_at.desc())
        .all()
    )

    if not tickets:
        raise HTTPException(
            status_code=404,
            detail="Tidak ada tiket selesai untuk asset ini."
        )

    intensitas = len(tickets)

    result = []
    for t in tickets:
        result.append({
            "ticket_id": str(t.ticket_id),
            "ticket_code": t.ticket_code,
            "title": t.title,
            "description": t.description,
            "status": t.status,
            "created_at": t.created_at,
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


            "pelapor": {
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
                "subkategori_nama": t.subkategori_nama_asset,
                "jenis_asset": t.jenis_asset,
                "lokasi_asset": t.lokasi_asset,
            }
        })

    return {
        "asset_id": asset_id,
        "intensitas_laporan": intensitas,
        "total_tickets": len(tickets),
        "data": result
    }

@router.get("/tickets/seksi/finished/ticket/{ticket_id}")
def get_finished_ticket_by_id(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "seksi":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya seksi OPD yang dapat melihat detail tiket."
        )

    seksi_opd_id = current_user.get("dinas_id")

    ticket = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.ticket_id == ticket_id,
            models.Tickets.opd_id_tickets == seksi_opd_id,
            models.Tickets.status == "selesai"
        )
        .first()
    )

    if not ticket:
        raise HTTPException(
            status_code=404,
            detail="Tiket tidak ditemukan atau bukan milik OPD Anda / belum selesai."
        )

    attachments = (
        db.query(models.TicketAttachment)
        .filter(models.TicketAttachment.has_id == ticket.ticket_id)
        .all()
    )

    intensitas = None
    if ticket.asset_id:
        intensitas = (
            db.query(func.count(models.Tickets.ticket_id))
            .filter(
                models.Tickets.asset_id == ticket.asset_id,
                models.Tickets.status == "selesai"
            )
            .scalar()
        )

    response = {
        "ticket_id": str(ticket.ticket_id),
        "ticket_code": ticket.ticket_code,
        "title": ticket.title,
        "description": ticket.description,
        "status": ticket.status,
        "created_at": ticket.created_at,
        "priority": ticket.priority,
        "lokasi_kejadian": ticket.lokasi_kejadian,
        "expected_resolution": ticket.expected_resolution,

        "pengerjaan_awal": ticket.pengerjaan_awal,
        "pengerjaan_akhir": ticket.pengerjaan_akhir,
        "pengerjaan_awal_teknisi": ticket.pengerjaan_awal_teknisi,
        "pengerjaan_akhir_teknisi": ticket.pengerjaan_akhir_teknisi,

        "kategori_risiko_id_asset": ticket.kategori_risiko_id_asset,
        "kategori_risiko_nama_asset": ticket.kategori_risiko_nama_asset,
        "kategori_risiko_selera_negatif": ticket.kategori_risiko_selera_negatif,
        "kategori_risiko_selera_positif": ticket.kategori_risiko_selera_positif,
        "area_dampak_id_asset": ticket.area_dampak_id_asset,
        "area_dampak_nama_asset": ticket.area_dampak_nama_asset,
        "deskripsi_pengendalian_bidang": ticket.deskripsi_pengendalian_bidang,


        "intensitas_laporan": intensitas,

        "pelapor": {
            "user_id": str(ticket.creates_id) if ticket.creates_id else None,
            "full_name": ticket.creates_user.full_name if ticket.creates_user else None,
            "email": ticket.creates_user.email if ticket.creates_user else None,
            "profile": ticket.creates_user.profile_url if ticket.creates_user else None,
        },

        "asset": None,
        "files": [
            {
                "attachment_id": str(a.attachment_id),
                "file_path": a.file_path,
                "uploaded_at": a.uploaded_at
            }
            for a in attachments
        ]
    }

    if ticket.asset_id:
        response["asset"] = {
            "asset_id": ticket.asset_id,
            "nama_asset": ticket.nama_asset,
            "kode_bmd": ticket.kode_bmd_asset,
            "nomor_seri": ticket.nomor_seri_asset,
            "kategori": ticket.kategori_asset,
            "subkategori_nama": ticket.subkategori_nama_asset,
            "jenis_asset": ticket.jenis_asset,
            "lokasi_asset": ticket.lokasi_asset,
        }

    return response

@router.get("/war-room/invitations/seksi")
def get_war_room_invitation_seksi(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    seksi_id = current_user["id"]

    war_rooms = (
        db.query(WarRoom)
        .join(WarRoomSeksi, WarRoomSeksi.war_room_id == WarRoom.id)
        .filter(WarRoomSeksi.seksi_id == seksi_id)
        .all()
    )

    return war_rooms


@router.get("/war-room/{id}")
def get_war_room_detail(
    id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    role = current_user.get("role_name")
    user_id = current_user.get("id")
    opd_id_user = current_user.get("dinas_id") 

    war_room = (
        db.query(WarRoom)
        .filter(WarRoom.id == id)
        .first()
    )

    if not war_room:
        raise HTTPException(status_code=404, detail="War room tidak ditemukan")

    if role == "admin dinas":
        pass

    elif role == "admin dinas":
        invited = (
            db.query(WarRoomOPD)
            .filter(
                WarRoomOPD.war_room_id == id,
                WarRoomOPD.opd_id == opd_id_user
            )
            .first()
        )
        if not invited:
            raise HTTPException(403, "Anda tidak diundang ke war room ini.")

    elif role == "seksi":
        invited = (
            db.query(WarRoomSeksi)
            .filter(
                WarRoomSeksi.war_room_id == id,
                WarRoomSeksi.seksi_id == user_id
            )
            .first()
        )
        if not invited:
            raise HTTPException(403, "Anda tidak diundang ke war room ini.")

    else:
        raise HTTPException(403, "Akses ditolak.")

    opd_list = db.query(WarRoomOPD).filter_by(war_room_id=id).all()
    seksi_list = db.query(WarRoomSeksi).filter_by(war_room_id=id).all()


    ticket = db.query(Ticket).filter(Ticket.ticket_id == war_room.ticket_id).first()

    return {
        "war_room": war_room,
        "opd_undangan": opd_list,
        "seksi_undangan": seksi_list,
        "ticket": ticket
    }


