from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from auth import database
from . import models, schemas
from auth.models import Roles, UserRoles, Opd
import auth.models as models
from auth.auth import get_current_user

router = APIRouter(prefix="/opd", tags=["opd"])

@router.post("/", response_model=schemas.OPDResponse)
async def create_opd(
    data: schemas.OPDCreate,
    db: Session = Depends(database.get_db),
    current_user: dict = Depends(get_current_user)
):
    if "admin_kota" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to create OPD."
        )

    existing_opd = db.query(models.Opd).filter(models.Opd.opd_name == data.opd_name).first()
    if existing_opd:
        raise HTTPException(status_code=400, detail="OPD name already exists")

    new_opd = models.Opd(opd_name=data.opd_name, description=data.description)
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
