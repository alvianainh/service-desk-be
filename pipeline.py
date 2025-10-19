import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.schemas import RegisterModel, LoginModel
from auth.auth import (
    register_user,
    verify_password,
    create_access_token,
    get_user_by_email,
    hash_password,
)
from auth import database
from auth.models import Users, Roles, UserRoles


router = APIRouter()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@router.get("/")
async def root():
    logger.info("GET / - Root endpoint accessed")
    return {"message": "Server is running!"}

# @router.post("/register")
# async def register(data: RegisterModel, db: Session = Depends(database.get_db)):
#     logger.info(f"POST /register - Register request for email: {data.email}")
#     result = await register_user(data, db)
#     logger.info(f"POST /register - Response: {result}")
#     return result

@router.post("/register")
async def register(data: RegisterModel, db: Session = Depends(database.get_db)):
    logger.info(f"POST /register - Register request for email: {data.email}")
    
    # Cek apakah user sudah ada
    existing_user = db.query(Users).filter(Users.email == data.email).first()
    if existing_user:
        return {"error": "Email already registered"}
    
    # Buat user baru
    hashed_pw = hash_password(data.password)
    new_user = Users(
        email=data.email,
        password=hashed_pw,
        first_name=data.first_name,
        last_name=data.last_name,
        phone_number=data.phone_number,
        opd_id=data.opd_id,
        birth_date=data.birth_date,
        address=data.address,
        no_employee=data.no_employee,
        jabatan=data.jabatan,
        division=data.division,
        start_date=data.start_date
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Ambil roles user (default: ["user"] jika belum ada role)
    from auth.models import Roles, UserRoles
    roles = (
        db.query(Roles.role_name)
        .join(UserRoles, Roles.role_id == UserRoles.role_id)
        .filter(UserRoles.user_id == new_user.id)
        .all()
    )
    role_names = [r.role_name for r in roles] if roles else ["user"]
    
    # Generate token
    access_token = create_access_token(new_user, db)

    
    logger.info(f"POST /register - User registered successfully: {new_user.email}")
    return {
        "message": "User registered successfully",
        "user_id": str(new_user.id),
        "token_type": "bearer",
        "user": {
            "email": new_user.email,
            "first_name": new_user.first_name,
            "last_name": new_user.last_name,
            "roles": role_names,
            "opd_id": str(new_user.opd_id) if new_user.opd_id else None,
            "no_employee": new_user.no_employee,
            "division": new_user.division
        }
    }


@router.post("/login")
async def login(data: LoginModel, db: Session = Depends(database.get_db)):
    user = await get_user_by_email(data.email, db)
    if not user or not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    from auth.models import Roles, UserRoles 
    roles = (
        db.query(Roles.role_name)
        .join(UserRoles, Roles.role_id == UserRoles.role_id)
        .filter(UserRoles.user_id == user.id)
        .all()
    )
    role_names = [r.role_name for r in roles] if roles else ["user"]

    access_token = create_access_token(user, db)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "roles": role_names
        }
    }
