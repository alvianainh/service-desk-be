import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Response, Header, Query
from sqlalchemy.orm import Session
from datetime import datetime, time
from . import models, schemas
from auth.database import get_db
from auth.auth import get_current_user, get_user_by_email, get_current_user_masyarakat, get_current_user_universal
from tickets import models, schemas
from tickets.models import Tickets, TicketAttachment, TicketCategories, TicketUpdates, TeknisiTags, TeknisiLevels, TicketRatings, Notifications, RFCIncidentRepeat, RFCChangeRequest
from tickets.schemas import TicketCreateSchema, TicketResponseSchema, TicketCategorySchema, TicketForSeksiSchema, TicketTrackResponse, UpdatePriority, ManualPriority, RejectReasonSeksi, RejectReasonBidang, AssignTeknisiSchema, RFCIncidentRepeatSchema, RFCChangeRequestSchema
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
import requests




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
TRACE_BASE_URL = "https://trace-app.my.id"



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
@router.get("/notifications/teknisi")
def get_teknisi_notifications(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "teknisi":
        raise HTTPException(403, "Hanya teknisi yang bisa melihat notifikasi ini")

    teknisi_id = current_user.get("id")
    now = datetime.utcnow()

    tickets = db.query(Tickets).filter(
        Tickets.assigned_teknisi_id == teknisi_id,
        Tickets.status != "selesai",
        Tickets.pengerjaan_awal.isnot(None),
        Tickets.pengerjaan_akhir.isnot(None)
    ).all()

    for ticket in tickets:
        total_duration = (ticket.pengerjaan_akhir - ticket.pengerjaan_awal).total_seconds()
        elapsed = (now - ticket.pengerjaan_awal).total_seconds()
        if total_duration <= 0:
            continue
        progress = elapsed / total_duration

        if progress >= 0.75:
            existing = db.query(Notifications).filter_by(
                ticket_id=ticket.ticket_id,
                user_id=teknisi_id,
                status="SLA Warning"
            ).first()
            if not existing:
                db.add(Notifications(
                    user_id=teknisi_id,
                    ticket_id=ticket.ticket_id,
                    message=f"PERINGATAN: 75% waktu pengerjaan tiket {ticket.ticket_code} sudah lewat, tapi belum selesai!",
                    status="SLA Warning",
                    is_read=False,
                    created_at=now
                ))
                db.commit()

    notifications = db.query(Notifications).filter_by(
        user_id=teknisi_id
    ).order_by(Notifications.created_at.desc()).all()

    result = [{
        "id": str(n.id),
        "ticket_id": str(n.ticket_id),
        "message": n.message,
        "status": n.status,
        "is_read": n.is_read,
        "created_at": n.created_at
    } for n in notifications]

    total = len(result)
    unread = sum(1 for n in result if not n["is_read"])

    return {
        "total_notifications": total,
        "unread_notifications": unread,
        "notifications": result
    }

@router.get("/notifications/teknisi/{notification_id}")
def get_teknisi_notification_by_id(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "teknisi":
        raise HTTPException(403, "Hanya teknisi yang bisa melihat notifikasi ini")

    notif = db.query(Notifications).filter(
        Notifications.id == notification_id,
        Notifications.user_id == current_user["id"]
    ).first()

    if not notif:
        raise HTTPException(404, "Notifikasi tidak ditemukan")

    ticket = None
    if notif.ticket_id:
        ticket = db.query(Tickets).filter(Tickets.ticket_id == notif.ticket_id).first()

    result = {
        "notification_id": str(notif.id),
        "ticket_id": str(notif.ticket_id) if notif.ticket_id else None,
        "ticket_code": ticket.ticket_code if ticket else None,
        "message": notif.message,
        "status": notif.status,
        "is_read": notif.is_read,
        "created_at": notif.created_at
    }

    return {"data": result}

@router.patch("/notifications/teknisi/{notification_id}/read")
def mark_teknisi_notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "teknisi":
        raise HTTPException(403, "Hanya teknisi yang bisa mengubah notifikasi")

    notif = db.query(Notifications).filter(
        Notifications.id == notification_id,
        Notifications.user_id == current_user["id"]
    ).first()

    if not notif:
        raise HTTPException(404, "Notifikasi tidak ditemukan")

    notif.is_read = True
    db.commit()
    db.refresh(notif)

    return {
        "message": "Notifikasi berhasil ditandai sudah dibaca",
        "notification_id": str(notif.id),
        "is_read": notif.is_read
    }

@router.patch("/notifications/teknisi/read-all")
def mark_all_teknisi_notifications_read(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "teknisi":
        raise HTTPException(403, "Hanya teknisi yang bisa mengubah notifikasi")

    notifs = db.query(Notifications).filter(
        Notifications.user_id == current_user["id"],
        Notifications.is_read == False
    ).all()

    if not notifs:
        return {"message": "Tidak ada notifikasi baru untuk ditandai sudah dibaca"}

    for notif in notifs:
        notif.is_read = True

    db.commit()

    return {
        "message": f"{len(notifs)} notifikasi berhasil ditandai sudah dibaca"
    }

@router.delete("/notifications/teknisi/{notification_id}")
def delete_teknisi_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "teknisi":
        raise HTTPException(403, "Hanya teknisi yang bisa menghapus notifikasi")

    notif = db.query(Notifications).filter(
        Notifications.id == notification_id,
        Notifications.user_id == current_user["id"]
    ).first()

    if not notif:
        raise HTTPException(404, "Notifikasi tidak ditemukan")

    db.delete(notif)
    db.commit()

    return {
        "message": "Notifikasi berhasil dihapus",
        "notification_id": str(notification_id)
    }


@router.get("/dashboard/teknisi/summary")
def dashboard_teknisi_summary(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "teknisi":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya teknisi yang dapat melihat dashboard."
        )

    teknisi_user_id = current_user.get("id")
    teknisi_opd_id = current_user.get("dinas_id")

    if not teknisi_opd_id:
        raise HTTPException(
            status_code=400,
            detail="User tidak memiliki OPD"
        )

    tickets = db.query(models.Tickets) \
        .filter(models.Tickets.opd_id_tickets == teknisi_opd_id) \
        .filter(models.Tickets.assigned_teknisi_id == teknisi_user_id) \
        .all()

    total_tickets = len(tickets)
    in_progress = sum(1 for t in tickets if t.status in ["assigned to teknisi", "diproses"])
    reopen = sum(1 for t in tickets if t.status == "reopen")

    approaching_deadline = 0
    now = datetime.now()

    for t in tickets:
        if not t.pengerjaan_awal or not t.pengerjaan_akhir:
            continue

        if t.status == "selesai":
            continue

        try:
            awal = t.pengerjaan_awal
            akhir = t.pengerjaan_akhir
            total_durasi = akhir - awal
            threshold_time = awal + total_durasi * 0.75
            if now >= threshold_time:
                approaching_deadline += 1
        except Exception:
            continue

    return {
        "teknisi_id": teknisi_user_id,
        "opd_id": teknisi_opd_id,
        "total_tickets": total_tickets,
        "in_progress": in_progress,
        "reopen": reopen,
        "deadline": approaching_deadline
    }


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
                "rfc_required": t.rfc_required,

                "kategori_risiko_id_asset": t.kategori_risiko_id_asset,
                "kategori_risiko_nama_asset": t.kategori_risiko_nama_asset,
                "kategori_risiko_selera_negatif": t.kategori_risiko_selera_negatif,
                "kategori_risiko_selera_positif": t.kategori_risiko_selera_positif,
                "area_dampak_id_asset": t.area_dampak_id_asset,
                "area_dampak_nama_asset": t.area_dampak_nama_asset,
                "deskripsi_pengendalian_bidang": t.deskripsi_pengendalian_bidang,
                # "request_type": t.request_type,
                "incident_repeat_flag": t.incident_repeat_flag,

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

    allowed_status = ["assigned to teknisi", "diproses"]
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

        "kategori_risiko_id_asset": ticket.kategori_risiko_id_asset,
        "kategori_risiko_nama_asset": ticket.kategori_risiko_nama_asset,
        "kategori_risiko_selera_negatif": ticket.kategori_risiko_selera_negatif,
        "kategori_risiko_selera_positif": ticket.kategori_risiko_selera_positif,
        "area_dampak_id_asset": ticket.area_dampak_id_asset,
        "area_dampak_nama_asset": ticket.area_dampak_nama_asset,
        "deskripsi_pengendalian_bidang": ticket.deskripsi_pengendalian_bidang,
        # "rfc_required": ticket.rfc_required,
        "incident_repeat_flag": ticket.incident_repeat_flag,


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


# @router.put("/tickets/teknisi/{ticket_id}/process")
# async def teknisi_start_processing(
#     ticket_id: str,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_universal)
# ):
#     if current_user.get("role_name") != "teknisi":
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: hanya teknisi yang dapat memproses tiket."
#         )

#     teknisi_opd_id = current_user.get("dinas_id")
#     teknisi_user_id = current_user.get("id")

#     if not teknisi_opd_id:
#         raise HTTPException(status_code=400, detail="User tidak memiliki OPD.")

#     ticket = (
#         db.query(models.Tickets)
#         .filter(models.Tickets.ticket_id == ticket_id)
#         .first()
#     )

#     if not ticket:
#         raise HTTPException(status_code=404, detail="Ticket tidak ditemukan.")

#     old_status = ticket.status

#     if ticket.opd_id_tickets != teknisi_opd_id:
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: Tiket ini bukan dari OPD teknisi."
#         )

#     if str(ticket.assigned_teknisi_id) != str(teknisi_user_id):
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: Tiket tidak diassign ke teknisi ini."
#         )

#     if ticket.status != "assigned to teknisi":
#         raise HTTPException(
#             status_code=400,
#             detail="Tiket belum siap diproses oleh teknisi."
#         )

#     ticket.status = "diproses"
#     ticket.status_ticket_pengguna = "proses pengerjaan teknisi"
#     ticket.status_ticket_seksi = "diproses"
#     ticket.status_ticket_teknisi = "diproses"
#     ticket.pengerjaan_awal_teknisi = datetime.utcnow()

#     ticket.pengerjaan_awal = datetime.utcnow() 

#     db.commit()
#     db.refresh(ticket)

#     add_ticket_history(
#         db=db,
#         ticket=ticket,
#         old_status=old_status,
#         new_status=ticket.status, 
#         updated_by=UUID(current_user["id"]),
#         extra={"notes": "Tiket dibuat melalui pelaporan online"}
#     )

#     await update_ticket_status(
#         db=db,
#         ticket=ticket,
#         new_status="Proses Pengerjaan Teknisi",
#         updated_by=current_user["id"]
#     )

#     seksi_users = (
#         db.query(Users)
#         .join(Roles)
#         .filter(Roles.role_name == "seksi", Users.opd_id == teknisi_opd_id)
#         .all()
#     )

#     for seksi in seksi_users:
#         db.add(models.Notifications(
#             user_id=seksi.id,
#             ticket_id=ticket.ticket_id,
#             message=f"Tiket {ticket.ticket_code} sedang diproses oleh teknisi",
#             status="Tiket Diproses Teknisi",
#             is_read=False,
#             created_at=datetime.utcnow()
#         ))

#     db.commit()

#     return {
#         "message": "Tiket berhasil diperbarui menjadi diproses oleh teknisi.",
#         "ticket_id": str(ticket.ticket_id),
#         "status": ticket.status,
#         "status_ticket_pengguna": ticket.status_ticket_pengguna,
#         "status_ticket_seksi": ticket.status_ticket_seksi,
#         "status_ticket_teknisi": ticket.status_ticket_teknisi,
#         "pengerjaan_awal": ticket.pengerjaan_awal
#     }

TRACE_BASE_URL = "https://trace-app.my.id"

@router.put("/tickets/teknisi/{ticket_id}/process")
async def teknisi_start_processing(
    ticket_id: str,
    # rfc_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "teknisi":
        raise HTTPException(403, "Akses ditolak: hanya teknisi")

    teknisi_opd_id = current_user.get("dinas_id")
    teknisi_user_id = current_user.get("id")
    if not teknisi_opd_id:
        raise HTTPException(400, "User tidak memiliki OPD")

    ticket = db.query(models.Tickets).filter(models.Tickets.ticket_id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket tidak ditemukan")
    if ticket.opd_id_tickets != teknisi_opd_id:
        raise HTTPException(403, "Tiket ini bukan dari OPD teknisi")
    if str(ticket.assigned_teknisi_id) != str(teknisi_user_id):
        raise HTTPException(403, "Tiket tidak diassign ke teknisi ini")
    if ticket.status != "assigned to teknisi":
        raise HTTPException(400, "Tiket belum siap diproses oleh teknisi")

    trace_response = None
    rfc_ok = True 

    rfc_id = ticket.trace_rfc_id

    if rfc_id:
        rfc = db.query(RFCChangeRequest).filter(RFCChangeRequest.trace_rfc_id == rfc_id).first()
        if not rfc:
            raise HTTPException(404, "RFC TRACE tidak ditemukan")
        # --- update ke TRACE ---
        token = current_user.get("access_token")
        try:
            with requests.Session() as session:
                trace_res = session.post(
                    f"{TRACE_BASE_URL}/api/change-managements/{rfc_id}/implemented",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "accept": "application/json",
                        "X-CSRF-TOKEN": "",
                        "Content-Type": "application/json"
                    },
                    data="{}",
                    timeout=10
                )
                if trace_res.status_code in (200, 201):
                    trace_response = trace_res.json()
                else:
                    trace_response = {"error": trace_res.text}
                    rfc_ok = False  # RFC gagal → jangan update status tiket
        except Exception as e:
            trace_response = {"error": str(e)}
            rfc_ok = False  # RFC gagal → jangan update status tiket

    # --- update internal DB hanya jika RFC berhasil atau ticket tanpa RFC ---
    if rfc_ok:
        old_status = ticket.status
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

        # --- Notify seksi ---
        seksi_users = (
            db.query(Users)
            .join(Roles)
            .filter(Roles.role_name == "seksi", Users.opd_id == teknisi_opd_id)
            .all()
        )
        for seksi in seksi_users:
            db.add(models.Notifications(
                user_id=seksi.id,
                ticket_id=ticket.ticket_id,
                message=f"Tiket {ticket.ticket_code} sedang diproses oleh teknisi",
                status="Tiket Diproses Teknisi",
                is_read=False,
                created_at=datetime.utcnow()
            ))
        db.commit()

    return {
        "message": "Tiket berhasil diperbarui menjadi diproses oleh teknisi." if rfc_ok else "Tiket tidak dapat diproses karena RFC TRACE gagal.",
        "ticket_id": str(ticket.ticket_id),
        "trace_response": trace_response,
        "status_updated": rfc_ok
    }


@router.put("/tickets/teknisi/{ticket_id}/complete")
async def teknisi_complete_ticket(
    ticket_id: str,
    # rfc_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "teknisi":
        raise HTTPException(403, "Akses ditolak: hanya teknisi yang dapat menyelesaikan tiket.")

    teknisi_opd_id = current_user.get("dinas_id")
    teknisi_user_id = current_user.get("id")
    if not teknisi_opd_id:
        raise HTTPException(400, "User tidak memiliki OPD")

    ticket = db.query(models.Tickets).filter(models.Tickets.ticket_id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket tidak ditemukan")
    if ticket.opd_id_tickets != teknisi_opd_id:
        raise HTTPException(403, "Tiket ini bukan dari OPD teknisi")
    if str(ticket.assigned_teknisi_id) != str(teknisi_user_id):
        raise HTTPException(403, "Tiket tidak diassign ke teknisi ini")
    if ticket.status != "diproses":
        raise HTTPException(400, "Tiket belum bisa diselesaikan karena status bukan 'diproses'")

    trace_response = None
    rfc_ok = True  

    rfc_id = ticket.trace_rfc_id

    if rfc_id:
        token = current_user.get("access_token")
        try:
            with requests.Session() as session:
                trace_res = session.post(
                    f"{TRACE_BASE_URL}/api/change-managements/{rfc_id}/completed",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "accept": "application/json",
                        "X-CSRF-TOKEN": "",
                        "Content-Type": "application/json"
                    },
                    data="{}",
                    timeout=10
                )
                if trace_res.status_code in (200, 201):
                    trace_response = trace_res.json()
                else:
                    trace_response = {"error": trace_res.text}
                    rfc_ok = False  # RFC gagal → jangan update status tiket
        except Exception as e:
            trace_response = {"error": str(e)}
            rfc_ok = False  # RFC gagal → jangan update status tiket

    # --- update internal DB hanya jika RFC berhasil atau ticket tanpa RFC ---
    if rfc_ok:
        old_status = ticket.status
        ticket.status = "selesai"
        ticket.status_ticket_pengguna = "selesai"
        ticket.status_ticket_seksi = "normal"
        ticket.status_ticket_teknisi = "selesai"
        ticket.pengerjaan_akhir_teknisi = datetime.utcnow()

        # update kuota teknisi
        teknisi = db.query(Users).filter(Users.id == teknisi_user_id).first()
        if teknisi:
            teknisi.teknisi_kuota_terpakai = max(teknisi.teknisi_kuota_terpakai - 1, 0)

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

        # notif seksi
        seksi_users = (
            db.query(Users)
            .join(Roles)
            .filter(Roles.role_name == "seksi", Users.opd_id == teknisi_opd_id)
            .all()
        )
        for seksi in seksi_users:
            db.add(models.Notifications(
                user_id=seksi.id,
                ticket_id=ticket.ticket_id,
                message=f"Tiket {ticket.ticket_code} telah selesai diproses teknisi",
                status="Tiket Selesai",
                is_read=False,
                created_at=datetime.utcnow()
            ))
        db.commit()

    return {
        "message": "Tiket berhasil diselesaikan oleh teknisi." if rfc_ok else "Tiket tidak dapat diselesaikan karena RFC TRACE gagal.",
        "ticket_id": str(ticket.ticket_id),
        "trace_response": trace_response,
        "status_updated": rfc_ok
    }



# @router.put("/tickets/teknisi/{ticket_id}/complete")
# async def teknisi_complete_ticket(
#     ticket_id: str,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_universal)
# ):

#     if current_user.get("role_name") != "teknisi":
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: hanya teknisi yang dapat menyelesaikan tiket."
#         )

#     teknisi_opd_id = current_user.get("dinas_id")
#     teknisi_user_id = current_user.get("id")

#     if not teknisi_opd_id:
#         raise HTTPException(status_code=400, detail="User tidak memiliki OPD.")

#     ticket = (
#         db.query(models.Tickets)
#         .filter(models.Tickets.ticket_id == ticket_id)
#         .first()
#     )

#     if not ticket:
#         raise HTTPException(status_code=404, detail="Ticket tidak ditemukan.")

#     old_status = ticket.status

#     if ticket.opd_id_tickets != teknisi_opd_id:
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: Tiket ini bukan dari OPD teknisi."
#         )

#     if str(ticket.assigned_teknisi_id) != str(teknisi_user_id):
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: Tiket tidak diassign ke teknisi ini."
#         )

#     if ticket.status != "diproses":
#         raise HTTPException(
#             status_code=400,
#             detail="Tiket belum bisa diselesaikan karena tidak dalam status 'diproses'."
#         )

#     ticket.status = "selesai"
#     ticket.status_ticket_pengguna = "selesai"
#     ticket.status_ticket_seksi = "normal"
#     ticket.status_ticket_teknisi = "selesai"
#     ticket.pengerjaan_akhir_teknisi = datetime.utcnow()


#     teknisi = db.query(Users).filter(Users.id == teknisi_user_id).first()

#     if teknisi:
#         teknisi.teknisi_kuota_terpakai -= 1
#         if teknisi.teknisi_kuota_terpakai < 0:
#             teknisi.teknisi_kuota_terpakai = 0

#     db.commit()
#     db.refresh(ticket)

#     add_ticket_history(
#         db=db,
#         ticket=ticket,
#         old_status=old_status,
#         new_status=ticket.status, 
#         updated_by=UUID(current_user["id"]),
#         extra={"notes": "Tiket dibuat melalui pelaporan online"}
#     )

#     await update_ticket_status(
#         db=db,
#         ticket=ticket,
#         new_status="Selesai",
#         updated_by=current_user["id"]
#     )

#     # ==== notif seksi OPD teknisi ====
#     seksi_users = (
#         db.query(Users)
#         .join(Roles)
#         .filter(Roles.role_name == "seksi", Users.opd_id == teknisi_opd_id)
#         .all()
#     )

#     for seksi in seksi_users:
#         db.add(models.Notifications(
#             user_id=seksi.id,
#             ticket_id=ticket.ticket_id,
#             message=f"Tiket {ticket.ticket_code} telah selesai diproses teknisi",
#             status="Tiket Selesai",
#             is_read=False,
#             created_at=datetime.utcnow()
#         ))

#     db.commit()

#     return {
#         "message": "Tiket berhasil diselesaikan oleh teknisi.",
#         "ticket_id": str(ticket.ticket_id),
#         "status": ticket.status,
#         "status_ticket_pengguna": ticket.status_ticket_pengguna,
#         "status_ticket_seksi": ticket.status_ticket_seksi,
#         "status_ticket_teknisi": ticket.status_ticket_teknisi,
#         "pengerjaan_akhir_teknisi": ticket.pengerjaan_akhir_teknisi
#     }

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
            "request_type": t.request_type,

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

        "kategori_risiko_id_asset": ticket.kategori_risiko_id_asset,
        "kategori_risiko_nama_asset": ticket.kategori_risiko_nama_asset,
        "kategori_risiko_selera_negatif": ticket.kategori_risiko_selera_negatif,
        "kategori_risiko_selera_positif": ticket.kategori_risiko_selera_positif,
        "area_dampak_id_asset": ticket.area_dampak_id_asset,
        "area_dampak_nama_asset": ticket.area_dampak_nama_asset,
        "deskripsi_pengendalian_bidang": ticket.deskripsi_pengendalian_bidang,
        "request_type": ticket.request_type,

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


@router.get("/configuration-items/active")
def get_active_configuration_items(
    current_user: dict = Depends(get_current_user_universal)
):
    token = current_user.get("access_token")

    url = "https://trace-app.my.id/api/configuration-items/search"

    headers = {
        "Authorization": f"Bearer {token}",
        "accept": "application/json"
    }

    # pagination default
    page = 1
    per_page = 100

    all_data = []

    while True:
        params = {
            "type": "other",
            "status": "active",
            "page": page,
            "per_page": per_page
        }

        response = requests.get(url, headers=headers, params=params)

        if response.status_code != 200:
            raise HTTPException(
                status_code=500,
                detail=f"Gagal fetch data CI dari Change: {response.text}"
            )

        result = response.json()

        # append data CI
        all_data.extend(result.get("data", []))

        pagination = result.get("pagination", {})
        last_page = pagination.get("last_page", 1)

        # kalau sudah di halaman terakhir → stop loop
        if page >= last_page:
            break

        page += 1

    return {
        "success": True,
        "total": len(all_data),
        "items": all_data
    }

ARISE_BASE_URL = "https://arise-app.my.id"

@router.post("/rfc/incident-repeat")
def create_rfc_incident_repeat(
    payload: RFCIncidentRepeatSchema,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "teknisi":
        raise HTTPException(403, "Akses ditolak: hanya teknisi")

    token = current_user.get("access_token")
    if not token:
        raise HTTPException(401, "Token tidak ditemukan")

    user = (
        db.query(Users)
        .filter(Users.id == current_user["id"])
        .first()
    )

    if not user:
        raise HTTPException(400, "User tidak ditemukan")

    nama_pemohon = user.full_name

    opd_pemohon = current_user.get("dinas_name")
    if not opd_pemohon:
        raise HTTPException(400, "Nama OPD tidak ditemukan di token")

    asset_res = requests.get(
        f"{ARISE_BASE_URL}/api/asset-barang/{payload.id_aset}",
        headers={
            "Authorization": f"Bearer {token}",
            "accept": "application/json"
        }
    )

    if asset_res.status_code != 200:
        raise HTTPException(400, f"Gagal fetch asset: {asset_res.text}")

    asset_data = asset_res.json()["data"]

    kategori_aset = asset_data.get("kategori")
    risk_score_aset = asset_data.get("nilai_resiko") or 0

    deskripsi_aset = payload.deskripsi_aset

    trace_payload = {
        "judul_perubahan": payload.judul_perubahan,
        "kategori_aset": kategori_aset,
        "id_aset": payload.id_aset,
        "deskripsi_aset": deskripsi_aset,
        "alasan_perubahan": payload.alasan_perubahan,
        "dampak_perubahan": payload.dampak_perubahan,
        "dampak_jika_tidak": payload.dampak_jika_tidak,
        "biaya_estimasi": payload.biaya_estimasi,
        "nama_pemohon": nama_pemohon,   
        "opd_pemohon": opd_pemohon,
        "risk_score_aset": risk_score_aset,
    }

    trace_res = requests.post(
        f"{TRACE_BASE_URL}/api/change-managements",
        json=trace_payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    )

    if trace_res.status_code not in (200, 201):
        raise HTTPException(400, f"Gagal create RFC: {trace_res.text}")

    trace_data = trace_res.json()
    trace_rfc_id = trace_data.get("data", {}).get("id")

    new_rfc = RFCIncidentRepeat(
        judul_perubahan=payload.judul_perubahan,
        kategori_aset=kategori_aset,
        id_aset=payload.id_aset,
        deskripsi_aset=deskripsi_aset,
        alasan_perubahan=payload.alasan_perubahan,
        dampak_perubahan=payload.dampak_perubahan,
        dampak_jika_tidak=payload.dampak_jika_tidak,
        biaya_estimasi=payload.biaya_estimasi,
        nama_pemohon=nama_pemohon,   
        opd_pemohon=opd_pemohon,
        risk_score_aset=risk_score_aset,
        dibuat_oleh=current_user["id"],
        trace_rfc_id=trace_rfc_id
    )

    db.add(new_rfc)
    db.commit()
    db.refresh(new_rfc)

    return {
        "message": "RFC insiden berulang berhasil diajukan",
        "local_rfc_id": str(new_rfc.id),
        "trace_response": trace_data
    }

@router.get("/rfc/incident-repeat")
def get_rfc_incident_repeat(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "teknisi":
        raise HTTPException(403, "Akses ditolak: hanya teknisi")

    token = current_user.get("access_token")
    if not token:
        raise HTTPException(401, "Token tidak ditemukan")

    rfcs = (
        db.query(RFCIncidentRepeat)
        .filter(RFCIncidentRepeat.dibuat_oleh == current_user["id"])
        .order_by(RFCIncidentRepeat.created_at.desc())
        .all()
    )

    results = []

    for r in rfcs:
        status_trace = None

        # --- Fetch status dari TRACE ---
        if r.trace_rfc_id:
            try:
                trace_res = requests.get(
                    f"{TRACE_BASE_URL}/api/change-managements/{r.trace_rfc_id}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "accept": "application/json"
                    }
                )

                if trace_res.status_code == 200:
                    trace_data = trace_res.json().get("data", {})
                    status_trace = trace_data.get("status")  # <--- ini status RFC
            except Exception:
                status_trace = None  # biar ga error

        results.append({
            "local_rfc_id": str(r.id),
            "trace_rfc_id": r.trace_rfc_id,
            "judul_perubahan": r.judul_perubahan,
            "kategori_aset": r.kategori_aset,
            "id_aset": r.id_aset,
            "deskripsi_aset": r.deskripsi_aset,
            "alasan_perubahan": r.alasan_perubahan,
            "dampak_perubahan": r.dampak_perubahan,
            "dampak_jika_tidak": r.dampak_jika_tidak,
            "biaya_estimasi": r.biaya_estimasi,
            "nama_pemohon": r.nama_pemohon,
            "opd_pemohon": r.opd_pemohon,
            "risk_score_aset": r.risk_score_aset,
            "created_at": r.created_at,
            "status_trace": status_trace  # <--- status dari TRACE
        })

    return {
        "total": len(results),
        "data": results
    }


@router.get("/rfc/incident-repeat/{local_rfc_id}")
def get_rfc_incident_repeat_by_id(
    local_rfc_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "teknisi":
        raise HTTPException(403, "Akses ditolak: hanya teknisi")

    token = current_user.get("access_token")
    if not token:
        raise HTTPException(401, "Token tidak ditemukan")

    # Ambil RFC dari tabel lokal
    r = (
        db.query(RFCIncidentRepeat)
        .filter(
            RFCIncidentRepeat.id == local_rfc_id,
            RFCIncidentRepeat.dibuat_oleh == current_user["id"]
        )
        .first()
    )

    if not r:
        raise HTTPException(404, "RFC tidak ditemukan")

    # Ambil status dari TRACE kalau ada
    status_trace = None
    if r.trace_rfc_id:
        try:
            trace_res = requests.get(
                f"{TRACE_BASE_URL}/api/change-managements/{r.trace_rfc_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "accept": "application/json"
                }
            )
            if trace_res.status_code == 200:
                trace_data = trace_res.json().get("data", {})
                status_trace = trace_data.get("status")
        except Exception:
            status_trace = None

    result = {
        "local_rfc_id": str(r.id),
        "trace_rfc_id": r.trace_rfc_id,
        "judul_perubahan": r.judul_perubahan,
        "kategori_aset": r.kategori_aset,
        "id_aset": r.id_aset,
        "deskripsi_aset": r.deskripsi_aset,
        "alasan_perubahan": r.alasan_perubahan,
        "dampak_perubahan": r.dampak_perubahan,
        "dampak_jika_tidak": r.dampak_jika_tidak,
        "biaya_estimasi": r.biaya_estimasi,
        "nama_pemohon": r.nama_pemohon,
        "opd_pemohon": r.opd_pemohon,
        "risk_score_aset": r.risk_score_aset,
        "created_at": r.created_at,
        "status_trace": status_trace
    }

    return result


@router.post("/rfc/change-request")
def create_rfc_change_request(
    payload: RFCChangeRequestSchema,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "teknisi":
        raise HTTPException(403, "Akses ditolak: hanya teknisi")

    token = current_user.get("access_token")
    if not token:
        raise HTTPException(401, "Token tidak ditemukan")

    # Ambil tiket terkait
    ticket = db.query(Tickets).filter(Tickets.ticket_id == payload.ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Tiket tidak ditemukan")

    # Nama pemohon & OPD dari current_user
    nama_pemohon = current_user.get("full_name")
    opd_pemohon = current_user.get("dinas_name")

    # Ambil data asset dari ARISE
    asset_res = requests.get(
        f"{ARISE_BASE_URL}/api/asset-barang/{payload.id_aset}",
        headers={
            "Authorization": f"Bearer {token}",
            "accept": "application/json"
        }
    )
    if asset_res.status_code != 200:
        raise HTTPException(400, f"Gagal fetch asset: {asset_res.text}")

    asset_data = asset_res.json()["data"]
    kategori_aset = asset_data.get("kategori")
    risk_score_aset = asset_data.get("nilai_resiko") or 0

    deskripsi_aset = payload.deskripsi_aset

    # Prepare payload ke TRACE
    trace_payload = {
        "judul_perubahan": payload.judul_perubahan,
        "kategori_aset": kategori_aset,
        "id_aset": payload.id_aset,
        "deskripsi_aset": deskripsi_aset,
        "alasan_perubahan": payload.alasan_perubahan,
        "dampak_perubahan": payload.dampak_perubahan,
        "dampak_jika_tidak": payload.dampak_jika_tidak,
        "biaya_estimasi": payload.biaya_estimasi,
        "nama_pemohon": nama_pemohon,
        "opd_pemohon": opd_pemohon,
        "risk_score_aset": risk_score_aset,
    }

    trace_res = requests.post(
        f"{TRACE_BASE_URL}/api/change-managements",
        json=trace_payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    )
    if trace_res.status_code not in (200, 201):
        raise HTTPException(400, f"Gagal create RFC: {trace_res.text}")

    trace_data = trace_res.json()
    trace_rfc_id = trace_data.get("data", {}).get("id")

    new_rfc = RFCChangeRequest(
        ticket_id=payload.ticket_id,
        judul_perubahan=payload.judul_perubahan,
        kategori_aset=kategori_aset,
        id_aset=payload.id_aset,
        requested_by=current_user["id"],
        deskripsi_aset=deskripsi_aset,
        alasan_perubahan=payload.alasan_perubahan,
        dampak_perubahan=payload.dampak_perubahan,
        dampak_jika_tidak=payload.dampak_jika_tidak,
        biaya_estimasi=payload.biaya_estimasi,
        nama_pemohon=nama_pemohon,
        opd_pemohon=opd_pemohon,
        risk_score_aset=risk_score_aset,
        status="pending",
        trace_rfc_id=trace_rfc_id
    )

    db.add(new_rfc)
    # db.commit()
    # db.refresh(new_rfc)

    # Update tiket supaya teknisi tidak bisa mengerjakan sebelum RFC disetujui
    ticket.status_ticket_seksi = "Menunggu RFC disetujui"
    ticket.rfc_required = True
    ticket.trace_rfc_id = trace_rfc_id

    db.commit()
    db.refresh(new_rfc)
    db.refresh(ticket)

    return {
        "message": "RFC change request berhasil diajukan",
        "local_rfc_id": str(new_rfc.id),
        "trace_response": trace_data,
        "ticket_status": ticket.status_ticket_seksi,
        "ticket_trace_rfc_id": ticket.trace_rfc_id,
        "ticket_rfc_required": ticket.rfc_required
    }

@router.get("/rfc/change-request")
def get_rfc_change_requests(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "teknisi":
        raise HTTPException(403, "Akses ditolak: hanya teknisi")

    token = current_user.get("access_token")
    if not token:
        raise HTTPException(401, "Token tidak ditemukan")

    rfcs = (
        db.query(RFCChangeRequest)
        .filter(RFCChangeRequest.requested_by == current_user["id"])
        .order_by(RFCChangeRequest.created_at.desc())
        .all()
    )

    results = []
    for r in rfcs:
        status_trace = None

        # --- Fetch status dari TRACE jika ada trace_rfc_id ---
        if r.trace_rfc_id:
            try:
                trace_res = requests.get(
                    f"{TRACE_BASE_URL}/api/change-managements/{r.trace_rfc_id}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "accept": "application/json"
                    }
                )
                if trace_res.status_code == 200:
                    trace_data = trace_res.json().get("data", {})
                    status_trace = trace_data.get("status")
            except Exception:
                status_trace = None

        # Ambil info tiket terkait
        ticket = db.query(Tickets).filter(Tickets.ticket_id == r.ticket_id).first()
        ticket_code = ticket.ticket_code if ticket else None
        ticket_status = ticket.status_ticket_seksi if ticket else None

        results.append({
            "local_rfc_id": str(r.id),
            "trace_rfc_id": r.trace_rfc_id,
            "ticket_id": str(r.ticket_id),
            "ticket_code": ticket_code,
            "judul_perubahan": r.judul_perubahan,
            "kategori_aset": r.kategori_aset,
            "id_aset": r.id_aset,
            "deskripsi_aset": r.deskripsi_aset,
            "alasan_perubahan": r.alasan_perubahan,
            "dampak_perubahan": r.dampak_perubahan,
            "dampak_jika_tidak": r.dampak_jika_tidak,
            "biaya_estimasi": r.biaya_estimasi,
            "nama_pemohon": r.nama_pemohon,
            "opd_pemohon": r.opd_pemohon,
            "risk_score_aset": r.risk_score_aset,
            "status_trace": status_trace,
            "created_at": r.created_at,
            "ticket_status": ticket_status
        })

    return {
        "total": len(results),
        "data": results
    }

@router.get("/rfc/change-request/{local_rfc_id}")
def get_rfc_change_request_by_id(
    local_rfc_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "teknisi":
        raise HTTPException(403, "Akses ditolak: hanya teknisi")

    token = current_user.get("access_token")
    if not token:
        raise HTTPException(401, "Token tidak ditemukan")

    rfc = db.query(RFCChangeRequest).filter(
        RFCChangeRequest.id == local_rfc_id,
        RFCChangeRequest.requested_by == current_user["id"]
    ).first()

    if not rfc:
        raise HTTPException(404, "RFC Change Request tidak ditemukan")

    # Ambil status dari TRACE
    status_trace = None
    if rfc.trace_rfc_id:
        try:
            trace_res = requests.get(
                f"{TRACE_BASE_URL}/api/change-managements/{rfc.trace_rfc_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "accept": "application/json"
                }
            )
            if trace_res.status_code == 200:
                trace_data = trace_res.json().get("data", {})
                status_trace = trace_data.get("status")
        except Exception:
            status_trace = None

    # Ambil info tiket terkait
    ticket = db.query(Tickets).filter(Tickets.ticket_id == rfc.ticket_id).first()
    ticket_code = ticket.ticket_code if ticket else None
    ticket_status = ticket.status_ticket_seksi if ticket else None

    return {
        "local_rfc_id": str(rfc.id),
        "trace_rfc_id": rfc.trace_rfc_id,
        "ticket_id": str(rfc.ticket_id),
        "ticket_code": ticket_code,
        "judul_perubahan": rfc.judul_perubahan,
        "kategori_aset": rfc.kategori_aset,
        "id_aset": rfc.id_aset,
        "deskripsi_aset": rfc.deskripsi_aset,
        "alasan_perubahan": rfc.alasan_perubahan,
        "dampak_perubahan": rfc.dampak_perubahan,
        "dampak_jika_tidak": rfc.dampak_jika_tidak,
        "biaya_estimasi": rfc.biaya_estimasi,
        "nama_pemohon": rfc.nama_pemohon,
        "opd_pemohon": rfc.opd_pemohon,
        "risk_score_aset": rfc.risk_score_aset,
        "status_trace": status_trace,
        "created_at": rfc.created_at,
        "ticket_status": ticket_status
    }