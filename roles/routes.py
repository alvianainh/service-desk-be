from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from auth.database import get_db
from auth.auth import get_current_user, get_current_user_masyarakat
from auth.models import Users, Roles
from .schemas import RoleSchema, AssignRoleSchema, RoleResponse
# from .models import Roles, UserRoles
import uuid
from datetime import datetime
import aiohttp

router = APIRouter()


async def sync_roles_from_asset(db: Session):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://arise-app.my.id/api/roles",
            headers={"accept": "application/json"}
        ) as resp:
            data = await resp.json()
            roles = data["data"]

            for r in roles:
                db_role = db.query(Roles).filter(Roles.role_id == r["id"]).first()

                if db_role:
                    db_role.role_name = r["name"]
                    db_role.created_at = r["created_at"]
                    db_role.updated_at = r["updated_at"]
                    db_role.is_local = False
                else:
                    new_role = Roles(
                        role_id=r["id"],
                        role_name=r["name"],
                        created_at=r["created_at"],
                        updated_at=r["updated_at"],
                        is_local=False
                    )
                    db.add(new_role)

            db.commit()


@router.post("/sync/roles")
async def sync_roles_endpoint(db: Session = Depends(get_db)):
    await sync_roles_from_asset(db)
    return {"message": "Roles synced successfully"}


@router.post("/roles")
def create_local_role(
    payload: RoleSchema,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role_name") != "diskominfo":
        raise HTTPException(
            status_code=403,
            detail="Unauthorized: hanya role diskominfo yang boleh menambah role lokal"
        )

    existing = db.query(Roles).filter(
        Roles.role_name.ilike(payload.role_name)
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Role '{payload.role_name}' sudah ada."
        )

    new_role = Roles(
        role_name=payload.role_name,
        is_local=True, 
    )

    db.add(new_role)
    db.commit()
    db.refresh(new_role)

    return {
        "message": "Role berhasil dibuat",
        "data": {
            "role_id": new_role.role_id,
            "role_name": new_role.role_name,
            "is_local": new_role.is_local,
            "created_at": new_role.created_at,
        }
    }

@router.get("/roles", response_model=list[RoleResponse])
def get_all_roles(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # if current_user.get("role_name") not in ["diskominfo"]:
    #     raise HTTPException(
    #         status_code=403,
    #         detail="Unauthorized: hanya role diskominfo yang boleh melihat daftar role"
    #     )

    roles = db.query(Roles).order_by(Roles.role_id.asc()).all()
    return roles


@router.get("/roles/{role_id}", response_model=RoleResponse)
def get_role_by_id(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # if current_user.get("role_name") not in ["diskominfo"]:
    #     raise HTTPException(
    #         status_code=403,
    #         detail="Unauthorized: hanya role diskominfo yang boleh melihat role"
    #     )

    role = db.query(Roles).filter(Roles.role_id == role_id).first()

    if not role:
        raise HTTPException(
            status_code=404,
            detail="Role tidak ditemukan"
        )

    return role

