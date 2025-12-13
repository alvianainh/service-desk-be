import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Response
from sqlalchemy.orm import Session
from datetime import datetime
from . import models, schemas
from auth.database import get_db
from auth.auth import get_current_user, get_user_by_email, get_current_user_masyarakat, get_current_user_universal
from tickets import models, schemas
from tickets.models import Tickets, TicketAttachment, TicketCategories, TicketUpdates, TicketHistory, TicketServiceRequests, Notifications
from tickets.schemas import TicketCreateSchema, TicketResponseSchema, TicketCategorySchema, TicketForSeksiSchema, TicketTrackResponse, UpdatePriority, ManualPriority, RejectReasonSeksi, RejectReasonBidang
import uuid
from auth.models import Opd, Dinas, Roles, Users
import os
from supabase import create_client, Client
from sqlalchemy import text, func
import mimetypes
from uuid import UUID, uuid4
from typing import Optional, List
import aiohttp, os, mimetypes, json
from dotenv import load_dotenv


router = APIRouter()
logger = logging.getLogger(__name__)

load_dotenv()

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



EXTERNAL_API_URL = os.environ.get("EXTERNAL_API_KATEGORI_RISIKO")
EXTERNAL_API_AREA_DAMPAK = os.environ.get("EXTERNAL_API_AREA_DAMPAK")
EXTERNAL_API_UNIT_KERJA = os.environ.get("EXTERNAL_API_UNIT_KERJA")


@router.get("/kategori-risiko")
async def get_kategori_risiko(current_user: dict = Depends(get_current_user_universal)):
    token = current_user.get("access_token")

    if not token:
        raise HTTPException(status_code=401, detail="Token user tidak tersedia")

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {token}",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(EXTERNAL_API_URL, headers=headers) as resp:
                if resp.status >= 400:
                    detail = await resp.text()
                    raise HTTPException(status_code=resp.status, detail=detail)

                data = await resp.json()
                return data 

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/area-dampak")
async def get_area_dampak(current_user: dict = Depends(get_current_user_universal)):
    token = current_user.get("access_token")

    if not token:
        raise HTTPException(status_code=401, detail="Token user tidak tersedia")

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {token}",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(EXTERNAL_API_AREA_DAMPAK, headers=headers) as resp:
                if resp.status >= 400:
                    detail = await resp.text()
                    raise HTTPException(status_code=resp.status, detail=detail)

                data = await resp.json()
                return data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/notifications/bidang")
def get_bidang_notifications(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "bidang":
        raise HTTPException(403, "Akses ditolak: hanya bidang yang dapat melihat notifikasi ini")

    try:
        user_uuid = UUID(current_user["id"])
    except ValueError:
        raise HTTPException(400, "User ID tidak valid")

    opd_id = current_user.get("dinas_id")

    # Query notifikasi yang terkait tiket verified by seksi
    notifications = (
        db.query(Notifications)
        .join(Tickets, Notifications.ticket_id == Tickets.ticket_id)
        .filter(
            Notifications.user_id == user_uuid,
            Tickets.status == "verified by seksi",
            Tickets.opd_id_tickets == opd_id
        )
        .order_by(Notifications.created_at.desc())
        .all()
    )

    result = []
    for notif in notifications:
        ticket = db.query(Tickets).filter(Tickets.ticket_id == notif.ticket_id).first()
        result.append({
            "notification_id": str(notif.id),
            "ticket_id": str(notif.ticket_id) if notif.ticket_id else None,
            "ticket_code": ticket.ticket_code if ticket else None,
            "message": notif.message,
            "status": notif.status,
            "is_read": notif.is_read,
            "created_at": notif.created_at.replace(tzinfo=timezone.utc) if notif.created_at else None
        })

    return {
        "total_notifications": len(result),
        "notifications": result
    }

@router.get("/notifications/bidang/{notification_id}")
def get_bidang_notification_by_id(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "bidang":
        raise HTTPException(403, "Akses ditolak: hanya bidang yang dapat melihat notifikasi ini")

    try:
        notif_uuid = UUID(notification_id)
        user_uuid = UUID(current_user["id"])
    except ValueError:
        raise HTTPException(400, "ID tidak valid")

    opd_id = current_user.get("dinas_id")

    # Ambil notif berdasarkan ID, user, dan tiket yang verified by seksi & sesuai opd
    notif = (
        db.query(Notifications)
        .join(Tickets, Notifications.ticket_id == Tickets.ticket_id)
        .filter(
            Notifications.id == notif_uuid,
            Notifications.user_id == user_uuid,
            Tickets.status == "verified by seksi",
            Tickets.opd_id_tickets == opd_id
        )
        .first()
    )

    if not notif:
        raise HTTPException(404, "Notifikasi tidak ditemukan atau tidak milik Anda")

    ticket = db.query(Tickets).filter(Tickets.ticket_id == notif.ticket_id).first()

    result = {
        "notification_id": str(notif.id),
        "ticket_id": str(notif.ticket_id) if notif.ticket_id else None,
        "ticket_code": ticket.ticket_code if ticket else None,
        "message": notif.message,
        "status": notif.status,
        "is_read": notif.is_read,
        "created_at": notif.created_at.replace(tzinfo=timezone.utc) if notif.created_at else None
    }

    return {"status": "success", "data": result}

@router.patch("/notifications/bidang/{notification_id}/read")
def mark_bidang_notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "bidang":
        raise HTTPException(403, "Hanya bidang yang bisa mengubah notifikasi")

    notif = db.query(models.Notifications).filter(
        models.Notifications.id == notification_id,
        models.Notifications.user_id == current_user["id"]
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

@router.patch("/notifications/bidang/read-all")
def mark_all_bidang_notifications_read(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "bidang":
        raise HTTPException(403, "Hanya bidang yang bisa mengubah notifikasi")

    # Ambil semua notif yang belum dibaca
    notifs = db.query(models.Notifications).join(
        models.Tickets, models.Notifications.ticket_id == models.Tickets.ticket_id
    ).filter(
        models.Notifications.user_id == current_user["id"],
        models.Notifications.is_read == False,
        models.Tickets.status == "verified by seksi",
        models.Tickets.opd_id_tickets == current_user["dinas_id"]
    ).all()

    if not notifs:
        return {"message": "Tidak ada notifikasi baru untuk ditandai sudah dibaca"}

    for notif in notifs:
        notif.is_read = True

    db.commit()

    return {
        "message": f"{len(notifs)} notifikasi berhasil ditandai sudah dibaca"
    }

@router.delete("/notifications/bidang/{notification_id}")
def delete_bidang_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "bidang":
        raise HTTPException(403, "Hanya bidang yang bisa menghapus notifikasi")

    notif = db.query(models.Notifications).join(
        models.Tickets, models.Notifications.ticket_id == models.Tickets.ticket_id
    ).filter(
        models.Notifications.id == notification_id,
        models.Notifications.user_id == current_user["id"],
        models.Tickets.status == "verified by seksi",
        models.Tickets.opd_id_tickets == current_user["dinas_id"]
    ).first()

    if not notif:
        raise HTTPException(404, "Notifikasi tidak ditemukan")

    db.delete(notif)
    db.commit()

    return {
        "message": "Notifikasi berhasil dihapus",
        "notification_id": str(notification_id)
    }



@router.get("/dashboard/bidang")
def get_dashboard_bidang(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "bidang":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya bidang yang dapat mengakses dashboard ini"
        )

    bidang_opd_id = current_user.get("dinas_id")
    if not bidang_opd_id:
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
        models.Tickets.opd_id_tickets == bidang_opd_id,
        models.Tickets.status == "verified by seksi",
        models.Tickets.request_type == "pelaporan_online"
    ).scalar()

    verified_tickets = db.query(func.count(models.Tickets.ticket_id)).filter(
        models.Tickets.opd_id_tickets == bidang_opd_id,
        models.Tickets.status == "verified by bidang",
        models.Tickets.request_type == "pelaporan_online"
    ).scalar()

    revisi_tickets = db.query(func.count(models.Tickets.ticket_id)).filter(
        models.Tickets.opd_id_tickets == bidang_opd_id,
        models.Tickets.status == "rejected by bidang",
        models.Tickets.request_type == "pelaporan_online"
    ).scalar()

    rejected_tickets = db.query(func.count(models.Tickets.ticket_id)).filter(
        models.Tickets.opd_id_tickets == bidang_opd_id,
        models.Tickets.status == "rejected",
        models.Tickets.request_type == "pelaporan_online"
    ).scalar()

    return {
        "total_tickets": total_tickets,
        "verified_tickets": verified_tickets,
        "revisi_tickets": revisi_tickets,
        "rejected_tickets": rejected_tickets
    }


@router.get("/tickets/bidang/verified/pelaporan-online")
def get_verified_pelaporan_online_for_bidang(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "bidang":
        raise HTTPException(
            403,
            "Akses ditolak: hanya bidang yang dapat melihat tiket ini"
        )

    opd_id = current_user.get("dinas_id")
    if not opd_id:
        raise HTTPException(400, "Akun bidang tidak memiliki dinas_id")

    tickets = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.status == "verified by seksi",
            models.Tickets.priority.isnot(None),
            models.Tickets.opd_id_tickets == opd_id,
            models.Tickets.request_type == "pelaporan_online"
        )
        .order_by(models.Tickets.created_at.desc())
        .all()
    )

    results = []
    for ticket in tickets:
        attachments = ticket.attachments if hasattr(ticket, "attachments") else []

        results.append({
            "ticket_id": str(ticket.ticket_id),
            "ticket_code": ticket.ticket_code,
            "title": ticket.title,
            "status": ticket.status,
            "created_at": ticket.created_at,
            "updated_at": ticket.updated_at,
            "priority": ticket.priority,
            "opd_id_tickets": ticket.opd_id_tickets,
            "ticket_source": ticket.ticket_source,
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
        "message": "Daftar tiket pelaporan online yang diverifikasi seksi",
        "total": len(results),
        "data": results
    }


@router.get("/tickets/bidang/verified/pengajuan-pelayanan")
def get_verified_pengajuan_pelayanan_for_bidang(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "bidang":
        raise HTTPException(
            403,
            "Akses ditolak: hanya bidang yang dapat melihat tiket ini"
        )

    opd_id = current_user.get("dinas_id")
    if not opd_id:
        raise HTTPException(400, "Akun bidang tidak memiliki dinas_id")

    tickets = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.status == "verified by seksi",
            models.Tickets.priority.isnot(None),
            models.Tickets.opd_id_tickets == opd_id,
            models.Tickets.request_type == "pengajuan_pelayanan"
        )
        .order_by(models.Tickets.created_at.desc())
        .all()
    )

    results = []
    for ticket in tickets:
        attachments = ticket.attachments if hasattr(ticket, "attachments") else []

        results.append({
            "ticket_id": str(ticket.ticket_id),
            "ticket_code": ticket.ticket_code,
            "title": ticket.title,
            "status": ticket.status,
            "lokasi_penempatan": ticket.lokasi_penempatan,
            "subkategori_nama": ticket.subkategori_nama_asset,
            "created_at": ticket.created_at,
            "updated_at": ticket.updated_at,
            "priority": ticket.priority,
            "opd_id_tickets": ticket.opd_id_tickets,
            "ticket_source": ticket.ticket_source,
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
        "message": "Daftar tiket pengajuan pelayanan yang diverifikasi seksi",
        "total": len(results),
        "data": results
    }




@router.get("/tickets/bidang/{ticket_id}")
def get_ticket_detail_bidang(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "bidang":
        raise HTTPException(
            403,
            "Akses ditolak: hanya admin bidang"
        )

    opd_id = current_user.get("dinas_id")
    if not opd_id:
        raise HTTPException(
            400,
            "Akun bidang tidak memiliki OPD ID"
        )

    ticket = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.ticket_id == ticket_id,
            models.Tickets.opd_id_tickets == opd_id,
            models.Tickets.status == "verified by seksi"
        )
        .first()
    )


    if not ticket:
        raise HTTPException(404, "Tiket tidak ditemukan, belum diverifikasi seksi atau bukan dari OPD Anda")

    attachments = (
        db.query(models.TicketAttachment)
        .filter(models.TicketAttachment.has_id == ticket_id)
        .all()
    )

    response = {
        "ticket_id": str(ticket.ticket_id),
        "ticket_code": ticket.ticket_code,
        "title": ticket.title,
        "description": ticket.description,
        "status": ticket.status,
        # "stage": ticket.ticket_stage,
        "created_at": ticket.created_at,
        "priority": ticket.priority,
        "lokasi_penempatan": ticket.lokasi_penempatan,
        "subkategori_nama": ticket.subkategori_nama_asset,

        "opd_id_tickets": ticket.opd_id_tickets,
        "lokasi_kejadian": ticket.lokasi_kejadian,
        "expected_resolution": ticket.expected_resolution,
        "ticket_source": ticket.ticket_source,
        "status_ticket_pengguna": ticket.status_ticket_pengguna,
        "status_ticket_seksi": ticket.status_ticket_seksi,
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

    return {
        "message": "Detail tiket untuk bidang",
        "data": response
    }


@router.patch("/tickets/bidang/verify/{ticket_id}")
async def verify_and_update_ticket_by_bidang(
    ticket_id: str,
    kategori_risiko_id: int = Form(...),
    area_dampak_id: int = Form(...),
    deskripsi_pengendalian: str = Form(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "bidang":
        raise HTTPException(403, "Akses ditolak: hanya admin bidang")

    opd_id = current_user.get("dinas_id")
    bidang_id = current_user.get("id")

    ticket = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.ticket_id == ticket_id,
            models.Tickets.opd_id_tickets == opd_id,
            models.Tickets.status == "verified by seksi",
            models.Tickets.request_type == "pelaporan_online",
            models.Tickets.ticket_source == "Pegawai",
        )
        .first()
    )

    if not ticket:
        raise HTTPException(404, "Tiket tidak valid untuk diverifikasi bidang")

    token = current_user.get("access_token")
    if not token:
        raise HTTPException(401, "Token user tidak tersedia")

    headers = {"accept": "application/json", "Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession() as session:
        async with session.get(EXTERNAL_API_URL, headers=headers) as resp:
            data = await resp.json()
            kategori_list = data.get("data", [])
            kategori = next((k for k in kategori_list if k["id"] == kategori_risiko_id), None)
            if not kategori:
                raise HTTPException(400, "Kategori risiko tidak valid")

        async with session.get(EXTERNAL_API_AREA_DAMPAK, headers=headers) as resp:
            data = await resp.json()
            area_list = data.get("data", [])
            area = next((a for a in area_list if a["id"] == area_dampak_id), None)
            if not area:
                raise HTTPException(400, "Area dampak tidak valid")

    ticket.status = "verified by bidang"
    ticket.ticket_stage = "verified-bidang"
    ticket.verified_bidang_id = bidang_id
    ticket.status_ticket_seksi = "Draft"
    ticket.updated_at = datetime.utcnow()

    ticket.kategori_risiko_id_asset = kategori["id"]
    ticket.kategori_risiko_nama_asset = kategori["nama"]
    ticket.kategori_risiko_selera_positif = kategori.get("selera_positif")
    ticket.kategori_risiko_selera_negatif = kategori.get("selera_negatif")

    ticket.area_dampak_id_asset = area["id"]
    ticket.area_dampak_nama_asset = area["nama"]

    ticket.deskripsi_pengendalian_bidang = deskripsi_pengendalian

    db.commit()

    add_ticket_history(
        db=db,
        ticket=ticket,
        old_status="verified by seksi",
        new_status=ticket.status,
        updated_by=UUID(current_user["id"]),
        extra={"notes": "Tiket diverifikasi dan bidang mengisi info tambahan"}
    )

    seksi_users = (
        db.query(Users)
        .join(Roles)
        .filter(Roles.role_name == "seksi", Users.opd_id == opd_id)
        .all()
    )

    for seksi in seksi_users:
        db.add(models.Notifications(
            user_id=seksi.id,
            ticket_id=ticket.ticket_id,
            message=f"Tiket {ticket.ticket_code} telah diverifikasi bidang dan siap diproses",
            status="Tiket Diverifikasi Bidang",
            is_read=False,
            created_at=datetime.utcnow()
        ))

    db.commit()

    return {"message": "Tiket berhasil diverifikasi oleh bidang dan info tambahan disimpan"}


@router.patch("/tickets/bidang/verify/masyarakat/{ticket_id}")
async def verify_ticket_masyarakat_by_bidang(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "bidang":
        raise HTTPException(403, "Akses ditolak: hanya admin bidang")

    opd_id = current_user.get("dinas_id")
    bidang_id = current_user.get("id")


    ticket = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.ticket_id == ticket_id,
            models.Tickets.opd_id_tickets == opd_id,
            models.Tickets.status == "verified by seksi",
            models.Tickets.request_type == "pelaporan_online",
            models.Tickets.ticket_source == "Masyarakat",
        )
        .first()
    )

    if not ticket:
        raise HTTPException(404, "Tiket tidak valid untuk diverifikasi bidang")

    old_status = ticket.status

    ticket.status = "verified by bidang"
    ticket.ticket_stage = "verified-bidang"
    ticket.verified_bidang_id = bidang_id
    ticket.status_ticket_seksi = "Draft"
    ticket.updated_at = datetime.utcnow()

    db.commit()


    add_ticket_history(
        db=db,
        ticket=ticket,
        old_status=old_status,
        new_status=ticket.status,
        updated_by=UUID(current_user["id"]),
        extra={"notes": "Tiket masyarakat diverifikasi langsung oleh bidang"}
    )

    # notif ke seksi
    seksi_users = (
        db.query(Users)
        .join(Roles)
        .filter(Roles.role_name == "seksi", Users.opd_id == opd_id)
        .all()
    )

    for seksi in seksi_users:
        db.add(models.Notifications(
            user_id=seksi.id,
            ticket_id=ticket.ticket_id,
            message=f"Tiket {ticket.ticket_code} sudah diverifikasi bidang dan siap diproses",
            status="Tiket Diverifikasi Bidang",
            is_read=False,
            created_at=datetime.utcnow()
        ))

    db.commit()


    return {"message": "Tiket masyarakat berhasil diverifikasi oleh bidang"}


@router.patch("/tickets/bidang/verify-pengajuan-pelayanan/{ticket_id}")
async def verify_ticket_by_bidang_simple(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "bidang":
        raise HTTPException(403, "Akses ditolak: hanya bidang")

    opd_id = current_user.get("dinas_id")
    bidang_id = current_user.get("id")

    # Filter tiket hanya untuk request_type = pengajuan_pelayanan dan status tertentu
    ticket = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.ticket_id == ticket_id,
            models.Tickets.opd_id_tickets == opd_id,
            models.Tickets.request_type == "pengajuan_pelayanan",
            models.Tickets.status == "pengajuan by bidang"  # filter status
        )
        .first()
    )

    if not ticket:
        raise HTTPException(404, "Tiket tidak valid atau tidak bisa diverifikasi bidang")

    # Update status
    old_status = ticket.status
    ticket.status = "verified by bidang"
    ticket.ticket_stage = "verified-bidang"
    ticket.verified_bidang_id = bidang_id
    ticket.updated_at = datetime.utcnow()

    db.commit()

    # Catat history
    add_ticket_history(
        db=db,
        ticket=ticket,
        old_status=old_status,
        new_status=ticket.status,
        updated_by=UUID(current_user["id"]),
        extra={"notes": "Tiket diverifikasi bidang"}
    )
    seksi_users = (
        db.query(Users)
        .join(Roles)
        .filter(Roles.role_name == "seksi", Users.opd_id == opd_id)
        .all()
    )

    for seksi in seksi_users:
        db.add(models.Notifications(
            user_id=seksi.id,
            ticket_id=ticket.ticket_id,
            message=f"Tiket {ticket.ticket_code} pengajuan pelayanan telah diverifikasi bidang dan siap diproses",
            status="Tiket Diverifikasi Bidang",
            is_read=False,
            created_at=datetime.utcnow()
        ))

    db.commit()

    return {"message": "Tiket berhasil diverifikasi oleh bidang", "status": ticket.status}

@router.post("/tickets/bidang/create-asset/{ticket_id}")
async def create_asset_and_save(
    ticket_id: str,
    unit_kerja_id: int = Form(...),
    lokasi_id: int = Form(...),
    nama_aset: str = Form(...),
    kategori_aset: str = Form(...), 
    sub_kategori_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "bidang":
        raise HTTPException(403, "Akses ditolak: hanya admin bidang")

    opd_id = current_user.get("dinas_id")

    ticket = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.ticket_id == ticket_id,
            models.Tickets.opd_id_tickets == opd_id,
            models.Tickets.request_type == "pengajuan_pelayanan"
        )
        .first()
    )
    if not ticket:
        raise HTTPException(404, "Tiket tidak ditemukan")

    token = current_user.get("access_token")
    if not token:
        raise HTTPException(401, "Token user tidak tersedia")

    # ======== Ambil unit kerja dan sub kategori dari backend aset ========
    headers = {"accept": "application/json", "Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession() as session:

        # Unit Kerja
        async with session.get("https://arise-app.my.id/api/unit-kerja", headers=headers) as resp:
            uk_data = (await resp.json()).get("data", [])
            allowed_uk = [u for u in uk_data if str(u["dinas_id"]) == str(opd_id)]
            selected_uk = next((u for u in allowed_uk if u["id"] == unit_kerja_id), None)
            if not selected_uk:
                raise HTTPException(400, "Unit kerja tidak valid untuk dinas ini")

        # Sub Kategori
        async with session.get("https://arise-app.my.id/api/sub-kategori", headers=headers) as resp:
            sub_data = (await resp.json()).get("data", [])
            selected_sub = next((s for s in sub_data if s["id"] == sub_kategori_id), None)
            if not selected_sub:
                raise HTTPException(400, "Sub-kategori aset tidak valid")

        form_data = aiohttp.FormData()
        form_data.add_field("unit_kerja_id", str(unit_kerja_id))
        form_data.add_field("kategori", kategori_aset)
        form_data.add_field("lokasi_id", str(lokasi_id))
        form_data.add_field("sub_kategori_id", str(sub_kategori_id))
        form_data.add_field("nama_asset", nama_aset)

        async with session.post(
            "https://arise-app.my.id/api/asset-barang",
            headers={"Authorization": f"Bearer {token}"},
            data=form_data
        ) as post_res:

            if post_res.status != 200 and post_res.status != 201:
                text = await post_res.text()
                raise HTTPException(post_res.status, f"Error posting asset: {text[:200]}")

            asset_resp = await post_res.json()
            asset_id = asset_resp.get("data", {}).get("id")
            if not asset_id:
                raise HTTPException(500, "ID asset tidak diterima dari backend aset")

    service_req = (
        db.query(models.TicketServiceRequests)
        .filter(models.TicketServiceRequests.ticket_id == ticket_id)
        .first()
    )
    if not service_req:
        raise HTTPException(404, "Data pengajuan pelayanan tidak ditemukan")

    service_req.unit_kerja_id = selected_uk["id"]
    service_req.lokasi_id = lokasi_id
    service_req.nama_aset_baru = nama_aset
    service_req.kategori_aset = kategori_aset
    service_req.subkategori_id = sub_kategori_id
    service_req.subkategori_nama = selected_sub["nama"]
    service_req.unit_kerja_nama = selected_uk["nama"]
    service_req.id_asset = str(asset_id)
    service_req.updated_at = datetime.utcnow()

    ticket.status = "pengajuan by bidang"
    ticket.updated_at = datetime.utcnow()

    db.commit()

    return {
        "message": "Asset berhasil dibuat dan tersimpan",
        "ticket_service_request_id": service_req.id,
        "id_asset": asset_id
    }

@router.get("/tickets/pengajuan-pelayanan/bidang")
async def get_all_pengajuan_asset(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "bidang":
        raise HTTPException(403, "Akses ditolak: hanya admin bidang")

    token = current_user.get("access_token")
    if not token:
        raise HTTPException(401, "Token user tidak tersedia")

    # Ambil semua ticket service request yang sudah ada id_asset tapi belum diverifikasi bidang
    service_requests = (
        db.query(models.TicketServiceRequests)
        .join(models.Tickets, models.Tickets.ticket_id == models.TicketServiceRequests.ticket_id)
        .filter(
            models.Tickets.status == "pengajuan by bidang",
            models.TicketServiceRequests.id_asset.isnot(None),
            models.Tickets.opd_id_tickets == current_user.get("dinas_id")  # optional filter
        )
        .all()
    )

    results = []
    headers = {"accept": "application/json", "Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession() as session:
        for sr in service_requests:
            ticket = sr.ticket

            # Ambil detail asset dari backend aset
            async with session.get(f"https://arise-app.my.id/api/asset-barang/{sr.id_asset}", headers=headers) as resp:
                if resp.status != 200:
                    asset_data = {"error": f"Gagal ambil asset {sr.id_asset}"}
                else:
                    asset_data = (await resp.json()).get("data", {})

            # Ambil attachments jika ada
            attachments = getattr(ticket, "attachments", [])

            results.append({
                "ticket_id": str(ticket.ticket_id),
                "ticket_code": ticket.ticket_code if hasattr(ticket, "ticket_code") else None,
                "nama_asset": sr.nama_aset_baru,
                "status_ticket_bidang": ticket.status,
                "asset": asset_data,
                "creator": {
                    "user_id": str(ticket.creates_id) if ticket.creates_id else None,
                    "full_name": ticket.creates_user.full_name if ticket.creates_user else None,
                    "profile": ticket.creates_user.profile_url if ticket.creates_user else None,
                    "email": ticket.creates_user.email if ticket.creates_user else None,
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

    return {"message": "Daftar pengajuan asset", "data": results}



@router.get("/tickets/bidang/asset-status/{ticket_id}")
async def get_asset_status(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    # cek role
    if current_user.get("role_name") != "bidang":
        raise HTTPException(403, "Akses ditolak: hanya admin bidang")

    try:
        ticket_uuid = UUID(ticket_id)
    except ValueError:
        raise HTTPException(400, "ticket_id harus UUID valid")

    service_req = (
        db.query(models.TicketServiceRequests)
        .filter(models.TicketServiceRequests.ticket_id == ticket_uuid)
        .first()
    )

    if not service_req or not service_req.id_asset:
        raise HTTPException(404, "ID asset tidak ditemukan untuk tiket ini")

    asset_id = service_req.id_asset
    token = current_user.get("access_token")
    if not token:
        raise HTTPException(401, "Token user tidak tersedia")

    # request ke backend aset
    headers = {"accept": "application/json", "Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://arise-app.my.id/api/asset-barang/{asset_id}", headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise HTTPException(resp.status, f"Gagal ambil status asset: {text[:200]}")
            asset_data = await resp.json()

    return asset_data


# @router.patch("/tickets/bidang/verify-pengajuan/{ticket_id}")
# async def verify_pengajuan_pelayanan_by_bidang(
#     ticket_id: str,
#     unit_kerja_id: int = Form(...),
#     lokasi_id: int = Form(...),
#     nama_aset: str = Form(...),
#     kategori_aset: str = Form(...), 
#     sub_kategori_id: int = Form(...),

#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_universal)
# ):

#     if current_user.get("role_name") != "bidang":
#         raise HTTPException(403, "Akses ditolak: hanya admin bidang")

#     opd_id = current_user.get("dinas_id")
#     bidang_id = current_user.get("id")

#     ticket = (
#         db.query(models.Tickets)
#         .filter(
#             models.Tickets.ticket_id == ticket_id,
#             models.Tickets.opd_id_tickets == opd_id,
#             models.Tickets.status == "verified by seksi",
#             models.Tickets.request_type == "pengajuan_pelayanan"
#         )
#         .first()
#     )

#     if not ticket:
#         raise HTTPException(404, "Tiket tidak valid untuk diverifikasi bidang")

#     token = current_user.get("access_token")
#     if not token:
#         raise HTTPException(401, "Token user tidak tersedia")

#     headers = {"accept": "application/json", "Authorization": f"Bearer {token}"}

#     async with aiohttp.ClientSession() as session:

#         async with session.get("https://arise-app.my.id/api/unit-kerja", headers=headers) as resp:
#             uk_data = (await resp.json()).get("data", [])
#             allowed_uk = [u for u in uk_data if str(u["dinas_id"]) == str(opd_id)]
#             selected_uk = next((u for u in allowed_uk if u["id"] == unit_kerja_id), None)

#             if not selected_uk:
#                 raise HTTPException(400, "Unit kerja tidak valid untuk dinas ini")

#         # async with session.get("https://arise-app.my.id/api/lokasi", headers=headers) as resp:
#         #     lokasi_data = (await resp.json()).get("data", [])
#         #     selected_lokasi = next((l for l in lokasi_data if l["id"] == lokasi_id), None)

#         #     if not selected_lokasi:
#         #         raise HTTPException(400, "Lokasi tidak valid")

#         async with session.get("https://arise-app.my.id/api/sub-kategori", headers=headers) as resp:
#             sub_data = (await resp.json()).get("data", [])
#             selected_sub = next((s for s in sub_data if s["id"] == sub_kategori_id), None)

#             if not selected_sub:
#                 raise HTTPException(400, "Sub-kategori aset tidak valid")

#     #selected lokasi temp
#     selected_lokasi = {
#         "id": lokasi_id,
#         "nama": f"Lokasi-{lokasi_id}"  
#     }

#     service_req = (
#         db.query(models.TicketServiceRequests)
#         .filter(models.TicketServiceRequests.ticket_id == ticket_id)
#         .first()
#     )

#     if not service_req:
#         raise HTTPException(404, "Data pengajuan pelayanan tidak ditemukan")

#     service_req.unit_kerja_id = selected_uk["id"]
#     service_req.lokasi_id = selected_lokasi["id"]
#     service_req.nama_aset_baru = nama_aset
#     service_req.kategori_aset = kategori_aset
#     service_req.subkategori_id = selected_sub["id"]
#     service_req.updated_at = datetime.utcnow()
#     service_req.subkategori_nama = selected_sub["nama"]
#     service_req.unit_kerja_nama = selected_uk["nama"]


#     ticket.status = "verified by bidang"
#     ticket.ticket_stage = "verified-bidang"
#     ticket.verified_bidang_id = bidang_id
#     ticket.status_ticket_seksi = "Draft"
#     ticket.updated_at = datetime.utcnow()

#     db.commit()

#     add_ticket_history(
#         db=db,
#         ticket=ticket,
#         old_status="verified by seksi",
#         new_status="verified by bidang",
#         updated_by=UUID(current_user["id"]),
#         extra={"notes": "Pengajuan pelayanan diverifikasi bidang"}
#     )

#     return {"message": "Pengajuan pelayanan berhasil diverifikasi oleh bidang"}




@router.patch("/tickets/bidang/reject/{ticket_id}")
def reject_by_bidang(
    ticket_id: str,
    payload: RejectReasonBidang,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "bidang":
        raise HTTPException(403, "Akses ditolak: hanya admin bidang")

    opd_id = current_user.get("dinas_id")

    ticket = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.ticket_id == ticket_id,
            models.Tickets.opd_id_tickets == opd_id,
            models.Tickets.status.in_(["verified by seksi", "pengajuan by bidang"])
        )
        .first()
    )

    if not ticket:
        raise HTTPException(404, "Tiket tidak valid untuk direject bidang")


    old_status = ticket.status

    ticket.status = "rejected by bidang"
    ticket.ticket_stage = "revisi-seksi"
    ticket.status_ticket_seksi = "revisi"
    ticket.rejection_reason_bidang = payload.reason
    ticket.updated_at = datetime.utcnow()

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

    # ==== notif ke seksi ====
    seksi_users = (
        db.query(Users)
        .join(Roles)
        .filter(Roles.role_name == "seksi", Users.opd_id == opd_id)
        .all()
    )

    for seksi in seksi_users:
        db.add(models.Notifications(
            user_id=seksi.id,
            ticket_id=ticket.ticket_id,
            message=f"Tiket {ticket.ticket_code} direvisi oleh bidang: {payload.reason}",
            status="Tiket Direvisi Bidang",
            is_read=False,
            created_at=datetime.utcnow()
        ))

    db.commit()

    return {"message": "Tiket berhasil ditolak oleh bidang", "reason": payload.reason}


@router.get("/bidang/ratings")
def get_ratings_for_bidang(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "bidang":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya bidang yang dapat melihat data rating."
        )

    bidang_id = current_user.get("id")
    opd_id_user = current_user.get("dinas_id")

    tickets = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.verified_bidang_id == bidang_id,
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


@router.get("/bidang/ratings/{ticket_id}")
def get_rating_detail_for_bidang(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "bidang":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: hanya bidang yang dapat melihat data rating."
        )

    bidang_id = current_user.get("id")
    opd_id_user = current_user.get("dinas_id")

    ticket = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.ticket_id == ticket_id,
            models.Tickets.verified_bidang_id == bidang_id,
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


@router.get("/tickets/bidang/all/assigned")
def get_assigned_tickets_for_seksi(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "bidang":
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


@router.get("/tickets/bidang/assigned-teknisi/{teknisi_id}")
def get_assigned_tickets_by_teknisi(
    teknisi_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    if current_user.get("role_name") != "bidang":
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


@router.get("/tickets/bidang/assigned/teknisi/{ticket_id}")
def get_ticket_detail_assigned_to_teknisi_for_seksi(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "bidang":
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
        "request_type": ticket.request_type,

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







