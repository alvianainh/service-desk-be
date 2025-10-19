from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from auth.database import get_db
from auth.auth import get_current_user
from auth.models import Users, Roles, UserRoles
from .schemas import RoleSchema, AssignRoleSchema
# from .models import Roles, UserRoles
import uuid
from datetime import datetime

router = APIRouter()

@router.post("/roles/")
async def create_role(
    role: RoleSchema,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    user_roles = current_user.get("roles", [])

    if "admin_kota" not in user_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Only admin_kota can create roles"
        )

    existing_role = db.query(Roles).filter(Roles.role_name == role.role_name).first()
    if existing_role:
        raise HTTPException(status_code=400, detail="Role already exists")

    new_role = Roles(
        role_id=uuid.uuid4(),
        role_name=role.role_name,
        description=role.description
    )
    db.add(new_role)
    db.commit()
    db.refresh(new_role)

    return {"message": "Role created successfully", "data": new_role}

@router.put("/{role_id}")
async def update_role(
    role_id: str,
    role_data: RoleSchema,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    user_roles = current_user.get("roles", [])
    if "admin_kota" not in user_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Only admin_kota can update roles"
        )

    role = db.query(Roles).filter(Roles.role_id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    role.role_name = role_data.role_name
    role.description = role_data.description
    db.commit()
    db.refresh(role)

    return {"message": "Role updated successfully", "data": role}

@router.delete("/{role_id}")
async def delete_role(
    role_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    user_roles = current_user.get("roles", [])
    if "admin_kota" not in user_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Only admin_kota can delete roles"
        )

    role = db.query(Roles).filter(Roles.role_id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    db.delete(role)
    db.commit()

    return {"message": "Role deleted successfully"}

@router.get("/roles/")
async def get_roles(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    roles = db.query(Roles).all()

    if not roles:
        raise HTTPException(status_code=404, detail="No roles found")

    return {"roles": roles}


@router.post("/assign-role/")
async def assign_role(
    data: AssignRoleSchema,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if "admin_kota" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Unauthorized: Only admin_kota can assign roles")

    user = db.query(Users).filter(Users.id == data.user_id).first()
    role = db.query(Roles).filter(Roles.role_id == data.role_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    db.query(UserRoles).filter(UserRoles.user_id == user.id).delete()

    new_user_role = UserRoles(
        user_id=user.id,
        role_id=role.role_id,
        assigned_at=datetime.utcnow() 
    )
    db.add(new_user_role)
    db.commit()
    db.refresh(new_user_role)

    return {
        "message": f"Role '{role.role_name}' successfully assigned to {user.email}",
        "data": {
            "user_id": str(user.id),
            "role_id": str(role.role_id),
            "role_name": role.role_name,
            "assigned_at": new_user_role.assigned_at.isoformat()
        }
    }


@router.put("/assign-role/{user_role_id}")
async def update_assigned_role(
    user_role_id: str,
    data: AssignRoleSchema,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if "admin_kota" not in current_user.get("roles", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized: Only admin_kota can update roles")

    user_role = db.query(UserRoles).filter(UserRoles.user_role_id == user_role_id).first()
    if not user_role:
        raise HTTPException(status_code=404, detail="Assigned role not found")

    role = db.query(Roles).filter(Roles.role_id == data.role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    user_role.role_id = role.role_id
    db.commit()
    db.refresh(user_role)

    return {
        "message": f"Assigned role updated to '{role.role_name}'",
        "data": {
            "user_id": str(user_role.user_id),
            "role_id": str(user_role.role_id)
        }
    }

@router.delete("/assign-role/{user_role_id}")
async def delete_assigned_role(
    user_role_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if "admin_kota" not in current_user.get("roles", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized: Only admin_kota can delete roles")

    user_role = db.query(UserRoles).filter(UserRoles.user_role_id == user_role_id).first()
    if not user_role:
        raise HTTPException(status_code=404, detail="Assigned role not found")

    db.delete(user_role)
    db.commit()

    return {"message": "Assigned role deleted successfully"}

@router.get("/user-roles/")
async def get_all_user_roles(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    if "admin_kota" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Only admin_kota can view all user roles"
        )

    result = (
        db.query(
            UserRoles.user_role_id,
            Users.id.label("user_id"),
            Users.first_name,
            Users.last_name,
            Users.email,
            Roles.role_id,
            Roles.role_name,
            Roles.description
        )
        .join(Users, Users.id == UserRoles.user_id)
        .join(Roles, Roles.role_id == UserRoles.role_id)
        .all()
    )

    if not result:
        raise HTTPException(status_code=404, detail="No user roles found")

    user_roles_list = []
    for r in result:
        user_roles_list.append({
            "user_role_id": str(r.user_role_id),
            "user_id": str(r.user_id),
            "first_name": r.first_name,
            "last_name": r.last_name,
            "email": r.email,
            "role_id": str(r.role_id),
            "role_name": r.role_name,
            "role_description": r.description
        })

    return {"user_roles": user_roles_list}


@router.get("/user/{user_id}/roles")
async def get_user_roles(
    user_id: str,
    current_user: dict = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    result = (
        db.query(
            Users.id,
            Users.first_name,
            Users.last_name,
            Users.email,
            Roles.role_name,
            Roles.description
        )
        .join(UserRoles, Users.id == UserRoles.user_id)
        .join(Roles, Roles.role_id == UserRoles.role_id)
        .filter(Users.id == user_id)
        .all()
    )

    if not result:
        raise HTTPException(status_code=404, detail="User or roles not found")

    user_info = {
        "user_id": str(result[0].id),
        "first_name": result[0].first_name,
        "last_name": result[0].last_name,
        "email": result[0].email
    }

    roles = [
        {"role_name": r.role_name, "description": r.description}
        for r in result
    ]

    return {
        "user": user_info,
        "roles": roles
    }