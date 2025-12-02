import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Response
from sqlalchemy.orm import Session
from datetime import datetime
from . import models, schemas
from auth.database import get_db
from auth.auth import get_current_user, get_user_by_email, get_current_user_masyarakat
from tickets import models, schemas
from tickets.models import Tickets, TicketAttachment, TicketCategories, TicketUpdates
from tickets.schemas import TicketCreateSchema, TicketResponseSchema, TicketCategorySchema, TicketForSeksiSchema, TicketTrackResponse, UpdatePriority, ManualPriority, RejectReasonSeksi, RejectReasonBidang
import uuid
from auth.models import Opd, Dinas, Roles
import os
from supabase import create_client, Client
from sqlalchemy import text
import mimetypes
from uuid import UUID, uuid4
from typing import Optional, List
import aiohttp, os, mimetypes, json


router = APIRouter(
    prefix="/seksi",
    tags=["seksi"],
    dependencies=[Depends(get_current_user)]
)
logger = logging.getLogger(__name__)


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

    allowed_status = [
        "Open",           
        "verified by seksi",   
        "rejected by bidang"   
    ]

    tickets = (
        db.query(models.Tickets)
        .filter(models.Tickets.opd_id_tickets == seksi_opd_id)
        .filter(models.Tickets.status.in_(allowed_status))
        .filter(models.Tickets.request_type == "pelaporan_online")  
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
                # "stage": t.ticket_stage,
                "priority": t.priority,
                "created_at": t.created_at,
                "ticket_source": t.ticket_source,
                "status_ticket_pengguna": t.status_ticket_pengguna,
                "status_ticket_seksi": t.status_ticket_seksi,
            

            #     "opd_id_tickets": t.opd_id_tickets,
            #     "lokasi_kejadian": t.lokasi_kejadian,

            #     "creator": {
            #         "user_id": str(t.creates_id) if t.creates_id else None,
            #         "full_name": t.creates_user.full_name if t.creates_user else None,
            #         "profile": t.creates_user.profile_url if t.creates_user else None,
            #         "email": t.creates_user.email if t.creates_user else None,
            #     },

            #     "asset": {
            #         "asset_id": t.asset_id,
            #         "nama_asset": t.nama_asset,
            #         "kode_bmd": t.kode_bmd_asset,
            #         "nomor_seri": t.nomor_seri_asset,
            #         "kategori": t.kategori_asset,
            #         "subkategori_id": t.subkategori_id_asset,
            #         "subkategori_nama": t.subkategori_nama_asset,
            #         "jenis_asset": t.jenis_asset,
            #         "lokasi_asset": t.lokasi_asset,
            #         "opd_id_asset": t.opd_id_asset,
            #     }
            }
            for t in tickets
        ]
    }



# DETAIL SEKSI
@router.get("/tickets/seksi/detail/{ticket_id}")
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

    allowed_status = [
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
    
    ticket.ticket_stage = "pending"
    ticket.status = "verified by seksi"
    ticket.status_ticket_seksi="pending"
    ticket.status_ticket_pengguna="proses verifikasi"
    ticket.verified_seksi_id=current_user.get("id")


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

    return {
        "message": "Prioritas tiket masyarakat berhasil ditetapkan",
        "ticket_id": ticket_id,
        "priority": ticket.priority
    }


@router.put("/tickets/{ticket_id}/reject")
def reject_ticket(
    ticket_id: str,
    payload: schemas.RejectReasonSeksi,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(
            403, "Akses ditolak: hanya seksi yang dapat menolak tiket"
        )

    ticket = db.query(models.Tickets).filter_by(ticket_id=ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Tiket tidak ditemukan")

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

    return {
        "message": "Tiket berhasil ditolak",
        "ticket_id": ticket_id,
        "status": ticket.status,
        "reason": ticket.rejection_reason_seksi
    }



@router.get("/tickets/seksi/verified-bidang")
def get_tickets_verified_by_bidang_for_seksi(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    if current_user.get("role_name") != "admin dinas":
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
            models.Tickets.status == "verified by bidang",
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
    current_user: dict = Depends(get_current_user)
):

    if current_user.get("role_name") != "admin dinas":
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
