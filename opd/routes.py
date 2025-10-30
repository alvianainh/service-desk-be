from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlalchemy.orm import Session
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


@router.get("/", response_model=list[schemas.OPDResponse])
async def get_all_opd(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    opd_list = db.query(models.Opd).all()

    if not opd_list:
        raise HTTPException(status_code=404, detail="No OPD data found")

    return opd_list


@router.put("/{opd_id}", response_model=schemas.OPDResponse)
async def update_opd(
    opd_id: str,
    data: schemas.OPDCreate,
    db: Session = Depends(database.get_db),
    current_user: dict = Depends(get_current_user)
):
    if "admin_kota" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update OPD."
        )

    opd = db.query(models.Opd).filter(models.Opd.opd_id == opd_id).first()
    if not opd:
        raise HTTPException(status_code=404, detail="OPD not found")

    opd.opd_name = data.opd_name
    opd.description = data.description
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
