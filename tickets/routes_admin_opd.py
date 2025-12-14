import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Response, Query, Path
from sqlalchemy.orm import Session
from datetime import datetime, time, timedelta, timezone
from . import models, schemas
from auth.database import get_db
from auth.auth import get_current_user, get_user_by_email, get_current_user_masyarakat, get_current_user_universal
from tickets import models, schemas
from tickets.models import Tickets, TicketAttachment, TicketCategories, TicketUpdates, TeknisiTags, TeknisiLevels, TicketRatings, WarRoom, WarRoomOPD, WarRoomSeksi, TicketServiceRequests, Notifications, Announcements
from tickets.schemas import TicketCreateSchema, TicketResponseSchema, TicketCategorySchema, TicketForSeksiSchema, TicketTrackResponse, UpdatePriority, ManualPriority, RejectReasonSeksi, RejectReasonBidang, AssignTeknisiSchema
import uuid
from auth.models import Opd, Dinas, Roles, Users, Articles
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


@router.get("/notifications-all/admin-dinas")
def get_admin_dinas_notifications(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    # ✅ Cek role admin dinas
    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(403, "Akses ditolak: hanya admin dinas yang dapat melihat notifikasi")

    try:
        admin_uuid = UUID(current_user["id"])
    except ValueError:
        raise HTTPException(400, "User ID tidak valid")

    opd_id = current_user.get("dinas_id")
    now = datetime.utcnow()

    # 1️⃣ SLA Warning: semua tiket di OPD belum selesai & ada pengerjaan awal & akhir
    tickets = db.query(Tickets).filter(
        Tickets.opd_id_tickets == opd_id,
        Tickets.status != "selesai",
        Tickets.pengerjaan_awal.isnot(None),
        Tickets.pengerjaan_akhir.isnot(None)
    ).all()

    for ticket in tickets:
        if not ticket.ticket_id:
            continue
        total_duration = (ticket.pengerjaan_akhir - ticket.pengerjaan_awal).total_seconds()
        elapsed = (now - ticket.pengerjaan_awal).total_seconds()
        if total_duration <= 0:
            continue
        progress = elapsed / total_duration

        if progress >= 0.75:
            existing = db.query(Notifications).filter_by(
                ticket_id=ticket.ticket_id,
                user_id=admin_uuid,
                status="SLA Warning"
            ).first()
            if not existing:
                teknisi = str(ticket.assigned_teknisi_id) if ticket.assigned_teknisi_id else "Belum ditugaskan"
                db.add(Notifications(
                    user_id=admin_uuid,
                    ticket_id=ticket.ticket_id,
                    message=f"PERINGATAN: 75% waktu pengerjaan tiket {ticket.ticket_code or 'N/A'} oleh teknisi {teknisi} sudah lewat tapi belum selesai!",
                    status="SLA Warning",
                    is_read=False,
                    created_at=now,
                    notification_type="ticket"
                ))
                db.commit()

    # 2️⃣ Notifikasi tiket (termasuk SLA warning)
    ticket_notifications = (
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
        .filter(Notifications.user_id == admin_uuid, Tickets.opd_id_tickets == opd_id)
        .order_by(Notifications.created_at.desc())
        .all()
    )

    ticket_data = [
        {
            "notification_id": str(n.notification_id),
            "ticket_id": str(n.ticket_id) if n.ticket_id else None,
            "ticket_code": n.ticket_code,
            "request_type": n.request_type,
            "opd_id_tiket": str(n.opd_id_tiket),
            "nama_dinas": n.nama_dinas,
            "rejection_reason_seksi": n.rejection_reason_seksi,
            "status_ticket_pengguna": n.status_ticket_pengguna,
            "message": n.message,
            "is_read": n.is_read,
            "created_at": n.created_at.replace(tzinfo=timezone.utc) if n.created_at.tzinfo is None else n.created_at,
            "notification_type": "ticket"
        }
        for n in ticket_notifications
    ]

    # 3️⃣ Notifikasi pengumuman
    announcement_notifications = (
        db.query(
            Notifications.id.label("notification_id"),
            Notifications.announcement_id,
            Notifications.message,
            Notifications.is_read,
            Notifications.created_at,
            Announcements.title,
            Announcements.content,
            Announcements.attachment_url,
            Announcements.attachment_type,
            Announcements.external_link,
            Announcements.created_by
        )
        .join(Announcements, Announcements.id == Notifications.announcement_id)
        .filter(
            Notifications.user_id == admin_uuid,
            Notifications.notification_type == "announcement",
            Announcements.is_active == True
        )
        .order_by(Notifications.created_at.desc())
        .all()
    )

    announcement_data = [
        {
            "notification_id": str(n.notification_id),
            "announcement_id": str(n.announcement_id),
            "title": n.title,
            "content": n.content,
            "attachment_url": n.attachment_url,
            "attachment_type": n.attachment_type,
            "external_link": n.external_link,
            "created_by": str(n.created_by),
            "created_at": n.created_at.replace(tzinfo=timezone.utc) if n.created_at.tzinfo is None else n.created_at,
            "message": n.message,
            "is_read": n.is_read,
            "notification_type": "announcement"
        }
        for n in announcement_notifications
    ]

    article_notifications = (
        db.query(
            Notifications.id.label("notification_id"),
            Notifications.message,
            Notifications.is_read,
            Notifications.created_at,
            Articles.title.label("article_title"),
            Articles.article_id.label("article_id")
        )
        .join(Articles, Articles.article_id == Notifications.article_id)
        .filter(
            Notifications.user_id == admin_uuid,
            Notifications.notification_type == "article"
        )
        .order_by(Notifications.created_at.desc())
        .all()
    )

    article_data = [
        {
            "notification_id": str(n.notification_id),
            "article_id": str(n.article_id),
            "title": n.article_title,
            "message": n.message,
            "is_read": n.is_read,
            "created_at": n.created_at.replace(tzinfo=timezone.utc) if n.created_at.tzinfo is None else n.created_at,
            "notification_type": "article"
        }
        for n in article_notifications
    ]

    # 4️⃣ Gabungkan & urut berdasarkan created_at
    war_room_notifications = (
        db.query(
            Notifications.id.label("notification_id"),
            Notifications.war_room_id,
            Notifications.message,
            Notifications.is_read,
            Notifications.created_at,
            WarRoom.title.label("war_room_title"),
            WarRoom.link_meet,
            WarRoom.start_time,
            WarRoom.end_time,
            WarRoom.ticket_id.label("ticket_id")
        )
        .join(WarRoom, WarRoom.id == Notifications.war_room_id)
        .filter(
            Notifications.user_id == admin_uuid,
            Notifications.notification_type == "war_room"
        )
        .order_by(Notifications.created_at.desc())
        .all()
    )

    war_room_data = []
    for n in war_room_notifications:
        war_room_data.append({
            "notification_id": str(n.notification_id),
            "war_room_id": str(n.war_room_id),
            "title": n.war_room_title,
            "link_meet": n.link_meet,
            "start_time": n.start_time,
            "end_time": n.end_time,
            "message": n.message,
            "is_read": n.is_read,
            "created_at": n.created_at.replace(tzinfo=timezone.utc) if n.created_at.tzinfo is None else n.created_at,
            "notification_type": "war_room",
            "ticket_id": str(n.ticket_id) if n.ticket_id else None  # cukup ID tiket saja
        })

        war_room_data.append({
            "notification_id": str(n.notification_id),
            "war_room_id": str(n.war_room_id),
            "title": n.war_room_title,
            "link_meet": n.link_meet,
            "start_time": n.start_time,
            "end_time": n.end_time,
            "message": n.message,
            "is_read": n.is_read,
            "created_at": n.created_at.replace(tzinfo=timezone.utc) if n.created_at.tzinfo is None else n.created_at,
            "notification_type": "war_room",
            "ticket_metadata": ticket_data
        })

    # Gabungkan semua notif
    all_notifications = ticket_data + announcement_data + article_data + war_room_data
    all_notifications.sort(key=lambda x: x["created_at"], reverse=True)

    total = len(all_notifications)
    unread = sum(1 for n in all_notifications if not n["is_read"])

    return {
        "status": "success",
        "total_notifications": total,
        "unread_notifications": unread,
        "data": all_notifications
    }

@router.get("/notifications/admin-dinas/{notification_id}")
def get_admin_dinas_notification_by_id(
    notification_id: str = Path(..., description="ID notifikasi"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    # ✅ Cek role
    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(403, "Akses ditolak: hanya admin dinas yang dapat melihat notifikasi")

    try:
        notif_uuid = UUID(notification_id)
        admin_uuid = UUID(current_user["id"])
    except ValueError:
        raise HTTPException(400, "ID notifikasi atau user tidak valid")

    # Ambil notifikasi
    notif = db.query(Notifications).filter(
        Notifications.id == notif_uuid,
        Notifications.user_id == admin_uuid
    ).first()

    if not notif:
        raise HTTPException(404, "Notifikasi tidak ditemukan")

    # Detail tergantung tipe notifikasi
    data = {
        "notification_id": str(notif.id),
        "message": notif.message,
        "status": notif.status,
        "is_read": notif.is_read,
        "created_at": notif.created_at.replace(tzinfo=timezone.utc) if notif.created_at.tzinfo is None else notif.created_at,
        "notification_type": notif.notification_type
    }

    if notif.notification_type == "ticket" and notif.ticket:
        opd = db.query(Dinas.nama).filter(Dinas.id == notif.ticket.opd_id_tickets).first()
        data.update({
            "ticket_id": str(notif.ticket.ticket_id),
            "ticket_code": notif.ticket.ticket_code,
            "request_type": notif.ticket.request_type,
            "opd_id_tiket": str(notif.ticket.opd_id_tickets),
            "nama_dinas": opd.nama if opd else None,
            "rejection_reason_seksi": notif.ticket.rejection_reason_seksi,
            "status_ticket_pengguna": notif.ticket.status_ticket_pengguna,
            "assigned_teknisi_id": str(notif.ticket.assigned_teknisi_id) if notif.ticket.assigned_teknisi_id else None
        })
    elif notif.notification_type == "announcement" and notif.announcement:
        data.update({
            "announcement_id": str(notif.announcement.id),
            "title": notif.announcement.title,
            "content": notif.announcement.content,
            "attachment_url": notif.announcement.attachment_url,
            "attachment_type": notif.announcement.attachment_type,
            "external_link": notif.announcement.external_link,
            "created_by": str(notif.announcement.created_by)
        })

    elif notif.notification_type == "war_room" and notif.war_room_id:
        war_room = db.query(WarRoom).filter(WarRoom.id == notif.war_room_id).first()
        if not war_room:
            raise HTTPException(404, "War Room tidak ditemukan")

        data.update({
            "war_room_id": str(war_room.id),
            "title": war_room.title,
            "link_meet": war_room.link_meet,
            "start_time": war_room.start_time,
            "end_time": war_room.end_time
        })

        # Ambil tiket dari war room
        if war_room.ticket_id:
            ticket = db.query(Tickets).filter(Tickets.ticket_id == war_room.ticket_id).first()
            if ticket:
                opd = db.query(Dinas.nama).filter(Dinas.id == ticket.opd_id_tickets).first()
                attachments = db.query(TicketAttachment).filter(TicketAttachment.has_id == ticket.ticket_id).all()
                
                ticket_data = {
                    "ticket_id": str(ticket.ticket_id),
                    "ticket_code": ticket.ticket_code,
                    "title": ticket.title,
                    "description": ticket.description,
                    "status": ticket.status,
                    "rejection_reason_bidang": ticket.rejection_reason_bidang,
                    "priority": ticket.priority,
                    "created_at": ticket.created_at,
                    "ticket_source": ticket.ticket_source,
                    "status_ticket_pengguna": ticket.status_ticket_pengguna,
                    "status_ticket_seksi": ticket.status_ticket_seksi,
                    "request_type": ticket.request_type,
                    "nilai_risiko_asset": ticket.nilai_risiko_asset,
                    "opd_id_tickets": ticket.opd_id_tickets,
                    "lokasi_kejadian": ticket.lokasi_kejadian,
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
                        } for a in attachments
                    ],
                    "nama_dinas": opd.nama if opd else None,
                    "rejection_reason_seksi": ticket.rejection_reason_seksi,
                    "assigned_teknisi_id": str(ticket.assigned_teknisi_id) if ticket.assigned_teknisi_id else None
                }

                # 🔹 Masukkan ticket_data ke response
                data["ticket"] = ticket_data



    return {"status": "success", "data": data}


@router.patch("/notifications-opd/{notification_id}/read")
def mark_notification_as_read(
    notification_id: str = Path(..., description="ID notifikasi"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    try:
        notif_uuid = UUID(notification_id)
        user_uuid = UUID(current_user["id"])
    except ValueError:
        raise HTTPException(400, "ID notifikasi atau user tidak valid")

    notif = db.query(Notifications).filter(
        Notifications.id == notif_uuid,
        Notifications.user_id == user_uuid
    ).first()

    if not notif:
        raise HTTPException(404, "Notifikasi tidak ditemukan")

    notif.is_read = True
    db.commit()

    return {"status": "success", "message": "Notifikasi telah ditandai sebagai dibaca"}


# 2️⃣ Mark as read all notifications for the user
@router.patch("/notifications-opd/read-all")
def mark_all_notifications_as_read(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    user_uuid = current_user["id"]

    updated = db.query(Notifications).filter(
        Notifications.user_id == user_uuid,
        Notifications.is_read == False
    ).update({Notifications.is_read: True}, synchronize_session=False)

    db.commit()

    return {
        "status": "success",
        "message": f"{updated} notifikasi telah ditandai sebagai dibaca"
    }

@router.delete("/notifications-opd/{notification_id}")
def delete_notification_by_id(
    notification_id: str = Path(..., description="ID notifikasi"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    try:
        notif_uuid = UUID(notification_id)
        user_uuid = UUID(current_user["id"])
    except ValueError:
        raise HTTPException(400, "ID notifikasi atau user tidak valid")

    notif = db.query(Notifications).filter(
        Notifications.id == notif_uuid,
        Notifications.user_id == user_uuid
    ).first()

    if not notif:
        raise HTTPException(404, "Notifikasi tidak ditemukan")

    db.delete(notif)
    db.commit()

    return {"status": "success", "message": "Notifikasi berhasil dihapus"}



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
            models.Tickets.request_type == "pelaporan_online",
            models.Tickets.status == "selesai"  # <-- hanya tiket selesai
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

        # if not rating:
        #     continue

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

            "rating": rating.rating if rating else None,
            "comment": rating.comment if rating else None,
            "rated_at": rating.created_at if rating else None,

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

@router.get("/admin-opd/statistik/pelaporan-online/rekap")
def get_rekap_pelaporan_online_bulanan(
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin OPD."
        )

    opd_id_user = current_user.get("dinas_id")

    if not year:
        year = datetime.now().year

    raw_result = (
        db.query(
            extract("month", models.Tickets.created_at).label("bulan"),
            func.count(models.Tickets.ticket_id).label("total")
        )
        .filter(
            models.Tickets.opd_id_tickets == opd_id_user,
            models.Tickets.request_type == "pelaporan_online",
            models.Tickets.status == "selesai",
            extract("year", models.Tickets.created_at) == year
        )
        .group_by(extract("month", models.Tickets.created_at))
        .all()
    )

    hasil_map = {int(r.bulan): r.total for r in raw_result}

    rekap = []
    for bulan in range(1, 13):
        rekap.append({
            "bulan": bulan,
            "total_tiket": hasil_map.get(bulan, 0)  
        })

    return {
        "tahun": year,
        "opd_id": opd_id_user,
        "rekap": rekap
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
            models.Tickets.request_type == "pelaporan_online",
            models.Tickets.status == "selesai"  # <-- hanya tiket selesai
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
            models.Tickets.request_type == "pelaporan_online",
            models.Tickets.status == "selesai"  # <-- hanya tiket selesai
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


@router.get("/admin-opd/statistik/pelaporan-online/filter")
def get_ratings_pelaporan_online_filter(
    month: Optional[int] = Query(None, ge=1, le=12, description="Filter bulan (1-12)"),
    year: Optional[int] = Query(None, description="Filter tahun (YYYY)"),
    source: Optional[str] = Query(None, description="Filter ticket_source: Masyarakat / Pegawai"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    # Hanya admin dinas
    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin OPD yang dapat melihat data rating."
        )

    opd_id_user = current_user.get("dinas_id")

    # Base query
    query = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.opd_id_tickets == opd_id_user,
            models.Tickets.request_type == "pelaporan_online",
            models.Tickets.status == "selesai"
        )
    )

    # Filter source
    if source in ["Masyarakat", "Pegawai"]:
        query = query.filter(models.Tickets.ticket_source == source)

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

    tickets = query.order_by(models.Tickets.created_at.desc()).all()

    results = []

    for t in tickets:

        rating = (
            db.query(models.TicketRatings)
            .filter(models.TicketRatings.ticket_id == t.ticket_id)
            .first()
        )

        # Skip jika belum ada rating
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
        "filter_month": month if month else "all",
        "filter_year": year if year else "all",
        "filter_source": source if source else "all",
        "data": results
    }


@router.get("/admin-opd/statistik/pelaporan-online/export")
def export_pelaporan_online_excel(
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None),
    source: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    # Akses admin dinas
    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin OPD yang dapat mengexport data."
        )

    opd_id_user = current_user.get("dinas_id")

    # Query utama
    query = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.opd_id_tickets == opd_id_user,
            models.Tickets.request_type == "pelaporan_online",
            models.Tickets.status == "selesai"
        )
    )

    if source in ["Masyarakat", "Pegawai"]:
        query = query.filter(models.Tickets.ticket_source == source)

    if year:
        query = query.filter(extract("year", models.Tickets.created_at) == year)

    if month:
        query = query.filter(extract("month", models.Tickets.created_at) == month)

    tickets = query.order_by(models.Tickets.created_at.desc()).all()

    # Mulai buat Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Pelaporan Online"

    # Header Excel (sesuai hasil return JSON)
    headers = [
        "ticket_id", "ticket_code", "title", "status", "priority",
        "lokasi_kejadian", "created_at", "ticket_source",

        # pengerjaan
        "pengerjaan_awal", "pengerjaan_akhir",
        "pengerjaan_awal_teknisi", "pengerjaan_akhir_teknisi",

        # rating
        "rating", "comment", "rated_at",

        # user
        "user_id", "full_name", "email", "profile",

        # asset
        "asset_id", "nama_asset", "kode_bmd", "nomor_seri", "kategori",
        "subkategori_id", "subkategori_nama", "jenis_asset", "lokasi_asset", "opd_id_asset",

        # list file akan digabung (dipisah koma)
        "files"
    ]

    ws.append(headers)

    # Isi data baris per baris
    for t in tickets:
        rating = (
            db.query(models.TicketRatings)
            .filter(models.TicketRatings.ticket_id == t.ticket_id)
            .first()
        )
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

            # user
            str(t.creates_id) if t.creates_id else None,
            t.creates_user.full_name if t.creates_user else None,
            t.creates_user.email if t.creates_user else None,
            t.creates_user.profile_url if t.creates_user else None,

            # asset
            t.asset_id,
            t.nama_asset,
            t.kode_bmd_asset,
            t.nomor_seri_asset,
            t.kategori_asset,
            t.subkategori_id_asset,
            t.subkategori_nama_asset,
            t.jenis_asset,
            t.lokasi_asset,
            t.opd_id_asset,

            file_list
        ]

        ws.append(row)

    # Simpan file
    filename = f"pelaporan_online_export_{uuid.uuid4()}.xlsx"
    filepath = os.path.join("exports", filename)

    os.makedirs("exports", exist_ok=True)
    wb.save(filepath)

    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename
    )




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
            models.Tickets.request_type == "pengajuan_pelayanan",
            models.Tickets.status == "selesai",
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

    
@router.get("/admin-opd/statistik/pengajuan-pelayanan/rekap")
def get_rekap_pengajuan_pelayanan_bulanan(
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    # Validasi role admin OPD
    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin OPD."
        )

    opd_id_user = current_user.get("dinas_id")

    # Default tahun sekarang
    if not year:
        year = datetime.now().year

    # Query group by bulan
    raw_result = (
        db.query(
            extract("month", models.Tickets.created_at).label("bulan"),
            func.count(models.Tickets.ticket_id).label("total")
        )
        .join(models.TicketServiceRequests,
              models.TicketServiceRequests.ticket_id == models.Tickets.ticket_id)
        .filter(
            models.Tickets.opd_id_tickets == opd_id_user,
            models.Tickets.request_type == "pengajuan_pelayanan",
            models.Tickets.status == "selesai",
            extract("year", models.Tickets.created_at) == year
        )
        .group_by(extract("month", models.Tickets.created_at))
        .all()
    )

    # Convert hasil query ke dict {bulan: total}
    hasil_map = {int(r.bulan): r.total for r in raw_result}

    # Build response bulan 1–12
    rekap = []
    for bulan in range(1, 13):
        rekap.append({
            "bulan": bulan,
            "total_tiket": hasil_map.get(bulan, None)  # None = null di JSON
        })

    return {
        "tahun": year,
        "opd_id": opd_id_user,
        "rekap": rekap
    }


@router.get("/admin-opd/statistik/pengajuan-pelayanan/subkategori")
def statistik_pengajuan_per_subkategori(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin OPD."
        )

    opd_id_user = current_user.get("dinas_id")

    # Ambil semua tiket selesai pengajuan_pelayanan milik OPD
    tickets = (
        db.query(models.Tickets)
        .join(models.TicketServiceRequests, models.TicketServiceRequests.ticket_id == models.Tickets.ticket_id)
        .filter(
            models.Tickets.opd_id_tickets == opd_id_user,
            models.Tickets.request_type == "pengajuan_pelayanan",
            models.Tickets.status == "selesai",
        )
        .all()
    )

    statistik = {}

    for t in tickets:
        sr = t.service_request[0] if t.service_request else None
        if not sr:
            continue

        key = (sr.subkategori_id, sr.subkategori_nama)

        if key not in statistik:
            statistik[key] = 0

        statistik[key] += 1

    result = [
        {
            "subkategori_id": sub_id,
            "subkategori_nama": sub_nama,
            "jumlah": count
        }
        for (sub_id, sub_nama), count in statistik.items()
    ]

    return {
        "total": len(tickets),
        "statistik_subkategori": result
    }


@router.get("/admin-opd/statistik/pengajuan-pelayanan/priority")
def statistik_pengajuan_per_priority(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin OPD."
        )

    opd_id_user = current_user.get("dinas_id")

    tickets = (
        db.query(models.Tickets)
        .join(models.TicketServiceRequests, models.TicketServiceRequests.ticket_id == models.Tickets.ticket_id)
        .filter(
            models.Tickets.opd_id_tickets == opd_id_user,
            models.Tickets.request_type == "pengajuan_pelayanan",
            models.Tickets.status == "selesai",
        )
        .all()
    )

    statistik = {}

    for t in tickets:
        key = t.priority or "unknown"

        if key not in statistik:
            statistik[key] = 0

        statistik[key] += 1

    result = [
        {
            "priority": priority,
            "jumlah": count
        }
        for priority, count in statistik.items()
    ]

    return {
        "total": len(tickets),
        "statistik_priority": result
    }

@router.get("/admin-opd/statistik/pengajuan-pelayanan/filter")
def get_statistik_pengajuan_pelayanan_filter(
    month: Optional[int] = Query(None, ge=1, le=12, description="Filter bulan (1-12)"),
    year: Optional[int] = Query(None, description="Filter tahun (YYYY)"),
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

    # Base Query
    query = (
        db.query(models.Tickets)
        .join(models.TicketServiceRequests, models.TicketServiceRequests.ticket_id == models.Tickets.ticket_id)
        .filter(
            models.Tickets.opd_id_tickets == opd_id_user,
            models.Tickets.request_type == "pengajuan_pelayanan",
            models.Tickets.status == "selesai"
        )
    )

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

    tickets = query.order_by(models.Tickets.created_at.desc()).all()

    results = []

    for t in tickets:

        # Ambil pengajuan pelayanan (form data)
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
        "data": results
    }

@router.get("/admin-opd/statistik/pengajuan-pelayanan/export")
def export_pengajuan_pelayanan_excel(
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin OPD."
        )

    opd_id_user = current_user.get("dinas_id")

    query = (
        db.query(models.Tickets)
        .join(models.TicketServiceRequests, models.TicketServiceRequests.ticket_id == models.Tickets.ticket_id)
        .filter(
            models.Tickets.opd_id_tickets == opd_id_user,
            models.Tickets.request_type == "pengajuan_pelayanan",
            models.Tickets.status == "selesai"
        )
    )

    if year:
        query = query.filter(extract("year", models.Tickets.created_at) == year)

    if month:
        query = query.filter(extract("month", models.Tickets.created_at) == month)

    tickets = query.order_by(models.Tickets.created_at.desc()).all()

    # ========================
    # Excel
    # ========================
    wb = Workbook()
    ws = wb.active
    ws.title = "Pengajuan Pelayanan"

    headers = [
        "ticket_id", "ticket_code", "title", "status", "priority",
        "created_at", "ticket_source", "request_type",

        "pengerjaan_awal", "pengerjaan_akhir",
        "pengerjaan_awal_teknisi", "pengerjaan_akhir_teknisi",

        # USER
        "user_id", "user_full_name", "user_email", "user_profile",

        # Form Pengajuan Pelayanan
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

    # ========================
    # Save as FILE (bukan BytesIO)
    # ========================
    os.makedirs("exports", exist_ok=True)
    filename = f"pengajuan_pelayanan_export_{uuid.uuid4()}.xlsx"
    filepath = os.path.join("exports", filename)

    wb.save(filepath)

    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename
    )



@router.get("/admin-opd/tickets/teknisi")
def get_all_teknisi_tickets_for_admin_opd(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya admin OPD yang dapat melihat tiket teknisi."
        )

    opd_id_user = current_user.get("dinas_id")

    if not opd_id_user:
        raise HTTPException(
            status_code=400,
            detail="Admin tidak memiliki OPD"
        )

    allowed_status = ["assigned to teknisi", "diproses"]

    tickets = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.opd_id_tickets == opd_id_user,
            models.Tickets.assigned_teknisi_id.isnot(None),
            models.Tickets.status.in_(allowed_status)
        )
        .order_by(models.Tickets.created_at.desc())
        .all()
    )

    result = []

    for t in tickets:
        teknisi_user = db.query(Users).filter(Users.id == t.assigned_teknisi_id).first()
        attachments = t.attachments if hasattr(t, "attachments") else []

        # ===== hitung status_sla =====
        status_sla = "sesuai sla"
        if t.pengerjaan_awal and t.pengerjaan_akhir:
            now = datetime.utcnow()
            total_duration = t.pengerjaan_akhir - t.pengerjaan_awal
            elapsed = now - t.pengerjaan_awal
            progress = elapsed / total_duration if total_duration.total_seconds() > 0 else 0

            if now > t.pengerjaan_akhir and t.status != "selesai":
                status_sla = "keterlambatan sla"
            elif progress >= 0.75 and t.status != "selesai":
                status_sla = "peringatan sla"

        result.append({
            "ticket_id": str(t.ticket_id),
            "ticket_code": t.ticket_code,
            "title": t.title,
            "description": t.description,
            "status": t.status,
            "priority": t.priority,
            "created_at": t.created_at,
            "ticket_source": t.ticket_source,
            "request_type": t.request_type,

            "pengerjaan_awal": t.pengerjaan_awal,
            "pengerjaan_akhir": t.pengerjaan_akhir,
            "pengerjaan_awal_teknisi": t.pengerjaan_awal_teknisi,
            "pengerjaan_akhir_teknisi": t.pengerjaan_akhir_teknisi,
            "status_sla": status_sla,  # tambahan field SLA

            "assigned_teknisi": {
                "id": teknisi_user.id if teknisi_user else None,
                "full_name": teknisi_user.full_name if teknisi_user else None,
                "email": teknisi_user.email if teknisi_user else None,
                "profile": teknisi_user.profile_url if teknisi_user else None
            },

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
