import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Response
from sqlalchemy.orm import Session
from datetime import datetime
from . import models, schemas
from auth.database import get_db
from auth.auth import get_current_user, get_user_by_email, get_current_user_masyarakat, get_current_user_universal
from tickets import models, schemas
from tickets.models import Tickets, TicketAttachment, TicketCategories, TicketUpdates, TicketHistory
from tickets.schemas import TicketCreateSchema, TicketResponseSchema, TicketCategorySchema, TicketForSeksiSchema, TicketTrackResponse, UpdatePriority, ManualPriority, RejectReasonSeksi, RejectReasonBidang
import uuid
from auth.models import Opd, Dinas, Roles
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


@router.get("/tickets/bidang/verified")
def get_verified_tickets_for_bidang(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):

    if current_user.get("role_name") != "bidang":
        raise HTTPException(
            403,
            "Akses ditolak: hanya admin bidang yang dapat melihat tiket yang diverifikasi oleh seksi"
        )

    opd_id = current_user.get("dinas_id")
    if not opd_id:
        raise HTTPException(
            400,
            "Akun bidang tidak memiliki dinas_id, hubungi admin sistem."
        )

    tickets = (
        db.query(models.Tickets)
        .filter(
            models.Tickets.status == "verified by seksi",
            models.Tickets.priority.isnot(None),
            models.Tickets.opd_id_tickets == opd_id
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
        "message": "Daftar tiket yang sudah diverifikasi oleh seksi",
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
            models.Tickets.status == "verified by seksi"
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
        # Ambil kategori risiko
        async with session.get(EXTERNAL_API_URL, headers=headers) as resp:
            data = await resp.json()
            kategori_list = data.get("data", [])
            kategori = next((k for k in kategori_list if k["id"] == kategori_risiko_id), None)
            if not kategori:
                raise HTTPException(400, "Kategori risiko tidak valid")

        # Ambil area dampak
        async with session.get(EXTERNAL_API_AREA_DAMPAK, headers=headers) as resp:
            data = await resp.json()
            area_list = data.get("data", [])
            area = next((a for a in area_list if a["id"] == area_dampak_id), None)
            if not area:
                raise HTTPException(400, "Area dampak tidak valid")

    # Update tiket
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

    return {"message": "Tiket berhasil diverifikasi oleh bidang dan info tambahan disimpan"}



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
            models.Tickets.status == "verified by seksi"
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







