import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Response, Query
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
from dotenv import load_dotenv




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

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET_NAME = "docs"
PRIORITY_OPTIONS = ["Low", "Medium", "High", "Critical"]

EXTERNAL_API_URL = os.environ.get("EXTERNAL_API_KATEGORI_RISIKO")
EXTERNAL_API_AREA_DAMPAK = os.environ.get("EXTERNAL_API_AREA_DAMPAK")
EXTERNAL_API_UNIT_KERJA = os.environ.get("EXTERNAL_API_UNIT_KERJA")


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

async def fetch_subkategori_name(subkategori_id: int) -> str:
    url = f"https://arise-app.my.id/api/sub-kategori"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as res:
            if res.status != 200:
                text = await res.text()
                raise HTTPException(status_code=res.status, detail=f"Error API SUB-KATEGORI: {text}")
            data = await res.json()
            for s in data.get("data", []):
                if s["id"] == subkategori_id:
                    return s["nama"]
    return ""


@router.get("/public/opd")
def get_all_opd_with_stats(db: Session = Depends(get_db)):

    # Total OPD
    total_opd = db.query(Dinas).count()

    # Total pelaporan
    total_pelaporan = db.query(Tickets).count()

    # Rating
    total_rating_value = db.query(func.sum(TicketRatings.rating)).scalar() or 0
    rating_count = db.query(func.count(TicketRatings.rating_id)).scalar() or 0


    # Hitung presentase rating (skala 1–5 ke 0–100%)
    presentase_rating = (
        (total_rating_value / (rating_count * 5)) * 100
        if rating_count > 0 else 0
    )

    return {
        "status": "success",
        "message": "Statistik OPD berhasil diambil",
        "data": {
            "total_opd": total_opd,
            "total_pelaporan": total_pelaporan,
            "total_rating_value": total_rating_value,
            "rating_count": rating_count,
            "presentase_rating": round(presentase_rating, 2)
        }
    }


@router.get("/unit-kerja")
async def get_unit_kerja(current_user: dict = Depends(get_current_user_universal)):
    token = current_user.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Token user tidak tersedia")

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {token}"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(EXTERNAL_API_UNIT_KERJA, headers=headers) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=resp.status, detail="Gagal fetch data Unit Kerja")
                
                data = await resp.json()
                return data

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/asset-barang")
async def proxy_get_asset_barang(
    search: str = Query(None, description="Kata kunci pencarian asset"),
    current_user: dict = Depends(get_current_user_universal)
):
    token = current_user["access_token"] 

    url = "https://arise-app.my.id/api/asset-barang"
    params = {}
    if search:
        params["search"] = search

    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "accept": "application/json"
            },
            params=params
        ) as res:

            if res.status != 200:
                text = await res.text()
                raise HTTPException(
                    status_code=res.status,
                    detail=text
                )

            data = await res.json()
            return data

@router.get("/sub-kategori")
async def get_all_subkategori():
    url = "https://arise-app.my.id/api/sub-kategori"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as res:

            if res.status != 200:
                text = await res.text()
                raise HTTPException(
                    status_code=res.status,
                    detail=f"Error API SUB-KATEGORI: {text}"
                )

            data = await res.json()
            return data.get("data", []) 




@router.post("/pelaporan-online")
async def create_public_report(
    # id_aset_opd: int = Form(...),
    asset_id: int = Form(...),
    title: Optional[str] = Form(None),
    lokasi_kejadian: Optional[str] = Form(None),
    description: str = Form(...),
    expected_resolution: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    token = current_user.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Token SSO tidak tersedia")

    role_id_asset = int(current_user["role_id"])
    role = db.query(Roles).filter(Roles.role_id == role_id_asset).first()
    role_name = role.role_name if role else "pegawai"

    aset = await fetch_asset_from_api(token, asset_id)

    #ini dipake validasi ---comment temp
    opd_id_value = aset.get("unit_kerja", {}).get("dinas_id")
    # if not opd_id_value:
    #     raise HTTPException(400, "Asset tidak memiliki OPD")

    asset_kode_bmd = aset.get("kode_bmd")
    asset_nomor_seri = aset.get("nomor_seri")
    asset_nama = aset.get("nama_asset") or aset.get("nama") or aset.get("asset_name")
    asset_kategori = aset.get("kategori")
    asset_subkategori_id = aset.get("asset_barang", {}).get("sub_kategori", {}).get("id")
    asset_jenis = aset.get("jenis")
    asset_lokasi = aset.get("lokasi")

    # asset_subkategori_id = aset.get("asset_barang", {}).get("sub_kategori", {}).get("id")
    subkategori_nama = await fetch_subkategori_name(asset_subkategori_id)

    ticket_uuid = uuid4()
    old_status = None

    request_type = "pelaporan_online"

    latest_ticket = db.query(models.Tickets)\
        .filter(models.Tickets.request_type == request_type)\
        .order_by(models.Tickets.created_at.desc())\
        .first()

    if latest_ticket and latest_ticket.ticket_code:
        try:
            last_number = int(latest_ticket.ticket_code.split("-")[2])
        except:
            last_number = 0
        next_number = f"{last_number + 1:04d}"
    else:
        next_number = "0001"

    ticket_code = f"SVD-PO-{next_number}-PG"

    new_ticket = models.Tickets(
        ticket_id=ticket_uuid,
        title=title,
        description=description,
        expected_resolution=expected_resolution,
        status="Open",
        status_ticket_pengguna="Menunggu Diproses",
        status_ticket_seksi="Draft",
        created_at=datetime.utcnow(),
        creates_id=UUID(current_user["id"]),
        ticket_stage="Draft",
        ticket_source="Pegawai",
        opd_id_asset=opd_id_value,
        opd_id_tickets=opd_id_value, 
        asset_id=asset_id,
        kode_bmd_asset=asset_kode_bmd,
        nomor_seri_asset=asset_nomor_seri,
        nama_asset=asset_nama,
        kategori_asset=asset_kategori,
        subkategori_id_asset=asset_subkategori_id,
        subkategori_nama_asset=subkategori_nama,
        jenis_asset=asset_jenis,
        lokasi_asset=asset_lokasi,
        lokasi_kejadian=lokasi_kejadian,
        metadata_asset=aset,
        role_id_source=role_id_asset,
        request_type=request_type,
        ticket_code=ticket_code 
    )
    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)

    add_ticket_history(
        db=db,
        ticket=new_ticket,
        old_status=old_status,
        new_status=new_ticket.status, 
        updated_by=UUID(current_user["id"]),
        extra={"notes": "Tiket dibuat melalui pelaporan online"}
    )

    new_update = models.TicketUpdates(
        status_change=new_ticket.status,
        notes="Tiket dibuat melalui pelaporan online",
        makes_by_id=UUID(current_user["id"]),
        ticket_id=new_ticket.ticket_id
    )
    db.add(new_update)
    db.commit()

    await update_ticket_status(
        db=db,
        ticket=new_ticket,
        new_status="Menunggu Diproses",
        updated_by=current_user["id"]
    )

    uploaded_files = []
    if files:
        for file in files:
            try:
                file_url = upload_supabase_file("docs", ticket_uuid, file)
                new_attach = models.TicketAttachment(
                    attachment_id=uuid4(),
                    has_id=ticket_uuid,
                    uploaded_at=datetime.utcnow(),
                    file_path=file_url
                )
                db.add(new_attach)
                db.commit()
                uploaded_files.append(file_url)
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Gagal upload file {file.filename}: {str(e)}"
                )

    return {
        "message": "Laporan berhasil dibuat",
        "ticket_id": str(ticket_uuid),
        "ticket_code": new_ticket.ticket_code, 
        "title": new_ticket.title,
        "jenis_layanan": new_ticket.request_type,
        "opd_tujuan": new_ticket.opd_id_tickets,
        "created_at": new_ticket.created_at,
        "lokasi_kejadian": new_ticket.lokasi_kejadian,
        "status_ticket_pengguna": new_ticket.status_ticket_pengguna,


        "status": "Open",
        "asset": aset,
        # "opd_aset": opd_aset,
        "uploaded_files": uploaded_files
    }


@router.post("/pelaporan-online-masyarakat")
async def create_public_report_masyarakat(
    title: Optional[str] = Form(None),
    id_opd: int = Form(...),
    description: str = Form(...),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_masyarakat)
):
    if current_user.get("role_name", "").lower() != "masyarakat":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hanya masyarakat yang dapat membuat laporan ini"
        )

    if not description.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kolom 'description' wajib diisi")

    dinas = db.query(Dinas).filter(Dinas.id == id_opd).first()
    if not dinas:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dinas tidak ditemukan di sistem")

    ticket_uuid = uuid4()
    old_status = None

    request_type = "pelaporan_online"

    latest_ticket = db.query(models.Tickets)\
        .filter(models.Tickets.request_type == request_type)\
        .order_by(models.Tickets.created_at.desc())\
        .first()

    if latest_ticket and latest_ticket.ticket_code:
        try:
            last_number = int(latest_ticket.ticket_code.split("-")[2])
        except:
            last_number = 0
        next_number = f"{last_number + 1:04d}"
    else:
        next_number = "0001"

    ticket_code = f"SVD-PO-{next_number}-MA"

    new_ticket = Tickets(
        ticket_id=ticket_uuid,
        title=title,
        description=description,
        status="Open",
        status_ticket_pengguna="Menunggu Diproses",
        status_ticket_seksi="Draft",
        ticket_source="Masyarakat",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        creates_id=current_user.get("id"),
        request_type=request_type,
        ticket_stage="Draft",
        opd_id_asset=None,                
        opd_id_tickets=dinas.id,        
        role_id_source=current_user.get("role_id"),
        ticket_code=ticket_code
    )
    db.add(new_ticket)


    add_ticket_history(
        db=db,
        ticket=new_ticket,
        old_status=old_status,
        new_status=new_ticket.status, 
        updated_by=UUID(current_user["id"]),
        extra={"notes": "Tiket dibuat melalui pelaporan online"}
    )

    new_update = TicketUpdates(
        status_change=new_ticket.status,
        notes="Tiket dibuat melalui pelaporan online masyarakat",
        makes_by_id=current_user.get("id"),
        ticket_id=new_ticket.ticket_id
    )

    db.add(new_update)

    db.commit()
    db.refresh(new_ticket)


    await update_ticket_status(
        db=db,
        ticket=new_ticket,
        new_status="Menunggu Diproses",
        updated_by=current_user["id"]
    )

    uploaded_files = []
    if files:
        for file in files:
            try:
                file_url = upload_supabase_file("docs", str(ticket_uuid), file)
                new_attach = TicketAttachment(
                    attachment_id=uuid4(),
                    has_id=ticket_uuid,
                    uploaded_at=datetime.utcnow(),
                    file_path=file_url
                )
                db.add(new_attach)
                uploaded_files.append(file_url)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Gagal upload file {file.filename}: {str(e)}"
                )
        db.commit()  

    return {
        "message": "Laporan berhasil dibuat",
        "ticket_id": str(ticket_uuid),
        "ticket_code": new_ticket.ticket_code, 
        "title": new_ticket.title,
        "jenis_layanan": new_ticket.request_type,
        "opd_tujuan": new_ticket.opd_id_tickets,
        "created_at": new_ticket.created_at,
        "lokasi_kejadian": new_ticket.lokasi_kejadian,
        "status_ticket_pengguna": new_ticket.status_ticket_pengguna,


        "status": "Open",
        # "opd_aset": opd_aset,
        "uploaded_files": uploaded_files
    }


@router.post("/pengajuan-pelayanan")
async def create_service_request(
    nama_asset: int = Form(...), 
    title: str = Form(...),
    lokasi_penempatan: Optional[str] = Form(None),
    description: str = Form(...),
    expected_resolution: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    token = current_user.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Token SSO tidak tersedia")

    subkategori_nama = await fetch_subkategori_name(nama_asset)
    ticket_uuid = uuid4()
    request_type = "pengajuan_pelayanan"

    latest_ticket = db.query(models.Tickets)\
        .filter(models.Tickets.request_type == request_type)\
        .order_by(models.Tickets.created_at.desc())\
        .first()

    if latest_ticket and latest_ticket.ticket_code:
        try:
            last_number = int(latest_ticket.ticket_code.split("-")[2])
        except:
            last_number = 0
        next_number = f"{last_number + 1:04d}"
    else:
        next_number = "0001"

    ticket_code = f"SVD-PL-{next_number}-PG"

    new_ticket = models.Tickets(
        ticket_id=ticket_uuid,
        title=title,
        description=description,
        expected_resolution=expected_resolution,
        status="Open",
        status_ticket_pengguna="Menunggu Diproses",
        status_ticket_seksi="Draft",
        created_at=datetime.utcnow(),
        creates_id=UUID(current_user["id"]),
        ticket_stage="Draft",
        ticket_source="Pegawai",
        subkategori_id_asset=nama_asset,
        subkategori_nama_asset=subkategori_nama,
        lokasi_penempatan=lokasi_penempatan,
        request_type=request_type,
        ticket_code=ticket_code,
        opd_id_tickets=current_user.get("dinas_id")  
    )

    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)

    uploaded_files = []
    if files:
        for file in files:
            try:
                file_url = upload_supabase_file("docs", ticket_uuid, file)
                new_attach = models.TicketAttachment(
                    attachment_id=uuid4(),
                    has_id=ticket_uuid,
                    uploaded_at=datetime.utcnow(),
                    file_path=file_url
                )
                db.add(new_attach)
                db.commit()
                uploaded_files.append(file_url)
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Gagal upload file {file.filename}: {str(e)}"
                )

    return {
        "message": "Pengajuan pelayanan berhasil dibuat",
        "ticket_id": str(ticket_uuid),
        "ticket_code": ticket_code,
        "title": title,
        "jenis_layanan": request_type,
        "lokasi_penempatan": lokasi_penempatan,
        "description": description,
        "expected_resolution": expected_resolution,
        "uploaded_files": uploaded_files
    }



# #SEKSI
# @router.get("/tickets/seksi")
# def get_tickets_for_seksi(
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):
#     if current_user.get("role_name") != "seksi":
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: hanya seksi yang dapat melihat daftar tiket"
#         )

#     seksi_opd_id = current_user.get("dinas_id")
#     if not seksi_opd_id:
#         raise HTTPException(
#             status_code=400,
#             detail="User tidak memiliki OPD"
#         )

#     allowed_status = [
#         "Reopen",
#         "Open",           
#         "verified by seksi",   
#         "rejected by bidang"   
#     ]

#     tickets = (
#         db.query(models.Tickets)
#         .filter(models.Tickets.opd_id_tickets == seksi_opd_id)
#         .filter(models.Tickets.status.in_(allowed_status))
#         .filter(models.Tickets.request_type == "pelaporan_online")  
#         .order_by(models.Tickets.created_at.desc())
#         .all()
#     )

#     return {
#         "total": len(tickets),
#         "data": [
#             {
#                 "ticket_id": str(t.ticket_id),
#                 "ticket_code": t.ticket_code,
#                 "title": t.title,
#                 "description": t.description,
#                 "status": t.status,
#                 # "stage": t.ticket_stage,
#                 "priority": t.priority,
#                 "created_at": t.created_at,
#                 "ticket_source": t.ticket_source,
#                 "status_ticket_pengguna": t.status_ticket_pengguna,
#                 "status_ticket_seksi": t.status_ticket_seksi,
            

#             #     "opd_id_tickets": t.opd_id_tickets,
#             #     "lokasi_kejadian": t.lokasi_kejadian,

#             #     "creator": {
#             #         "user_id": str(t.creates_id) if t.creates_id else None,
#             #         "full_name": t.creates_user.full_name if t.creates_user else None,
#             #         "profile": t.creates_user.profile_url if t.creates_user else None,
#             #         "email": t.creates_user.email if t.creates_user else None,
#             #     },

#             #     "asset": {
#             #         "asset_id": t.asset_id,
#             #         "nama_asset": t.nama_asset,
#             #         "kode_bmd": t.kode_bmd_asset,
#             #         "nomor_seri": t.nomor_seri_asset,
#             #         "kategori": t.kategori_asset,
#             #         "subkategori_id": t.subkategori_id_asset,
#             #         "subkategori_nama": t.subkategori_nama_asset,
#             #         "jenis_asset": t.jenis_asset,
#             #         "lokasi_asset": t.lokasi_asset,
#             #         "opd_id_asset": t.opd_id_asset,
#             #     }
#             }
#             for t in tickets
#         ]
#     }



# # DETAIL SEKSI
# @router.get("/tickets/seksi/detail/{ticket_id}")
# def get_ticket_detail_seksi(
#     ticket_id: str,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):
#     if current_user.get("role_name") != "seksi":
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: hanya seksi yang dapat melihat detail tiket"
#         )

#     seksi_opd_id = current_user.get("dinas_id")
#     if not seksi_opd_id:
#         raise HTTPException(
#             status_code=400,
#             detail="User tidak memiliki OPD"
#         )

#     allowed_status = [
#         "Reopen",
#         "Open",           
#         "verified by seksi",   
#         "rejected by bidang"   
#     ]

#     ticket = (
#         db.query(models.Tickets)
#         .filter(models.Tickets.ticket_id == ticket_id)
#         .filter(models.Tickets.opd_id_tickets == seksi_opd_id)
#         .filter(models.Tickets.status.in_(allowed_status))
#         .filter(models.Tickets.request_type == "pelaporan_online")
#         .first()
#     )

#     if not ticket:
#         raise HTTPException(
#             status_code=404,
#             detail="Tiket tidak ditemukan, sudah terverifikasi bidang atau tidak memiliki akses"
#         )

#     attachments = (
#         db.query(models.TicketAttachment)
#         .filter(models.TicketAttachment.has_id == ticket_id)
#         .all()
#     )


#     return {
#         "ticket_id": str(ticket.ticket_id),
#         "ticket_code": ticket.ticket_code,
#         "title": ticket.title,
#         "description": ticket.description,
#         "status": ticket.status,
#         # "stage": ticket.ticket_stage,
#         "created_at": ticket.created_at,
#         "priority": ticket.priority,

#         "opd_id_tickets": ticket.opd_id_tickets,
#         "lokasi_kejadian": ticket.lokasi_kejadian,
#         "expected_resolution": ticket.expected_resolution,
#         "ticket_source": ticket.ticket_source,
#         "status_ticket_pengguna": ticket.status_ticket_pengguna,
#         "status_ticket_seksi": ticket.status_ticket_seksi,
        
#         "creator": {
#             "user_id": str(ticket.creates_id) if ticket.creates_id else None,
#             "full_name": ticket.creates_user.full_name if ticket.creates_user else None,
#             "profile": ticket.creates_user.profile_url if ticket.creates_user else None,
#             "email": ticket.creates_user.email if ticket.creates_user else None,
#         },

#         "asset": {
#             "asset_id": ticket.asset_id,
#             "nama_asset": ticket.nama_asset,
#             "kode_bmd": ticket.kode_bmd_asset,
#             "nomor_seri": ticket.nomor_seri_asset,
#             "kategori": ticket.kategori_asset,
#             "subkategori_id": ticket.subkategori_id_asset,
#             "subkategori_nama": ticket.subkategori_nama_asset,
#             "jenis_asset": ticket.jenis_asset,
#             "lokasi_asset": ticket.lokasi_asset,
#             "opd_id_asset": ticket.opd_id_asset,
#         },
#         "files": [
#             {
#                 "attachment_id": str(a.attachment_id),
#                 "file_path": a.file_path,
#                 "uploaded_at": a.uploaded_at
#             }
#             for a in attachments
#         ]
#     }



# @router.put("/tickets/{ticket_id}/priority")
# async def update_ticket_priority(
#     ticket_id: str,
#     payload: schemas.UpdatePriority,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):
#     if current_user.get("role_name") != "seksi":
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: hanya seksi yang dapat mengubah prioritas"
#         )

#     ticket = (
#         db.query(models.Tickets)
#         .filter(models.Tickets.ticket_id == ticket_id)
#         .first()
#     )

#     if not ticket:
#         raise HTTPException(404, "Tiket tidak ditemukan")

#     old_status = ticket.status

#     if ticket.ticket_source != "Pegawai":
#         raise HTTPException(
#             status_code=400,
#             detail="Tiket bukan berasal dari Pegawai, gunakan endpoint /priority/masyarakat."
#         )

#     if ticket.status == "rejected":
#         raise HTTPException(
#             400,
#             "Tiket sudah ditolak dan tidak dapat diproses lagi."
#         )

#     if ticket.priority is None and ticket.status != "rejected by bidang":
#         pass

#     elif ticket.status == "rejected by bidang":
#         ticket.rejection_reason_bidang = None
#         ticket.status_ticket_seksi = "pending"

#     else:
#         raise HTTPException(
#             400,
#             f"Tiket sudah memiliki prioritas '{ticket.priority}' dan tidak bisa diubah lagi."
#         )

#     # if ticket.priority is not None:
#     #     raise HTTPException(
#     #         status_code=400,
#     #         detail=f"Prioritas sudah diset menjadi '{ticket.priority}' dan tidak dapat diubah lagi."
#     #     )

#     urgency = payload.urgency
#     impact = payload.impact
#     score = urgency * impact

#     if score == 9:
#         priority = "Critical"
#     elif score == 6:
#         priority = "High"
#     elif score in (3, 4):
#         priority = "Medium"
#     elif score in (1, 2):
#         priority = "Low"
#     else:
#         raise HTTPException(400, "Nilai urgensi * dampak tidak valid")


#     ticket.priority = priority
#     ticket.priority_score = score
#     ticket.verified_seksi_id = current_user.get("id")

#     if priority == "Critical":
#         ticket.ticket_stage = "war-room-required"
#         ticket.status = "critical - waiting war room"
#         ticket.status_ticket_seksi = "done"
#         ticket.status_ticket_pengguna = "menunggu war room"

#     else:
#         ticket.ticket_stage = "pending"
#         ticket.status = "verified by seksi"
#         ticket.status_ticket_seksi = "pending"
#         ticket.status_ticket_pengguna = "proses verifikasi"

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
#         new_status="Proses Verifikasi",
#         updated_by=current_user["id"]
#     )

#     # db.commit()
#     # db.refresh(ticket)

#     return {
#         "message": "Prioritas tiket berhasil ditetapkan",
#         "ticket_id": ticket_id,
#         "priority": ticket.priority,
#         "score": score
#     }


# @router.put("/tickets/{ticket_id}/priority/masyarakat")
# async def set_priority_masyarakat(
#     ticket_id: str,
#     payload: schemas.ManualPriority,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):

#     if current_user.get("role_name") != "seksi":
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: hanya seksi yang dapat mengubah prioritas"
#         )

#     ticket = db.query(models.Tickets).filter_by(ticket_id=ticket_id).first()
#     if not ticket:
#         raise HTTPException(404, "Tiket tidak ditemukan")

#     old_status = ticket.status

#     if ticket.ticket_source != "Masyarakat":
#         raise HTTPException(
#             status_code=400,
#             detail="Tiket bukan berasal dari masyarakat, gunakan endpoint matrix."
#         )

#     if ticket.status == "rejected":
#         raise HTTPException(
#             400,
#             "Tiket sudah ditolak dan tidak dapat diproses lagi."
#         )

#     if ticket.priority is None and ticket.status != "rejected by bidang":
#         pass

#     elif ticket.status == "rejected by bidang":
#         ticket.rejection_reason_bidang = None
#         ticket.status_ticket_seksi = "pending"

#     else:
#         raise HTTPException(
#             400,
#             f"Tiket sudah memiliki prioritas '{ticket.priority}' dan tidak bisa diubah lagi."
#         )

#     # if ticket.priority is not None:
#     #     raise HTTPException(
#     #         400,
#     #         f"Prioritas sudah ditetapkan menjadi '{ticket.priority}' dan tidak dapat diubah lagi."
#     #     )

#     valid_priorities = ["low", "medium", "high", "critical"]
#     if payload.priority.lower() not in valid_priorities:
#         raise HTTPException(
#             400,
#             "Prioritas tidak valid, harus salah satu: low, medium, high, critical."
#         )

#     ticket.priority = payload.priority.capitalize()  
#     ticket.ticket_stage = "pending"
#     ticket.status = "verified by seksi"
#     ticket.status_ticket_seksi="pending"
#     ticket.status_ticket_pengguna="proses verifikasi"
#     ticket.verified_seksi_id=current_user.get("id")


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
#         new_status="Proses Verifikasi",
#         updated_by=current_user["id"]
#     )

#     return {
#         "message": "Prioritas tiket masyarakat berhasil ditetapkan",
#         "ticket_id": ticket_id,
#         "priority": ticket.priority
#     }


# @router.put("/tickets/{ticket_id}/reject")
# async def reject_ticket(
#     ticket_id: str,
#     payload: schemas.RejectReasonSeksi,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):

#     if current_user.get("role_name") != "seksi":
#         raise HTTPException(
#             403, "Akses ditolak: hanya seksi yang dapat menolak tiket"
#         )

#     ticket = db.query(models.Tickets).filter_by(ticket_id=ticket_id).first()
#     if not ticket:
#         raise HTTPException(404, "Tiket tidak ditemukan")

#     old_status = ticket.status

#     if ticket.priority is not None or ticket.status == "rejected":
#         raise HTTPException(
#             400,
#             "Tiket sudah diproses set prioritas dan tidak dapat diubah lagi."
#         )

#     ticket.status = "rejected"  
#     ticket.ticket_stage = "done" 
#     ticket.status_ticket_pengguna = "tiket ditolak"
#     ticket.status_ticket_seksi = "rejected"
#     ticket.rejection_reason_seksi = payload.reason

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
#         new_status="Tiket Ditolak",
#         updated_by=current_user["id"]
#     )

#     return {
#         "message": "Tiket berhasil ditolak",
#         "ticket_id": ticket_id,
#         "status": ticket.status,
#         "reason": ticket.rejection_reason_seksi
#     }



# @router.get("/tickets/seksi/verified-bidang")
# def get_tickets_verified_by_bidang_for_seksi(
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):

#     if current_user.get("role_name") != "seksi":
#         raise HTTPException(
#             403,
#             "Akses ditolak: hanya seksi yang dapat mengakses daftar tiket ini"
#         )

#     seksi_opd_id = current_user.get("dinas_id")
#     if not seksi_opd_id:
#         raise HTTPException(400, "User tidak memiliki OPD")

#     tickets = (
#         db.query(models.Tickets)
#         .filter(
#             models.Tickets.opd_id_tickets == seksi_opd_id,
#             or_(
#                 models.Tickets.status == "verified by bidang",
#                 models.Tickets.status == "assigned to teknisi",
#                 models.Tickets.status == "diproses"
#             ),
#             models.Tickets.request_type == "pelaporan_online"
#         )
#         .order_by(models.Tickets.created_at.desc())
#         .all()
#     )

#     result = []

#     for t in tickets:
#         attachments = t.attachments if hasattr(t, "attachments") else []

#         result.append({
#             "ticket_id": str(t.ticket_id),
#             "ticket_code": t.ticket_code,
#             "title": t.title,
#             "status": t.status,
#             "priority": t.priority,
#             "created_at": t.created_at,
#             "ticket_source": t.ticket_source,
#             "status_ticket_pengguna": t.status_ticket_pengguna,
#             "status_ticket_seksi": t.status_ticket_seksi,

#             "opd_id_tickets": t.opd_id_tickets,
#             "lokasi_kejadian": t.lokasi_kejadian,

#             "creator": {
#                     "user_id": str(t.creates_id) if t.creates_id else None,
#                     "full_name": t.creates_user.full_name if t.creates_user else None,
#                     "profile": t.creates_user.profile_url if t.creates_user else None,
#                     "email": t.creates_user.email if t.creates_user else None,
#             },

#             "asset": {
#                 "asset_id": t.asset_id,
#                 "nama_asset": t.nama_asset,
#                 "kode_bmd": t.kode_bmd_asset,
#                 "nomor_seri": t.nomor_seri_asset,
#                 "kategori": t.kategori_asset,
#                 "subkategori_id": t.subkategori_id_asset,
#                 "subkategori_nama": t.subkategori_nama_asset,
#                 "jenis_asset": t.jenis_asset,
#                 "lokasi_asset": t.lokasi_asset,
#                 "opd_id_asset": t.opd_id_asset,
#             },

#             "files": [
#                 {
#                     "attachment_id": str(a.attachment_id),
#                     "file_path": a.file_path,
#                     "uploaded_at": a.uploaded_at
#                 }
#                 for a in attachments
#             ]
#         })

#     return {
#         "total": len(result),
#         "data": result
#     }

# @router.get("/tickets/seksi/verified-bidang/{ticket_id}")
# def get_ticket_detail_verified_by_bidang_for_seksi(
#     ticket_id: str,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):

#     if current_user.get("role_name") != "seksi":
#         raise HTTPException(
#             403,
#             "Akses ditolak: hanya seksi yang dapat mengakses detail tiket ini"
#         )

#     seksi_opd_id = current_user.get("dinas_id")
#     if not seksi_opd_id:
#         raise HTTPException(400, "User tidak memiliki OPD")

#     try:
#         uuid_obj = uuid.UUID(ticket_id)
#     except ValueError:
#         raise HTTPException(400, "ticket_id tidak valid (bukan UUID)")

#     ticket = (
#         db.query(models.Tickets)
#         .filter(
#             models.Tickets.ticket_id == uuid_obj,
#             models.Tickets.opd_id_tickets == seksi_opd_id,
#             models.Tickets.status == "verified by bidang",
#             models.Tickets.request_type == "pelaporan_online"
#         )
#         .first()
#     )

#     if not ticket:
#         raise HTTPException(404, "Tiket tidak ditemukan atau tidak memiliki akses")

#     attachments = ticket.attachments if hasattr(ticket, "attachments") else []

#     return {
#         "ticket_id": str(ticket.ticket_id),
#         "ticket_code": ticket.ticket_code,
#         "title": ticket.title,
#         "description": ticket.description,
#         "priority": ticket.priority,
#         "status": ticket.status,
#         "created_at": ticket.created_at,
#         "updated_at": ticket.updated_at,

#         "lokasi_kejadian": ticket.lokasi_kejadian,
#         "opd_id_tickets": ticket.opd_id_tickets,

#         "creator": {
#             "user_id": str(ticket.creates_id) if ticket.creates_id else None,
#             "full_name": ticket.creates_user.full_name if ticket.creates_user else None,
#             "profile": ticket.creates_user.profile_url if ticket.creates_user else None,
#             "email": ticket.creates_user.email if ticket.creates_user else None,
#         },

#         "asset": {
#             "asset_id": ticket.asset_id,
#             "nama_asset": ticket.nama_asset,
#             "kode_bmd": ticket.kode_bmd_asset,
#             "nomor_seri": ticket.nomor_seri_asset,
#             "kategori": ticket.kategori_asset,
#             "subkategori_id": ticket.subkategori_id_asset,
#             "subkategori_nama": ticket.subkategori_nama_asset,
#             "jenis_asset": ticket.jenis_asset,
#             "lokasi_asset": ticket.lokasi_asset,
#             "opd_id_asset": ticket.opd_id_asset,
#         },

#         "files": [
#             {
#                 "attachment_id": str(a.attachment_id),
#                 "file_path": a.file_path,
#                 "uploaded_at": a.uploaded_at
#             }
#             for a in attachments
#         ]
#     }




# @router.get("/teknisi/seksi")
# def get_technicians_for_seksi(
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):

#     if current_user.get("role_name") != "seksi":
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: hanya seksi yang dapat melihat daftar teknisi"
#         )

#     seksi_opd_id = current_user.get("dinas_id")
#     if not seksi_opd_id:
#         raise HTTPException(
#             status_code=400,
#             detail="User tidak memiliki OPD"
#         )

#     technicians = (
#         db.query(Users)
#         .filter(Users.role_id == 6) 
#         .filter(Users.opd_id == seksi_opd_id)
#         .all()
#     )

#     result = []

#     for tech in technicians:
#         level = tech.teknisi_level_obj  
#         tag = tech.teknisi_tag_obj  

#         quota = level.quota if level else 0
#         used = tech.teknisi_kuota_terpakai or 0
#         remaining_quota = quota - used

#         result.append({
#             "id": str(tech.id),
#             "full_name": tech.full_name,
#             "profile_url": tech.profile_url,
#             "email": tech.email,

#             "tag": tag.name if tag else None,
#             "tag_id": tag.id if tag else None,

#             "level": level.name if level else None,
#             "level_id": level.id if level else None,
#             "quota": quota,

#             "current_load": used,
#             "remaining_quota": remaining_quota
#         })

#     return {
#         "total": len(result),
#         "data": result
#     }


# @router.put("/tickets/{ticket_id}/assign-teknisi")
# async def assign_teknisi(
#     ticket_id: str,
#     payload: AssignTeknisiSchema,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):
#     if current_user.get("role_name") != "seksi":
#         raise HTTPException(status_code=403, detail="Akses ditolak")

#     ticket = db.query(Tickets).filter(Tickets.ticket_id == ticket_id).first()
#     if not ticket:
#         raise HTTPException(status_code=404, detail="Ticket tidak ditemukan")

#     old_status = ticket.status

#     if ticket.assigned_teknisi_id is not None:
#         raise HTTPException(
#             status_code=400,
#             detail="Tiket ini sudah pernah di-assign ke teknisi. Tidak boleh assign ulang."
#         )

#     if ticket.status != "verified by bidang":
#         raise HTTPException(status_code=400, detail="Ticket belum diverifikasi bidang")

#     teknisi = db.query(Users).filter(Users.id == payload.teknisi_id).first()
#     if not teknisi:
#         raise HTTPException(status_code=400, detail="Teknisi tidak ditemukan")

#     if teknisi.role_id != 6:
#         raise HTTPException(status_code=400, detail="User ini bukan teknisi")


#     if teknisi.opd_id != current_user.get("dinas_id"):
#         raise HTTPException(status_code=403, detail="Teknisi bukan dari OPD yang sama")

#     level = teknisi.teknisi_level_obj
#     if (teknisi.teknisi_kuota_terpakai or 0) >= level.quota:
#         raise HTTPException(status_code=400, detail="Kuota teknisi penuh")

#     now_time = datetime.now().time()
#     pengerjaan_awal = datetime.combine(payload.pengerjaan_awal, now_time)
#     pengerjaan_akhir = datetime.combine(payload.pengerjaan_akhir, now_time)

#     ticket.assigned_teknisi_id = payload.teknisi_id
#     ticket.pengerjaan_awal = pengerjaan_awal
#     ticket.pengerjaan_akhir = pengerjaan_akhir
#     ticket.status = "assigned to teknisi"
#     ticket.status_ticket_teknisi = "Draft"
#     ticket.status_ticket_pengguna = "proses penugasan teknisi"
#     ticket.status_ticket_seksi = "diproses"

#     teknisi.teknisi_kuota_terpakai += 1


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
#         new_status="Proses Penugasan Teknisi",
#         updated_by=current_user["id"]
#     )

#     return {"message": "Teknisi berhasil diassign", "ticket_id": ticket_id}


# @router.get("/tickets/seksi/assigned")
# def get_assigned_tickets_for_seksi(
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):
#     if current_user.get("role_name") != "seksi":
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: hanya seksi yang dapat melihat tiket assigned."
#         )

#     seksi_opd_id = current_user.get("dinas_id")

#     tickets = (
#         db.query(
#             Tickets.ticket_id,
#             Tickets.ticket_code,
#             Tickets.title,
#             Tickets.assigned_teknisi_id,
#             Tickets.pengerjaan_awal,
#             Tickets.pengerjaan_akhir,
#             Tickets.status,
#             Users.full_name.label("nama_teknisi"),
#             Tickets.request_type,
#             Tickets.created_at
#         )
#         .join(Users, Users.id == Tickets.assigned_teknisi_id)
#         .filter(
#             Tickets.opd_id_tickets == seksi_opd_id,
#             Tickets.assigned_teknisi_id.isnot(None)  # sudah diassign teknisi
#         )
#         .order_by(Tickets.created_at.desc())
#         .all()
#     )

#     return {
#         "status": "success",
#         "count": len(tickets),
#         "data": [
#             {
#                 "ticket_id": str(t.ticket_id),
#                 "ticket_code": t.ticket_code,
#                 "title": t.title,
#                 "assigned_teknisi_id": str(t.assigned_teknisi_id),
#                 "nama_teknisi": t.nama_teknisi,
#                 "pengerjaan_awal": t.pengerjaan_awal,
#                 "pengerjaan_akhir": t.pengerjaan_akhir,
#                 "status": t.status,
#                 "request_type": t.request_type,
#                 "created_at": t.created_at
#             }
#             for t in tickets
#         ]
#     }


# @router.get("/tickets/seksi/assigned/{teknisi_id}")
# def get_assigned_tickets_by_teknisi(
#     teknisi_id: str,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_universal)
# ):
#     if current_user.get("role_name") != "seksi":
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: hanya seksi yang dapat melihat tiket assigned."
#         )

#     seksi_opd_id = current_user.get("dinas_id")

#     tickets = (
#         db.query(
#             Tickets.ticket_id,
#             Tickets.ticket_code,
#             Tickets.title,
#             Tickets.assigned_teknisi_id,
#             Tickets.pengerjaan_awal,
#             Tickets.pengerjaan_akhir,
#             Tickets.status,
#             Users.full_name.label("nama_teknisi"),
#             Tickets.request_type,
#             Tickets.created_at
#         )
#         .join(Users, Users.id == Tickets.assigned_teknisi_id)
#         .filter(
#             Tickets.opd_id_tickets == seksi_opd_id, 
#             Tickets.assigned_teknisi_id == teknisi_id
#         )
#         .order_by(Tickets.created_at.desc())
#         .all()
#     )

#     return {
#         "status": "success",
#         "count": len(tickets),
#         "data": [
#             {
#                 "ticket_id": str(t.ticket_id),
#                 "ticket_code": t.ticket_code,
#                 "title": t.title,
#                 "assigned_teknisi_id": str(t.assigned_teknisi_id),
#                 "nama_teknisi": t.nama_teknisi,
#                 "pengerjaan_awal": t.pengerjaan_awal,
#                 "pengerjaan_akhir": t.pengerjaan_akhir,
#                 "status": t.status,
#                 "request_type": t.request_type,
#                 "created_at": t.created_at
#             }
#             for t in tickets
#         ]
#     }


# @router.get("/tickets/seksi/assigned/teknisi/{ticket_id}")
# def get_ticket_detail_assigned_to_teknisi_for_seksi(
#     ticket_id: str,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):

#     if current_user.get("role_name") != "seksi":
#         raise HTTPException(
#             403,
#             "Akses ditolak: hanya seksi yang dapat mengakses detail tiket ini"
#         )

#     seksi_opd_id = current_user.get("dinas_id")
#     if not seksi_opd_id:
#         raise HTTPException(400, "User tidak memiliki OPD")

#     try:
#         uuid_obj = uuid.UUID(ticket_id)
#     except ValueError:
#         raise HTTPException(400, "ticket_id tidak valid (bukan UUID)")

#     ticket = (
#         db.query(models.Tickets)
#         .filter(
#             models.Tickets.ticket_id == uuid_obj,
#             models.Tickets.opd_id_tickets == seksi_opd_id,
#             models.Tickets.assigned_teknisi_id.isnot(None)  # sudah diassign teknisi
#         )
#         .first()
#     )

#     if not ticket:
#         raise HTTPException(404, "Tiket tidak ditemukan atau tidak memiliki akses")

#     attachments = ticket.attachments if hasattr(ticket, "attachments") else []

#     return {
#         "ticket_id": str(ticket.ticket_id),
#         "ticket_code": ticket.ticket_code,
#         "title": ticket.title,
#         "description": ticket.description,
#         "priority": ticket.priority,
#         "status": ticket.status,
#         "created_at": ticket.created_at,
#         "updated_at": ticket.updated_at,
#         "status_ticket_seksi": ticket.status_ticket_seksi,

#         "lokasi_kejadian": ticket.lokasi_kejadian,
#         "opd_id_tickets": ticket.opd_id_tickets,

#         "creator": {
#             "user_id": str(ticket.creates_id) if ticket.creates_id else None,
#             "full_name": ticket.creates_user.full_name if ticket.creates_user else None,
#             "profile": ticket.creates_user.profile_url if ticket.creates_user else None,
#             "email": ticket.creates_user.email if ticket.creates_user else None,
#         },

#         "asset": {
#             "asset_id": ticket.asset_id,
#             "nama_asset": ticket.nama_asset,
#             "kode_bmd": ticket.kode_bmd_asset,
#             "nomor_seri": ticket.nomor_seri_asset,
#             "kategori": ticket.kategori_asset,
#             "subkategori_id": ticket.subkategori_id_asset,
#             "subkategori_nama": ticket.subkategori_nama_asset,
#             "jenis_asset": ticket.jenis_asset,
#             "lokasi_asset": ticket.lokasi_asset,
#             "opd_id_asset": ticket.opd_id_asset,
#         },

#         "files": [
#             {
#                 "attachment_id": str(a.attachment_id),
#                 "file_path": a.file_path,
#                 "uploaded_at": a.uploaded_at
#             }
#             for a in attachments
#         ]
#     }





# @router.get("/seksi/ratings")
# def get_ratings_for_seksi(
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):

#     if current_user.get("role_name") != "seksi":
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: hanya seksi yang dapat melihat data rating."
#         )

#     seksi_id = current_user.get("id")
#     opd_id_user = current_user.get("dinas_id")

#     tickets = (
#         db.query(models.Tickets)
#         .filter(
#             models.Tickets.verified_seksi_id == seksi_id,
#             models.Tickets.opd_id_tickets == opd_id_user
#         )
#         .order_by(models.Tickets.created_at.desc())
#         .all()
#     )

#     results = []
#     for t in tickets:

#         rating = (
#             db.query(models.TicketRatings)
#             .filter(models.TicketRatings.ticket_id == t.ticket_id)
#             .first()
#         )

#         if not rating:
#             continue

#         attachments = t.attachments if hasattr(t, "attachments") else []

#         results.append({
#             "ticket_id": str(t.ticket_id),
#             "ticket_code": t.ticket_code,
#             "title": t.title,
#             "status": t.status,
#             "verified_seksi_id": t.verified_seksi_id,
#             "opd_id": t.opd_id_tickets,

#             "rating": rating.rating if rating else None,
#             "comment": rating.comment if rating else None,
#             "rated_at": rating.created_at if rating else None,

#             "description": t.description,
#             "priority": t.priority,
#             "lokasi_kejadian": t.lokasi_kejadian,
#             "expected_resolution": t.expected_resolution,
#             "pengerjaan_awal": t.pengerjaan_awal,
#             "pengerjaan_akhir": t.pengerjaan_akhir,
#             "pengerjaan_awal_teknisi": t.pengerjaan_awal_teknisi,
#             "pengerjaan_akhir_teknisi": t.pengerjaan_akhir_teknisi,

#             "creator": {
#                 "user_id": str(t.creates_id) if t.creates_id else None,
#                 "full_name": t.creates_user.full_name if t.creates_user else None,
#                 "profile": t.creates_user.profile_url if t.creates_user else None,
#                 "email": t.creates_user.email if t.creates_user else None,
#             },

#             "asset": {
#                 "asset_id": t.asset_id,
#                 "nama_asset": t.nama_asset,
#                 "kode_bmd": t.kode_bmd_asset,
#                 "nomor_seri": t.nomor_seri_asset,
#                 "kategori": t.kategori_asset,
#                 "subkategori_id": t.subkategori_id_asset,
#                 "subkategori_nama": t.subkategori_nama_asset,
#                 "jenis_asset": t.jenis_asset,
#                 "lokasi_asset": t.lokasi_asset,
#                 "opd_id_asset": t.opd_id_asset,
#             },

#             "files": [
#                 {
#                     "attachment_id": str(a.attachment_id),
#                     "file_path": a.file_path,
#                     "uploaded_at": a.uploaded_at
#                 }
#                 for a in attachments
#             ]
#         })

#     return {
#         "total": len(results),
#         "data": results
#     }


# @router.get("/seksi/ratings/{ticket_id}")
# def get_rating_detail_for_seksi(
#     ticket_id: str,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):

#     if current_user.get("role_name") != "seksi":
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: hanya seksi yang dapat melihat data rating."
#         )

#     seksi_id = current_user.get("id")
#     opd_id_user = current_user.get("dinas_id")

#     ticket = (
#         db.query(models.Tickets)
#         .filter(
#             models.Tickets.ticket_id == ticket_id,
#             models.Tickets.verified_seksi_id == seksi_id,
#             models.Tickets.opd_id_tickets == opd_id_user
#         )
#         .first()
#     )

#     if not ticket:
#         raise HTTPException(
#             status_code=404,
#             detail="Tiket tidak ditemukan atau Anda tidak memiliki akses."
#         )

#     rating = (
#         db.query(models.TicketRatings)
#         .filter(models.TicketRatings.ticket_id == ticket.ticket_id)
#         .first()
#     )


#     if not rating:
#         return {
#             "ticket_id": str(ticket.ticket_id),
#             "ticket_code": ticket.ticket_code,
#             "rating": None,
#             "comment": None,
#             "rated_at": None
#         }


#     attachments = ticket.attachments if hasattr(ticket, "attachments") else []

#     return {
#         "ticket_id": str(ticket.ticket_id),
#         "ticket_code": ticket.ticket_code,
#         "title": ticket.title,
#         "status": ticket.status,
#         "verified_seksi_id": ticket.verified_seksi_id,
#         "opd_id": ticket.opd_id_tickets,

#         "rating": rating.rating if rating else None,
#         "comment": rating.comment if rating else None,
#         "rated_at": rating.created_at if rating else None,

#         "description": ticket.description,
#         "priority": ticket.priority,
#         "lokasi_kejadian": ticket.lokasi_kejadian,
#         "expected_resolution": ticket.expected_resolution,
#         "pengerjaan_awal": ticket.pengerjaan_awal,
#         "pengerjaan_akhir": ticket.pengerjaan_akhir,
#         "pengerjaan_awal_teknisi": ticket.pengerjaan_awal_teknisi,
#         "pengerjaan_akhir_teknisi": ticket.pengerjaan_akhir_teknisi,

#         "creator": {
#             "user_id": str(ticket.creates_id) if ticket.creates_id else None,
#             "full_name": ticket.creates_user.full_name if ticket.creates_user else None,
#             "profile": ticket.creates_user.profile_url if ticket.creates_user else None,
#             "email": ticket.creates_user.email if ticket.creates_user else None,
#         },

#         "asset": {
#             "asset_id": ticket.asset_id,
#             "nama_asset": ticket.nama_asset,
#             "kode_bmd": ticket.kode_bmd_asset,
#             "nomor_seri": ticket.nomor_seri_asset,
#             "kategori": ticket.kategori_asset,
#             "subkategori_id": ticket.subkategori_id_asset,
#             "subkategori_nama": ticket.subkategori_nama_asset,
#             "jenis_asset": ticket.jenis_asset,
#             "lokasi_asset": ticket.lokasi_asset,
#             "opd_id_asset": ticket.opd_id_asset,
#         },

#         "files": [
#             {
#                 "attachment_id": str(a.attachment_id),
#                 "file_path": a.file_path,
#                 "uploaded_at": a.uploaded_at
#             }
#             for a in attachments
#         ]
#     }


# @router.get("/tickets/seksi/finished")
# def get_finished_tickets_for_seksi(
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):
#     if current_user.get("role_name") != "seksi":
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: hanya seksi OPD yang dapat melihat daftar tiket selesai."
#         )

#     seksi_opd_id = current_user.get("dinas_id")

#     masyarakat_tickets = (
#         db.query(models.Tickets)
#         .filter(
#             models.Tickets.status == "selesai",
#             models.Tickets.opd_id_tickets == seksi_opd_id,
#             models.Tickets.asset_id.is_(None)
#         )
#         .order_by(models.Tickets.created_at.desc())
#         .all()
#     )

#     masyarakat_result = [
#         {
#             "ticket_id": t.ticket_id,
#             "ticket_code": t.ticket_code,
#             "title": t.title,
#             "description": t.description,
#             "status": t.status,
#             "latest_report_date": t.created_at,
#             "asset": None,
#             "intensitas_laporan": None
#         }
#         for t in masyarakat_tickets
#     ]

#     subquery = (
#         db.query(
#             models.Tickets.asset_id,
#             func.max(models.Tickets.created_at).label("latest_date")
#         )
#         .filter(
#             models.Tickets.opd_id_tickets == seksi_opd_id,
#             models.Tickets.status == "selesai",
#             models.Tickets.asset_id.isnot(None)
#         )
#         .group_by(models.Tickets.asset_id)
#         .subquery()
#     )

#     latest_tickets = (
#         db.query(models.Tickets)
#         .join(
#             subquery,
#             (models.Tickets.asset_id == subquery.c.asset_id) &
#             (models.Tickets.created_at == subquery.c.latest_date)
#         )
#         .order_by(models.Tickets.created_at.desc())
#         .all()
#     )

#     asset_ids = {t.asset_id for t in latest_tickets}

#     intensitas_map = (
#         db.query(models.Tickets.asset_id, func.count(models.Tickets.ticket_id))
#         .filter(
#             models.Tickets.asset_id.in_(asset_ids),
#             models.Tickets.status == "selesai"
#         )
#         .group_by(models.Tickets.asset_id)
#         .all()
#     )
#     intensitas_dict = {asset_id: count for asset_id, count in intensitas_map}

#     aset_result = []
#     for t in latest_tickets:
#         aset_result.append({
#             "ticket_id": t.ticket_id,
#             "ticket_code": t.ticket_code,
#             "latest_report_date": t.created_at,
#             "title": t.title,
#             "description": t.description,
#             "status": t.status,

#             "intensitas_laporan": intensitas_dict.get(t.asset_id, 0),

#             "asset": {
#                 "asset_id": t.asset_id,
#                 "nama_asset": t.nama_asset,
#                 "kode_bmd": t.kode_bmd_asset,
#                 "nomor_seri": t.nomor_seri_asset,
#                 "kategori": t.kategori_asset,
#                 "subkategori_nama": t.subkategori_nama_asset,
#                 "jenis_asset": t.jenis_asset,
#                 "lokasi_asset": t.lokasi_asset,
#             }
#         })

#     combined = masyarakat_result + aset_result

#     combined_sorted = sorted(combined, key=lambda x: x["latest_report_date"], reverse=True)

#     return {
#         "total_tickets": len(combined_sorted),
#         "data": combined_sorted
#     }


# @router.get("/tickets/seksi/finished/{asset_id}")
# def get_finished_tickets_by_asset_id(
#     asset_id: int,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):

#     if current_user.get("role_name") != "seksi":
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: hanya seksi OPD yang dapat melihat detail tiket."
#         )

#     seksi_opd_id = current_user.get("dinas_id")

#     tickets = (
#         db.query(models.Tickets)
#         .filter(
#             models.Tickets.opd_id_tickets == seksi_opd_id,
#             models.Tickets.status == "selesai",
#             models.Tickets.asset_id == asset_id
#         )
#         .order_by(models.Tickets.created_at.desc())
#         .all()
#     )

#     if not tickets:
#         raise HTTPException(
#             status_code=404,
#             detail="Tidak ada tiket selesai untuk asset ini."
#         )

#     intensitas = len(tickets)

#     result = []
#     for t in tickets:
#         result.append({
#             "ticket_id": str(t.ticket_id),
#             "ticket_code": t.ticket_code,
#             "title": t.title,
#             "description": t.description,
#             "status": t.status,
#             "created_at": t.created_at,
#             "pengerjaan_awal": t.pengerjaan_awal,
#             "pengerjaan_akhir": t.pengerjaan_akhir,
#             "pengerjaan_awal_teknisi": t.pengerjaan_awal_teknisi,
#             "pengerjaan_akhir_teknisi": t.pengerjaan_akhir_teknisi,


#             "pelapor": {
#                 "user_id": str(t.creates_id) if t.creates_id else None,
#                 "full_name": t.creates_user.full_name if t.creates_user else None,
#                 "email": t.creates_user.email if t.creates_user else None,
#                 "profile": t.creates_user.profile_url if t.creates_user else None,
#             },

#             "asset": {
#                 "asset_id": t.asset_id,
#                 "nama_asset": t.nama_asset,
#                 "kode_bmd": t.kode_bmd_asset,
#                 "nomor_seri": t.nomor_seri_asset,
#                 "kategori": t.kategori_asset,
#                 "subkategori_nama": t.subkategori_nama_asset,
#                 "jenis_asset": t.jenis_asset,
#                 "lokasi_asset": t.lokasi_asset,
#             }
#         })

#     return {
#         "asset_id": asset_id,
#         "intensitas_laporan": intensitas,
#         "total_tickets": len(tickets),
#         "data": result
#     }

# @router.get("/tickets/seksi/finished/ticket/{ticket_id}")
# def get_finished_ticket_by_id(
#     ticket_id: str,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):
#     if current_user.get("role_name") != "seksi":
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: hanya seksi OPD yang dapat melihat detail tiket."
#         )

#     seksi_opd_id = current_user.get("dinas_id")

#     ticket = (
#         db.query(models.Tickets)
#         .filter(
#             models.Tickets.ticket_id == ticket_id,
#             models.Tickets.opd_id_tickets == seksi_opd_id,
#             models.Tickets.status == "selesai"
#         )
#         .first()
#     )

#     if not ticket:
#         raise HTTPException(
#             status_code=404,
#             detail="Tiket tidak ditemukan atau bukan milik OPD Anda / belum selesai."
#         )

#     attachments = (
#         db.query(models.TicketAttachment)
#         .filter(models.TicketAttachment.has_id == ticket.ticket_id)
#         .all()
#     )

#     intensitas = None
#     if ticket.asset_id:
#         intensitas = (
#             db.query(func.count(models.Tickets.ticket_id))
#             .filter(
#                 models.Tickets.asset_id == ticket.asset_id,
#                 models.Tickets.status == "selesai"
#             )
#             .scalar()
#         )

#     response = {
#         "ticket_id": str(ticket.ticket_id),
#         "ticket_code": ticket.ticket_code,
#         "title": ticket.title,
#         "description": ticket.description,
#         "status": ticket.status,
#         "created_at": ticket.created_at,
#         "priority": ticket.priority,
#         "lokasi_kejadian": ticket.lokasi_kejadian,
#         "expected_resolution": ticket.expected_resolution,

#         "pengerjaan_awal": ticket.pengerjaan_awal,
#         "pengerjaan_akhir": ticket.pengerjaan_akhir,
#         "pengerjaan_awal_teknisi": ticket.pengerjaan_awal_teknisi,
#         "pengerjaan_akhir_teknisi": ticket.pengerjaan_akhir_teknisi,

#         "intensitas_laporan": intensitas,

#         "pelapor": {
#             "user_id": str(ticket.creates_id) if ticket.creates_id else None,
#             "full_name": ticket.creates_user.full_name if ticket.creates_user else None,
#             "email": ticket.creates_user.email if ticket.creates_user else None,
#             "profile": ticket.creates_user.profile_url if ticket.creates_user else None,
#         },

#         "asset": None,
#         "files": [
#             {
#                 "attachment_id": str(a.attachment_id),
#                 "file_path": a.file_path,
#                 "uploaded_at": a.uploaded_at
#             }
#             for a in attachments
#         ]
#     }

#     if ticket.asset_id:
#         response["asset"] = {
#             "asset_id": ticket.asset_id,
#             "nama_asset": ticket.nama_asset,
#             "kode_bmd": ticket.kode_bmd_asset,
#             "nomor_seri": ticket.nomor_seri_asset,
#             "kategori": ticket.kategori_asset,
#             "subkategori_nama": ticket.subkategori_nama_asset,
#             "jenis_asset": ticket.jenis_asset,
#             "lokasi_asset": ticket.lokasi_asset,
#         }

#     return response

# @router.get("/war-room/invitations/seksi")
# def get_war_room_invitation_seksi(
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):
#     seksi_id = current_user["id"]

#     war_rooms = (
#         db.query(WarRoom)
#         .join(WarRoomSeksi, WarRoomSeksi.war_room_id == WarRoom.id)
#         .filter(WarRoomSeksi.seksi_id == seksi_id)
#         .all()
#     )

#     return war_rooms


# @router.get("/war-room/{id}")
# def get_war_room_detail(
#     id: UUID,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_universal)
# ):
#     role = current_user.get("role_name")
#     user_id = current_user.get("id")
#     opd_id_user = current_user.get("dinas_id") 

#     war_room = (
#         db.query(WarRoom)
#         .filter(WarRoom.id == id)
#         .first()
#     )

#     if not war_room:
#         raise HTTPException(status_code=404, detail="War room tidak ditemukan")

#     if role == "admin dinas":
#         pass

#     elif role == "admin dinas":
#         invited = (
#             db.query(WarRoomOPD)
#             .filter(
#                 WarRoomOPD.war_room_id == id,
#                 WarRoomOPD.opd_id == opd_id_user
#             )
#             .first()
#         )
#         if not invited:
#             raise HTTPException(403, "Anda tidak diundang ke war room ini.")

#     elif role == "seksi":
#         invited = (
#             db.query(WarRoomSeksi)
#             .filter(
#                 WarRoomSeksi.war_room_id == id,
#                 WarRoomSeksi.seksi_id == user_id
#             )
#             .first()
#         )
#         if not invited:
#             raise HTTPException(403, "Anda tidak diundang ke war room ini.")

#     else:
#         raise HTTPException(403, "Akses ditolak.")

#     opd_list = db.query(WarRoomOPD).filter_by(war_room_id=id).all()
#     seksi_list = db.query(WarRoomSeksi).filter_by(war_room_id=id).all()


#     ticket = db.query(Ticket).filter(Ticket.ticket_id == war_room.ticket_id).first()

#     return {
#         "war_room": war_room,
#         "opd_undangan": opd_list,
#         "seksi_undangan": seksi_list,
#         "ticket": ticket
#     }









# # TEKNISI
# @router.get("/tickets/teknisi")
# def get_tickets_for_teknisi(
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):
#     if current_user.get("role_name") != "teknisi":
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: hanya teknisi yang dapat melihat daftar tiket"
#         )

#     teknisi_opd_id = current_user.get("dinas_id")
#     teknisi_user_id = current_user.get("id")

#     if not teknisi_opd_id:
#         raise HTTPException(
#             status_code=400,
#             detail="User tidak memiliki OPD"
#         )

#     allowed_status = ["assigned to teknisi", "diproses"]

#     tickets = (
#         db.query(models.Tickets)
#         .filter(models.Tickets.opd_id_tickets == teknisi_opd_id)
#         .filter(models.Tickets.assigned_teknisi_id == teknisi_user_id)
#         .filter(models.Tickets.status.in_(allowed_status))
#         .order_by(models.Tickets.created_at.desc())
#         .all()
#     )

#     attachments = tickets.attachments if hasattr(tickets, "attachments") else []


#     return {
#         "total": len(tickets),
#         "data": [
#             {
#                 "ticket_id": str(t.ticket_id),
#                 "ticket_code": t.ticket_code,
#                 "title": t.title,
#                 "description": t.description,
#                 "status": t.status,
#                 "priority": t.priority,
#                 "created_at": t.created_at,
#                 "ticket_source": t.ticket_source,
#                 "status_ticket_pengguna": t.status_ticket_pengguna,
#                 "status_ticket_seksi": t.status_ticket_seksi,
#                 "status_ticket_teknisi": t.status_ticket_teknisi,
#                 "pengerjaan_awal": t.pengerjaan_awal,
#                 "pengerjaan_akhir": t.pengerjaan_akhir,
#                 "pengerjaan_awal_teknisi": t.pengerjaan_awal_teknisi,
#                 "pengerjaan_akhir_teknisi": t.pengerjaan_akhir_teknisi,


#                 "creator": {
#                     "user_id": str(t.creates_id) if t.creates_id else None,
#                     "full_name": t.creates_user.full_name if t.creates_user else None,
#                     "profile": t.creates_user.profile_url if t.creates_user else None,
#                     "email": t.creates_user.email if t.creates_user else None,
#                 },

#                 "asset": {
#                     "asset_id": t.asset_id,
#                     "nama_asset": t.nama_asset,
#                     "kode_bmd": t.kode_bmd_asset,
#                     "nomor_seri": t.nomor_seri_asset,
#                     "kategori": t.kategori_asset,
#                     "subkategori_id": t.subkategori_id_asset,
#                     "subkategori_nama": t.subkategori_nama_asset,
#                     "jenis_asset": t.jenis_asset,
#                     "lokasi_asset": t.lokasi_asset,
#                     "opd_id_asset": t.opd_id_asset,
#                 },
#                 "files": [
#                     {
#                         "attachment_id": str(a.attachment_id),
#                         "file_path": a.file_path,
#                         "uploaded_at": a.uploaded_at
#                     }
#                     for a in attachments
#                 ]
#             }
#             for t in tickets
#         ]
#     }


# @router.get("/tickets/teknisi/{ticket_id}")
# def get_ticket_detail_for_teknisi(
#     ticket_id: str,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):
#     if current_user.get("role_name") != "teknisi":
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: hanya teknisi yang dapat mengakses detail tiket."
#         )

#     teknisi_opd_id = current_user.get("dinas_id")
#     teknisi_user_id = current_user.get("id")

#     if not teknisi_opd_id:
#         raise HTTPException(
#             status_code=400,
#             detail="User tidak memiliki OPD"
#         )

#     ticket = (
#         db.query(models.Tickets)
#         .filter(models.Tickets.ticket_id == ticket_id)
#         .first()
#     )

#     if not ticket:
#         raise HTTPException(status_code=404, detail="Ticket tidak ditemukan")

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

#     allowed_status = ["assigned to teknisi"]
#     if ticket.status not in allowed_status:
#         raise HTTPException(
#             status_code=403,
#             detail="Tiket ini belum siap dikerjakan atau statusnya tidak valid untuk teknisi."
#         )

#     attachments = ticket.attachments if hasattr(ticket, "attachments") else []

#     return {
#         "ticket_id": str(ticket.ticket_id),
#         "ticket_code": ticket.ticket_code,
#         "title": ticket.title,
#         "description": ticket.description,
#         "priority": ticket.priority,
#         "status": ticket.status,
#         "created_at": ticket.created_at,
#         "lokasi_kejadian": ticket.lokasi_kejadian,
#         "pengerjaan_awal": ticket.pengerjaan_awal,
#         "pengerjaan_akhir": ticket.pengerjaan_akhir,
#         "expected_resolution": ticket.expected_resolution,

#         "status_ticket_pengguna": ticket.status_ticket_pengguna,
#         "status_ticket_seksi": ticket.status_ticket_seksi,
#         "status_ticket_teknisi": ticket.status_ticket_teknisi,

#         "creator": {
#             "user_id": str(ticket.creates_id) if ticket.creates_id else None,
#             "full_name": ticket.creates_user.full_name if ticket.creates_user else None,
#             "email": ticket.creates_user.email if ticket.creates_user else None,
#             "profile": ticket.creates_user.profile_url if ticket.creates_user else None,
#         },

#         "asset": {
#             "asset_id": ticket.asset_id,
#             "nama_asset": ticket.nama_asset,
#             "kode_bmd": ticket.kode_bmd_asset,
#             "nomor_seri": ticket.nomor_seri_asset,
#             "kategori": ticket.kategori_asset,
#             "subkategori_id": ticket.subkategori_id_asset,
#             "subkategori_nama": ticket.subkategori_nama_asset,
#             "jenis_asset": ticket.jenis_asset,
#             "lokasi_asset": ticket.lokasi_asset,
#             "opd_id_asset": ticket.opd_id_asset,
#         },

#         "files": [
#             {
#                 "attachment_id": str(a.attachment_id),
#                 "file_path": a.file_path,
#                 "uploaded_at": a.uploaded_at,
#             }
#             for a in attachments
#         ]
#     }


# @router.put("/tickets/teknisi/{ticket_id}/process")
# def teknisi_start_processing(
#     ticket_id: str,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
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

#     return {
#         "message": "Tiket berhasil diperbarui menjadi diproses oleh teknisi.",
#         "ticket_id": str(ticket.ticket_id),
#         "status": ticket.status,
#         "status_ticket_pengguna": ticket.status_ticket_pengguna,
#         "status_ticket_seksi": ticket.status_ticket_seksi,
#         "status_ticket_teknisi": ticket.status_ticket_teknisi,
#         "pengerjaan_awal": ticket.pengerjaan_awal
#     }


# @router.put("/tickets/teknisi/{ticket_id}/complete")
# def teknisi_complete_ticket(
#     ticket_id: str,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
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

#     return {
#         "message": "Tiket berhasil diselesaikan oleh teknisi.",
#         "ticket_id": str(ticket.ticket_id),
#         "status": ticket.status,
#         "status_ticket_pengguna": ticket.status_ticket_pengguna,
#         "status_ticket_seksi": ticket.status_ticket_seksi,
#         "status_ticket_teknisi": ticket.status_ticket_teknisi,
#         "pengerjaan_akhir_teknisi": ticket.pengerjaan_akhir_teknisi
#     }

# @router.get("/teknisi/ratings")
# def get_ratings_for_teknisi(
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):

#     if current_user.get("role_name") != "teknisi":
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: hanya seksi yang dapat melihat data rating."
#         )

#     teknisi_id = current_user.get("id")
#     opd_id_user = current_user.get("dinas_id")

#     tickets = (
#         db.query(models.Tickets)
#         .filter(
#             models.Tickets.assigned_teknisi_id == teknisi_id,
#             models.Tickets.opd_id_tickets == opd_id_user
#         )
#         .order_by(models.Tickets.created_at.desc())
#         .all()
#     )

#     results = []
#     for t in tickets:

#         rating = (
#             db.query(models.TicketRatings)
#             .filter(models.TicketRatings.ticket_id == t.ticket_id)
#             .first()
#         )

#         if not rating:
#             continue

#         attachments = t.attachments if hasattr(t, "attachments") else []

#         results.append({
#             "ticket_id": str(t.ticket_id),
#             "ticket_code": t.ticket_code,
#             "title": t.title,
#             "status": t.status,
#             "verified_seksi_id": t.verified_seksi_id,
#             "assigned_teknisi_id": t.assigned_teknisi_id,
#             "opd_id": t.opd_id_tickets,

#             "rating": rating.rating if rating else None,
#             "comment": rating.comment if rating else None,
#             "rated_at": rating.created_at if rating else None,

#             "description": t.description,
#             "priority": t.priority,
#             "lokasi_kejadian": t.lokasi_kejadian,
#             "expected_resolution": t.expected_resolution,
#             "pengerjaan_awal": t.pengerjaan_awal,
#             "pengerjaan_akhir": t.pengerjaan_akhir,
#             "pengerjaan_awal_teknisi": t.pengerjaan_awal_teknisi,
#             "pengerjaan_akhir_teknisi": t.pengerjaan_akhir_teknisi,

#             "creator": {
#                 "user_id": str(t.creates_id) if t.creates_id else None,
#                 "full_name": t.creates_user.full_name if t.creates_user else None,
#                 "profile": t.creates_user.profile_url if t.creates_user else None,
#                 "email": t.creates_user.email if t.creates_user else None,
#             },

#             "asset": {
#                 "asset_id": t.asset_id,
#                 "nama_asset": t.nama_asset,
#                 "kode_bmd": t.kode_bmd_asset,
#                 "nomor_seri": t.nomor_seri_asset,
#                 "kategori": t.kategori_asset,
#                 "subkategori_id": t.subkategori_id_asset,
#                 "subkategori_nama": t.subkategori_nama_asset,
#                 "jenis_asset": t.jenis_asset,
#                 "lokasi_asset": t.lokasi_asset,
#                 "opd_id_asset": t.opd_id_asset,
#             },

#             "files": [
#                 {
#                     "attachment_id": str(a.attachment_id),
#                     "file_path": a.file_path,
#                     "uploaded_at": a.uploaded_at
#                 }
#                 for a in attachments
#             ]
#         })

#     return {
#         "total": len(results),
#         "data": results
#     }


# @router.get("/teknisi/ratings/{ticket_id}")
# def get_rating_detail_for_teknisi(
#     ticket_id: str,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user_masyarakat)
# ):

#     if current_user.get("role_name") != "teknisi":
#         raise HTTPException(
#             status_code=403,
#             detail="Akses ditolak: hanya seksi yang dapat melihat data rating."
#         )

#     teknisi_id = current_user.get("id")
#     opd_id_user = current_user.get("dinas_id")

#     ticket = (
#         db.query(models.Tickets)
#         .filter(
#             models.Tickets.ticket_id == ticket_id,
#             models.Tickets.assigned_teknisi_id == teknisi_id,
#             models.Tickets.opd_id_tickets == opd_id_user
#         )
#         .first()
#     )

#     if not ticket:
#         raise HTTPException(
#             status_code=404,
#             detail="Tiket tidak ditemukan atau Anda tidak memiliki akses."
#         )

#     rating = (
#         db.query(models.TicketRatings)
#         .filter(models.TicketRatings.ticket_id == ticket.ticket_id)
#         .first()
#     )

#     if not rating:
#         return {
#             "ticket_id": str(ticket.ticket_id),
#             "ticket_code": ticket.ticket_code,
#             "rating": None,
#             "comment": None,
#             "rated_at": None
#         }


#     attachments = ticket.attachments if hasattr(ticket, "attachments") else []

#     return {
#         "ticket_id": str(ticket.ticket_id),
#         "ticket_code": ticket.ticket_code,
#         "title": ticket.title,
#         "status": ticket.status,
#         "verified_seksi_id": ticket.verified_seksi_id,
#         "assigned_teknisi_id": ticket.assigned_teknisi_id,
#         "opd_id": ticket.opd_id_tickets,

#         "rating": rating.rating if rating else None,
#         "comment": rating.comment if rating else None,
#         "rated_at": rating.created_at if rating else None,

#         "description": ticket.description,
#         "priority": ticket.priority,
#         "lokasi_kejadian": ticket.lokasi_kejadian,
#         "expected_resolution": ticket.expected_resolution,
#         "pengerjaan_awal": ticket.pengerjaan_awal,
#         "pengerjaan_akhir": ticket.pengerjaan_akhir,
#         "pengerjaan_awal_teknisi": ticket.pengerjaan_awal_teknisi,
#         "pengerjaan_akhir_teknisi": ticket.pengerjaan_akhir_teknisi,

#         "creator": {
#             "user_id": str(ticket.creates_id) if ticket.creates_id else None,
#             "full_name": ticket.creates_user.full_name if ticket.creates_user else None,
#             "profile": ticket.creates_user.profile_url if ticket.creates_user else None,
#             "email": ticket.creates_user.email if ticket.creates_user else None,
#         },

#         "asset": {
#             "asset_id": ticket.asset_id,
#             "nama_asset": ticket.nama_asset,
#             "kode_bmd": ticket.kode_bmd_asset,
#             "nomor_seri": ticket.nomor_seri_asset,
#             "kategori": ticket.kategori_asset,
#             "subkategori_id": ticket.subkategori_id_asset,
#             "subkategori_nama": ticket.subkategori_nama_asset,
#             "jenis_asset": ticket.jenis_asset,
#             "lokasi_asset": ticket.lokasi_asset,
#             "opd_id_asset": ticket.opd_id_asset,
#         },

#         "files": [
#             {
#                 "attachment_id": str(a.attachment_id),
#                 "file_path": a.file_path,
#                 "uploaded_at": a.uploaded_at
#             }
#             for a in attachments
#         ]
#     }









# #BIDANG
# @router.get("/tickets/bidang/verified")
# def get_verified_tickets_for_bidang(
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user)
# ):

#     if current_user.get("role_name") != "bidang":
#         raise HTTPException(
#             403,
#             "Akses ditolak: hanya admin bidang yang dapat melihat tiket yang diverifikasi oleh seksi"
#         )

#     opd_id = current_user.get("dinas_id")
#     if not opd_id:
#         raise HTTPException(
#             400,
#             "Akun bidang tidak memiliki dinas_id, hubungi admin sistem."
#         )

#     tickets = (
#         db.query(models.Tickets)
#         .filter(
#             models.Tickets.status == "verified by seksi",
#             models.Tickets.priority.isnot(None),
#             models.Tickets.opd_id_tickets == opd_id
#         )
#         .order_by(models.Tickets.created_at.desc())
#         .all()
#     )

#     results = []

#     for ticket in tickets:

#         attachments = ticket.attachments if hasattr(ticket, "attachments") else []

#         results.append({
#             "ticket_id": str(ticket.ticket_id),
#             "ticket_code": ticket.ticket_code,
#             "title": ticket.title,
#             "status": ticket.status,
#             "created_at": ticket.created_at,
#             "updated_at": ticket.updated_at,
#             "priority": ticket.priority,
#             "opd_id_tickets": ticket.opd_id_tickets,
#             "ticket_source": ticket.ticket_source,

#             "creator": {
#                 "user_id": str(ticket.creates_id) if ticket.creates_id else None,
#                 "full_name": ticket.creates_user.full_name if ticket.creates_user else None,
#                 "profile": ticket.creates_user.profile_url if ticket.creates_user else None,
#                 "email": ticket.creates_user.email if ticket.creates_user else None,
#             },

#             "asset": {
#                 "asset_id": ticket.asset_id,
#                 "nama_asset": ticket.nama_asset,
#                 "kode_bmd": ticket.kode_bmd_asset,
#                 "nomor_seri": ticket.nomor_seri_asset,
#             },

#             "files": [
#                 {
#                     "attachment_id": str(a.attachment_id),
#                     "file_path": a.file_path,
#                     "uploaded_at": a.uploaded_at
#                 }
#                 for a in attachments
#             ]
#         })

#     return {
#         "message": "Daftar tiket yang sudah diverifikasi oleh seksi",
#         "total": len(results),
#         "data": results
#     }



# @router.get("/tickets/bidang/{ticket_id}")
# def get_ticket_detail_bidang(
#     ticket_id: str,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user)
# ):

#     if current_user.get("role_name") != "bidang":
#         raise HTTPException(
#             403,
#             "Akses ditolak: hanya admin bidang"
#         )

#     opd_id = current_user.get("dinas_id")
#     if not opd_id:
#         raise HTTPException(
#             400,
#             "Akun bidang tidak memiliki OPD ID"
#         )

#     ticket = (
#         db.query(models.Tickets)
#         .filter(
#             models.Tickets.ticket_id == ticket_id,
#             models.Tickets.opd_id_tickets == opd_id,
#             models.Tickets.status == "verified by seksi"
#         )
#         .first()
#     )


#     if not ticket:
#         raise HTTPException(404, "Tiket tidak ditemukan, belum diverifikasi seksi atau bukan dari OPD Anda")

#     attachments = (
#         db.query(models.TicketAttachment)
#         .filter(models.TicketAttachment.has_id == ticket_id)
#         .all()
#     )

#     response = {
#         "ticket_id": str(ticket.ticket_id),
#         "ticket_code": ticket.ticket_code,
#         "title": ticket.title,
#         "description": ticket.description,
#         "status": ticket.status,
#         # "stage": ticket.ticket_stage,
#         "created_at": ticket.created_at,
#         "priority": ticket.priority,

#         "opd_id_tickets": ticket.opd_id_tickets,
#         "lokasi_kejadian": ticket.lokasi_kejadian,
#         "expected_resolution": ticket.expected_resolution,
#         "ticket_source": ticket.ticket_source,
#         "status_ticket_pengguna": ticket.status_ticket_pengguna,
#         "status_ticket_seksi": ticket.status_ticket_seksi,

#         "creator": {
#             "user_id": str(ticket.creates_id) if ticket.creates_id else None,
#             "full_name": ticket.creates_user.full_name if ticket.creates_user else None,
#             "profile": ticket.creates_user.profile_url if ticket.creates_user else None,
#             "email": ticket.creates_user.email if ticket.creates_user else None,
#         },

#         "asset": {
#             "asset_id": ticket.asset_id,
#             "nama_asset": ticket.nama_asset,
#             "kode_bmd": ticket.kode_bmd_asset,
#             "nomor_seri": ticket.nomor_seri_asset,
#             "kategori": ticket.kategori_asset,
#             "subkategori_id": ticket.subkategori_id_asset,
#             "subkategori_nama": ticket.subkategori_nama_asset,
#             "jenis_asset": ticket.jenis_asset,
#             "lokasi_asset": ticket.lokasi_asset,
#             "opd_id_asset": ticket.opd_id_asset,
#         },

#         "files": [
#             {
#                 "attachment_id": str(a.attachment_id),
#                 "file_path": a.file_path,
#                 "uploaded_at": a.uploaded_at
#             }
#             for a in attachments
#         ]
#     }

#     return {
#         "message": "Detail tiket untuk bidang",
#         "data": response
#     }


# @router.patch("/tickets/bidang/verify/{ticket_id}")
# def verify_by_bidang(
#     ticket_id: str,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user)
# ):

#     if current_user.get("role_name") != "bidang":
#         raise HTTPException(403, "Akses ditolak: hanya admin bidang")

#     opd_id = current_user.get("dinas_id")

#     ticket = (
#         db.query(models.Tickets)
#         .filter(
#             models.Tickets.ticket_id == ticket_id,
#             models.Tickets.opd_id_tickets == opd_id,
#             models.Tickets.status == "verified by seksi"
#         )
#         .first()
#     )

#     if not ticket:
#         raise HTTPException(404, "Tiket tidak valid untuk diverifikasi bidang")

#     ticket.status = "verified by bidang"
#     ticket.ticket_stage = "verified-bidang"
#     ticket.status_ticket_seksi = "Draft"
#     ticket.updated_at = datetime.utcnow()

#     db.commit()

#     return {"message": "Tiket berhasil diverifikasi oleh bidang"}



# @router.patch("/tickets/bidang/reject/{ticket_id}")
# def reject_by_bidang(
#     ticket_id: str,
#     payload: RejectReasonBidang,
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user)
# ):

#     if current_user.get("role_name") != "bidang":
#         raise HTTPException(403, "Akses ditolak: hanya admin bidang")

#     opd_id = current_user.get("dinas_id")

#     ticket = (
#         db.query(models.Tickets)
#         .filter(
#             models.Tickets.ticket_id == ticket_id,
#             models.Tickets.opd_id_tickets == opd_id,
#             models.Tickets.status == "verified by seksi"
#         )
#         .first()
#     )

#     if not ticket:
#         raise HTTPException(404, "Tiket tidak valid untuk direject bidang")

#     ticket.status = "rejected by bidang"
#     ticket.ticket_stage = "revisi-seksi"
#     ticket.status_ticket_seksi = "revisi"
#     ticket.rejection_reason_bidang = payload.reason
#     ticket.updated_at = datetime.utcnow()

#     db.commit()
#     db.refresh(ticket)

#     return {"message": "Tiket berhasil ditolak oleh bidang", "reason": payload.reason}
















# @router.get("/tickets/bidang/verified")
# def get_verified_tickets_for_bidang(
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user)
# ):

#     # Hanya role 'admin bidang'
#     if current_user.get("role_name") != "bidang":
#         raise HTTPException(
#             403,
#             "Akses ditolak: hanya admin bidang yang dapat melihat tiket yang sudah diverifikasi seksi"
#         )

#     opd_id = current_user.get("dinas_id")
#     if not opd_id:
#         raise HTTPException(
#             400,
#             "Akun bidang tidak memiliki OPD ID, hubungi admin sistem."
#         )

#     # Ambil semua tiket yang sudah diverifikasi seksi untuk OPD yang sama
#     tickets = (
#         db.query(models.Tickets)
#         .filter(
#             models.Tickets.status == "verified by seksi",
#             models.Tickets.priority.isnot(None),
#             models.Tickets.opd_id_tickets == opd_id
#         )
#         .order_by(models.Tickets.created_at.desc())
#         .all()
#     )

#     # Format response: ticket_id dan ticket_code di atas
#     formatted_tickets = []
#     for t in tickets:
#         t_dict = t.__dict__.copy()
#         t_dict.pop("_sa_instance_state", None)

#         formatted = {
#             "ticket_id": t.ticket_id,
#             "ticket_code": t.ticket_code,
#             **t_dict
#         }

#         formatted_tickets.append(formatted)

#     return {
#         "message": "Daftar tiket yang sudah diverifikasi oleh seksi",
#         "total": len(formatted_tickets),
#         "data": formatted_tickets
#     }
















# @router.post("/pelaporan-online")
# async def create_public_report(
#     opd_id: str = Form(...),
#     category_id: str = Form(...),
#     description: str = Form(...),
#     action: str = Form("submit"),
#     files: Optional[List[UploadFile]] = File(None),
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user)
# ):
#     roles = current_user.get("roles", [])
#     allowed_roles = {"masyarakat", "pegawai"}
#     if not any(role in allowed_roles for role in roles):
#         raise HTTPException(status_code=403, detail="Unauthorized: hanya masyarakat atau pegawai yang dapat membuat laporan")


#     opd_exists = db.execute(text("SELECT 1 FROM opd WHERE opd_id = :id"), {"id": opd_id}).first()
#     category_exists = db.execute(text("SELECT 1 FROM ticket_categories WHERE category_id = :id"), {"id": category_id}).first()

#     if not opd_exists or not category_exists:
#         raise HTTPException(status_code=404, detail="Invalid OPD atau kategori ID")

#     action_lower = action.lower()
#     if "masyarakat" in roles:
#         if action_lower == "draft":
#             status_val = "Draft"
#             stage_val = "user_draft"
#         elif action_lower == "submit":
#             status_val = "Open"
#             stage_val = "user_submit"
#         else:
#             raise HTTPException(status_code=400, detail="Aksi tidak valid. Gunakan 'draft' atau 'submit'.")
#     else:
#         status_val = "Open"
#         stage_val = "user_submit"

#     new_ticket = Tickets(
#         ticket_id=uuid4(),
#         description=description,
#         status=status_val,
#         opd_id=UUID(opd_id),
#         category_id=UUID(category_id),
#         creates_id=UUID(current_user["id"]),
#         ticket_source="pegawai" if "pegawai" in roles else "masyarakat",
#         ticket_stage=stage_val,
#         created_at=datetime.utcnow()
#     )

#     db.add(new_ticket)
#     db.commit()
#     db.refresh(new_ticket)

#     uploaded_files = [] 

#     if files:
#         for file in files:
#             try:
#                 file_ext = os.path.splitext(file.filename)[1]
#                 file_name = f"{new_ticket.ticket_id}_{uuid4()}{file_ext}"

#                 content_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
#                 file_bytes = await file.read()

#                 res = supabase.storage.from_("docs").upload(
#                     file_name,
#                     file_bytes,
#                     {"content-type": content_type}
#                 )

#                 if hasattr(res, "error") and res.error:
#                     raise Exception(res.error.message)
#                 if isinstance(res, dict) and res.get("error"):
#                     raise Exception(res["error"])

#                 file_url = supabase.storage.from_("docs").get_public_url(file_name)
#                 if not isinstance(file_url, str):
#                     file_url = None

#                 new_attachment = TicketAttachment(
#                     attachment_id=uuid4(),
#                     has_id=new_ticket.ticket_id,
#                     uploaded_at=datetime.utcnow(),
#                     file_path=file_url
#                 )
#                 db.add(new_attachment)
#                 db.commit()

#                 uploaded_files.append(file_url)

#             except Exception as e:
#                 raise HTTPException(status_code=500, detail=f"Gagal upload file {file.filename}: {str(e)}")

#     if "masyarakat" in roles and action_lower == "draft":
#         message = "Laporan disimpan sebagai draft. Anda dapat mengirimkannya nanti."
#     elif "masyarakat" in roles and action_lower == "submit":
#         message = "Laporan berhasil dikirim dan menunggu verifikasi dari seksi."
#     else:
#         message = "Laporan pegawai berhasil dibuat dan dikirim."

#     return {
#         "message": message,
#         "ticket_id": str(new_ticket.ticket_id),
#         "status": new_ticket.status,
#         "ticket_stage": new_ticket.ticket_stage,
#         "uploaded_files": uploaded_files 
#     }





# @router.get("/pelaporan-online/draft")
async def get_user_drafts(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    roles = current_user.get("roles", [])
    if "masyarakat" not in roles:
        raise HTTPException(status_code=403, detail="Unauthorized: Only masyarakat can access drafts")

    user_id = current_user["id"]

    drafts = db.execute(
        text("""
            SELECT ticket_id, description, additional_info, opd_id, category_id, status, ticket_stage, created_at
            FROM tickets
            WHERE creates_id = :user_id
              AND status = 'Draft'
              AND ticket_stage = 'user_draft'
            ORDER BY created_at DESC
        """),
        {"user_id": user_id}
    ).mappings().all()

    return {"drafts": [dict(row) for row in drafts]}



# @router.put("/pelaporan-online/submit/{ticket_id}")
async def submit_draft_ticket(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    roles = current_user.get("roles", [])
    if "masyarakat" not in roles:
        raise HTTPException(status_code=403, detail="Unauthorized: Only masyarakat can submit tickets")

    ticket = db.execute(
        text("""
            SELECT * FROM tickets
            WHERE ticket_id = :ticket_id
              AND creates_id = :user_id
        """),
        {"ticket_id": str(ticket_id), "user_id": current_user["id"]}
    ).mappings().first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Tiket tidak ditemukan atau bukan milik Anda")

    if ticket["status"] != "Draft" or ticket["ticket_stage"] != "user_draft":
        raise HTTPException(status_code=400, detail="Tiket ini sudah dikirim atau bukan draft")

    missing_fields = []
    if not ticket["description"]:
        missing_fields.append("description")
    if not ticket["category_id"]:
        missing_fields.append("category_id")
    if not ticket["opd_id"]:
        missing_fields.append("opd_id")

    if missing_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Tiket belum lengkap. Harap isi kolom: {', '.join(missing_fields)}"
        )

    db.execute(
        text("""
            UPDATE tickets
            SET status = 'Open',
                ticket_stage = 'user_submit',
                updated_at = NOW()
            WHERE ticket_id = :ticket_id
        """),
        {"ticket_id": str(ticket_id)}
    )
    db.commit()

    return {"message": "Tiket berhasil dikirim dari draft", "ticket_id": str(ticket_id)}


# @router.get("/ticket-categories", response_model=list[TicketCategorySchema])
async def get_ticket_categories(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    opd_id = current_user.get("opd_id")

    if not opd_id:
        raise HTTPException(status_code=400, detail="Invalid token: opd_id missing")

    categories = db.query(TicketCategories).filter(TicketCategories.opd_id == opd_id).all()

    return categories




# @router.post("/pengajuan-pelayanan")
async def create_ticket_pegawai_JANGAN_DIPAKE_DULU(
    request_type: str = Form(...),             
    description: str = Form(...),
    additional_info: str = Form(None),
    opd_id: str = Form(...),
    creates_id: str = Form(...),
    priority: str = Form("Medium"),
    file: UploadFile = None
):
    try:
        file_path = None
        if file:
            ext = os.path.splitext(file.filename)[1]
            filename = f"{uuid.uuid4()}{ext}"
            full_path = f"pegawai/{filename}"

            res = supabase.storage.from_(BUCKET_NAME).upload(
                full_path, await file.read(), {"content-type": file.content_type}
            )

            if res.get("error"):
                raise HTTPException(status_code=500, detail=f"File upload failed: {res['error']['message']}")

            file_path = f"{BUCKET_NAME}/{full_path}"

        new_ticket = {
            "title": request_type.replace("_", " ").title(),
            "description": description,
            "priority": priority,
            "status": "Open",
            "ticket_source": "pegawai",
            "request_type": request_type,
            "creates_id": creates_id,
            "opd_id": opd_id,
            "additional_info": additional_info,
            "created_at": datetime.utcnow().isoformat()
        }

        ticket_res = supabase.table("tickets").insert(new_ticket).execute()
        if not ticket_res.data:
            raise HTTPException(status_code=500, detail="Ticket creation failed")

        ticket_id = ticket_res.data[0]["ticket_id"]

        if file_path:
            supabase.table("ticket_attachment").insert({
                "uploaded_at": datetime.utcnow().isoformat(),
                "file_path": file_path,
                "has_id": ticket_id
            }).execute()

        return {
            "ticket_id": ticket_id,
            "message": "Ticket created successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



#SEKSI
# @router.get("/tickets/seksi", response_model=list[TicketForSeksiSchema])
async def get_tickets_for_seksi(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    roles = current_user.get("roles", [])
    if "seksi" not in roles:
        raise HTTPException(status_code=403, detail="Access denied: only seksi can view this data")

    opd_id = current_user.get("opd_id")
    if not opd_id:
        raise HTTPException(status_code=400, detail="Invalid token: opd_id missing")

    tickets = (
        db.query(Tickets)
        .filter(
            Tickets.opd_id == opd_id,
            Tickets.status != "Draft"
        )
        .all()
    )

    return tickets

# @router.get("/tickets/seksi/{ticket_id}", response_model=TicketForSeksiSchema)
async def get_ticket_detail_seksi_temp(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_masyarakat)
):
    if "seksi" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Access denied: only seksi can view this data")

    opd_id = current_user.get("opd_id")

    ticket = (
        db.query(Tickets)
        .filter(Tickets.ticket_id == ticket_id, Tickets.opd_id == opd_id)
        .first()
    )

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found or access denied")

    return ticket


# @router.post("/tickets/seksi/verify/{ticket_id}")
async def verify_ticket_seksi(
    ticket_id: str,
    priority: str = Form(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if "seksi" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Access denied: only seksi can verify tickets")

    if priority not in PRIORITY_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid priority, must be one of {PRIORITY_OPTIONS}")

    opd_id = current_user.get("opd_id")
    ticket = db.query(Tickets).filter(Tickets.ticket_id == ticket_id, Tickets.opd_id == opd_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found or access denied")

    ticket.priority = priority
    ticket.status = "Verified by Seksi"
    ticket.updated_at = datetime.utcnow()
    db.add(ticket)

    update = TicketUpdates(
        status_change=ticket.status,
        notes=f"Verified by Seksi with priority {priority}",
        update_time=datetime.utcnow(),
        has_calendar_id=ticket.opd_id,
        makes_by_id=current_user["id"],
        ticket_id=ticket.ticket_id
    )
    db.add(update)
    db.commit()

    return {
        "message": f"Ticket {ticket_id} verified successfully",
        "ticket_id": ticket_id,
        "status": ticket.status,
        "priority": ticket.priority
    }



# Tracking tiket
# @router.get(
#     "/track/{ticket_id}",
#     tags=["tickets"],
#     summary="Track Ticket Status",
#     response_model=schemas.TicketTrackResponse
# )
async def track_ticket(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user) 
):
    ticket = (
        db.query(Tickets)
        .join(TicketCategories, Tickets.category_id == TicketCategories.category_id)
        .join(Opd, Tickets.opd_id == Opd.opd_id)
        .filter(Tickets.ticket_id == ticket_id)
        .first()
    )

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return schemas.TicketTrackResponse(
        ticket_id=ticket.ticket_id,
        status=ticket.status,
        jenis_laporan=ticket.category.category_name if ticket.category else None,
        opd=ticket.opd.opd_name if ticket.opd else None,
    )