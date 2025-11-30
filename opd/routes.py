from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import Optional
from auth import database
from auth.database import get_db
from uuid import uuid4
import os
import mimetypes
from datetime import datetime
from supabase import create_client
from sqlalchemy import text
from . import models, schemas
from auth.models import Roles, Opd, Dinas
import auth.models as models
from auth.auth import get_current_user
import aiohttp

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

router = APIRouter(prefix="/opd", tags=["opd"])


async def sync_dinas_from_asset(db: Session):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://arise-app.my.id/api/dinas",
            headers={"accept": "application/json"}
        ) as resp:
            data = await resp.json()
            dinas_list = data["data"]

            for d in dinas_list:
                db_dinas = db.query(Dinas).filter(Dinas.id == d["id"]).first()

                if db_dinas:
                    db_dinas.nama = d["nama"]
                    db_dinas.created_at = d["created_at"]
                    db_dinas.updated_at = d["updated_at"]
                else:
                    new_dinas = Dinas(
                        id=d["id"],
                        nama=d["nama"],
                        created_at=d["created_at"],
                        updated_at=d["updated_at"],
                        file_path=None  # default, internal only
                    )
                    db.add(new_dinas)

            db.commit()

@router.post("/sync/dinas")
async def sync_dinas_endpoint(db: Session = Depends(get_db)):
    await sync_dinas_from_asset(db)
    return {"message": "Dinas synced successfully"}


@router.get("/dinas")
def get_all_dinas(db: Session = Depends(get_db)):
    dinas = db.query(Dinas).all()
    return {
        "message": "Success",
        "data": dinas
    }



@router.get("/dinas/{id}")
def get_dinas_by_id(id: int, db: Session = Depends(get_db)):
    dinas = db.query(Dinas).filter(Dinas.id == id).first()

    if not dinas:
        raise HTTPException(status_code=404, detail="Dinas not found")

    return {
        "message": "Success",
        "data": dinas
    }


@router.put("/dinas/{id_aset}/icon")
async def update_icon_dinas(
    id_aset: int,
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    token = current_user["token"]

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://arise-app.my.id/api/dinas/{id_aset}",
            headers={"Authorization": f"Bearer {token}"}
        ) as res:
            if res.status != 200:
                err = await res.text()
                raise HTTPException(
                    status_code=400,
                    detail=f"ID Dinas Aset tidak ditemukan: {err}"
                )

            dinas_aset = await res.json()

    nama_dinas = dinas_aset["data"]["nama"]

    dinas = db.query(Dinas).filter(Dinas.id == id_aset).first()

    if not dinas:
        raise HTTPException(
            status_code=404,
            detail="Dinas belum pernah disinkron atau dibuat. Gunakan endpoint sync/dinas lebih dahulu."
        )

    file_url = dinas.file_path 

    if file:
        try:

            if dinas.file_path:
                old_filename = dinas.file_path.split("/")[-1]
                supabase.storage.from_("opd_icon").remove([old_filename])

            ext = os.path.splitext(file.filename)[1]
            new_filename = f"{uuid4()}{ext}"

            file_bytes = await file.read()

            supabase.storage.from_("opd_icon").upload(new_filename, file_bytes)

            file_url = supabase.storage.from_("opd_icon").get_public_url(new_filename)

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Upload icon gagal: {str(e)}"
            )

    dinas.nama = nama_dinas
    dinas.file_path = file_url
    dinas.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(dinas)

    return {
        "message": "Icon Dinas berhasil diupdate",
        "data": {
            "id": dinas.id,
            "nama": dinas.nama,
            "file_path": dinas.file_path
        }
    }



# @router.get("/opd-asset", response_model=list[schemas.OPDResponse])
# async def get_all_opd(
#     db: Session = Depends(database.get_db)
# ):
#     async with aiohttp.ClientSession() as session:
#         async with session.get("https://arise-app.my.id/api/dinas") as res:
#             if res.status != 200:
#                 err = await res.text()
#                 raise HTTPException(500, f"Gagal ambil OPD dari ASET: {err}")

#             aset_data = await res.json()

#     local_opds = db.query(models.Opd).all()
#     local_map = {o.id_aset: o for o in local_opds}

#     final_result = []
#     for opd in aset_data["data"]:
#         aset_id = opd["id"]
#         local = local_map.get(aset_id)

#         final_result.append({
#             "opd_id": str(local.opd_id) if local else None,
#             "id_aset": opd["id"],
#             "opd_name": opd["nama"],
#             "file_path": local.file_path if local else None,
#             "description": local.description if local else None,
#         })

#     return final_result

