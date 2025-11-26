from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import Optional
from auth import database
from uuid import uuid4
import os
import mimetypes
from datetime import datetime
from supabase import create_client
from sqlalchemy import text
from . import models, schemas
from auth.models import Roles, UserRoles, Opd
import auth.models as models
from auth.auth import get_current_user
import aiohttp

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

router = APIRouter(prefix="/opd", tags=["opd"])

@router.post("/", response_model=schemas.OPDResponse)
async def create_opd(
    opd_name: str = Form(...),
    description: str = Form(None),
    file: UploadFile = File(None),
    db: Session = Depends(database.get_db),
    current_user: dict = Depends(get_current_user)
):
    if "admin_kota" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to create OPD."
        )

    existing_opd = db.query(models.Opd).filter(models.Opd.opd_name == opd_name).first()
    if existing_opd:
        raise HTTPException(status_code=400, detail="OPD name already exists")

    file_url = None

    if file:
        try:
            file_ext = os.path.splitext(file.filename)[1]
            file_name = f"{uuid4()}{file_ext}"

            content_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
            file_bytes = await file.read()

            res = supabase.storage.from_("opd_icon").upload(
                file_name,
                file_bytes,
                {"content-type": content_type}
            )

            if hasattr(res, "error") and res.error:
                raise Exception(res.error.message)
            if isinstance(res, dict) and res.get("error"):
                raise Exception(res["error"])

            file_url = supabase.storage.from_("opd_icon").get_public_url(file_name)
            if not isinstance(file_url, str):
                file_url = None

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Icon upload failed: {str(e)}")

    new_opd = models.Opd(
        opd_name=opd_name,
        description=description,
        file_path=file_url
    )

    db.add(new_opd)
    db.commit()
    db.refresh(new_opd)

    return new_opd


# @router.get("/", response_model=list[schemas.OPDResponse])
# async def get_all_opd(
#     current_user: dict = Depends(get_current_user),
#     db: Session = Depends(database.get_db)
# ):
#     opd_list = db.query(models.Opd).all()

#     if not opd_list:
#         raise HTTPException(status_code=404, detail="No OPD data found")

#     return opd_list

@router.get("/", response_model=list[schemas.OPDResponse])
async def get_all_opd(
    db: Session = Depends(database.get_db)
):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://arise-app.my.id/api/dinas") as res:
            if res.status != 200:
                err = await res.text()
                raise HTTPException(500, f"Gagal ambil OPD dari ASET: {err}")

            aset_data = await res.json()

    # ambil icon lokal dari DB
    local_opds = db.query(models.Opd).all()
    local_map = {o.id_aset: o for o in local_opds}

    final_result = []
    for opd in aset_data["data"]:
        aset_id = opd["id"]
        local = local_map.get(aset_id)

        final_result.append({
            "opd_id": str(local.opd_id) if local else None,
            "id_aset": opd["id"],
            "opd_name": opd["nama"],
            "file_path": local.file_path if local else None,
            "description": local.description if local else None,
        })

    return final_result



@router.post("/opd/{id_aset}/icon", response_model=schemas.OPDResponse)
async def upload_icon_opd(
    id_aset: int,
    description: str = Form(None),
    file: UploadFile = File(None),
    db: Session = Depends(database.get_db),
    current_user: dict = Depends(get_current_user),
):
    token = current_user["token"]

    # 1. Ambil data OPD dari ASET
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://arise-app.my.id/api/dinas/{id_aset}",
            headers={"Authorization": f"Bearer {token}"}
        ) as res:
            if res.status != 200:
                err = await res.text()
                raise HTTPException(400, f"ID ASET tidak ditemukan: {err}")

            opd_aset = await res.json()

    opd_name = opd_aset["data"]["nama"]

    # 2. Cek database lokal
    opd = db.query(models.Opd).filter(models.Opd.id_aset == id_aset).first()

    # 3. Upload icon ke Supabase
    file_url = None
    if file:
        file_ext = os.path.splitext(file.filename)[1]
        file_name = f"{uuid4()}{file_ext}"
        file_bytes = await file.read()

        supabase.storage.from_("opd_icon").upload(file_name, file_bytes)
        file_url = supabase.storage.from_("opd_icon").get_public_url(file_name)

    # 4. Insert/update DB lokal
    if not opd:
        opd = models.Opd(
            id_aset=id_aset,
            opd_name=opd_name,
            file_path=file_url,
            description=description
        )
        db.add(opd)
    else:
        opd.opd_name = opd_name
        opd.file_path = file_url or opd.file_path
        opd.description = description or opd.description

    db.commit()
    db.refresh(opd)

    return opd




@router.put("/opd/{id_aset}/icon", response_model=schemas.OPDResponse)
async def update_icon_opd(
    id_aset: int,
    description: Optional[str] = Form(None),
    file: UploadFile = File(None),
    db: Session = Depends(database.get_db),
    current_user: dict = Depends(get_current_user)
):
    token = current_user["token"]

    # --- 1. Ambil data OPD dari API ASET ---
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://arise-app.my.id/api/dinas/{id_aset}",
            headers={"Authorization": f"Bearer {token}"}
        ) as res:
            if res.status != 200:
                err = await res.text()
                raise HTTPException(400, f"ID ASET tidak ditemukan: {err}")

            opd_aset = await res.json()

    opd_name = opd_aset["data"]["nama"]

    # --- 2. Cek database lokal ---
    opd = db.query(models.Opd).filter(models.Opd.id_aset == id_aset).first()
    if not opd:
        raise HTTPException(
            status_code=404, 
            detail="OPD belum pernah dibuat. Gunakan endpoint POST /opd/{id_aset}/icon terlebih dahulu."
        )

    # --- 3. Upload ikon baru ---
    file_url = opd.file_path  # default: pakai yg lama
    if file:
        try:
            # hapus icon lama jika ada
            if opd.file_path:
                old_filename = opd.file_path.split("/")[-1]
                supabase.storage.from_("opd_icon").remove([old_filename])

            file_ext = os.path.splitext(file.filename)[1]
            file_name = f"{uuid4()}{file_ext}"

            file_bytes = await file.read()

            supabase.storage.from_("opd_icon").upload(file_name, file_bytes)
            file_url = supabase.storage.from_("opd_icon").get_public_url(file_name)

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Icon upload failed: {str(e)}")

    # --- 4. Update DB lokal ---
    opd.opd_name = opd_name
    opd.description = description or opd.description
    opd.file_path = file_url

    db.commit()
    db.refresh(opd)

    return opd




@router.delete("/{opd_id}", status_code=status.HTTP_200_OK)
async def delete_opd(
    opd_id: str,
    db: Session = Depends(database.get_db),
    current_user: dict = Depends(get_current_user)
):
    if "admin_kota" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete OPD."
        )

    opd = db.query(models.Opd).filter(models.Opd.opd_id == opd_id).first()
    if not opd:
        raise HTTPException(status_code=404, detail="OPD not found")

    db.delete(opd)
    db.commit()
    return {"detail": "OPD deleted successfully"}
