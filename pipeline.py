import logging
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from auth.database import get_db
# from auth.auth import routes as auth_routes

from auth.schemas import RegisterModel, LoginModel
from auth.auth import (
    register_user,
    verify_password,
    create_access_token,
    get_user_by_email,
    hash_password,
    get_current_user,
    create_refresh_token,
    verify_refresh_token
)
from auth import database
from auth.models import Users, Roles, UserRoles, Opd, RefreshTokens
from pydantic import BaseModel
from typing import List, Optional
from datetime import date
from uuid import UUID
import uuid
import mimetypes
import os
from dotenv import load_dotenv
from datetime import datetime
from supabase import create_client, Client

router = APIRouter()
# router.include_router(auth_routes.router)


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET_NAME = "avatar"

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
REFRESH_TOKEN_EXPIRE_DAYS = 7

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UserProfileSchema(BaseModel):
    id: UUID
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    birth_date: Optional[date] = None
    address: Optional[str] = None
    jabatan: Optional[str] = None
    start_date: Optional[date] = None
    profile_url: Optional[str] = None
    roles: List[str] = []
    opd_id: Optional[UUID] = None
    opd_name: Optional[str] = None
    no_employee: Optional[str] = None
    division: Optional[str] = None
    nik: Optional[str] = None

    model_config = {
        "from_attributes": True  # Pydantic V2
    }

class UserProfileUpdateSchema(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    birth_date: Optional[date] = None
    address: Optional[str] = None



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

# @router.post("/register")
# async def register(data: RegisterModel, db: Session = Depends(database.get_db)):
#     logger.info(f"POST /register - Register request for email: {data.email}")
    
#     # Cek apakah user sudah ada
#     existing_user = db.query(Users).filter(Users.email == data.email).first()
#     if existing_user:
#         return {"error": "Email already registered"}
    
#     # Buat user baru
#     hashed_pw = hash_password(data.password)
#     new_user = Users(
#         email=data.email,
#         password=hashed_pw,
#         first_name=data.first_name,
#         last_name=data.last_name,
#         phone_number=data.phone_number,
#         opd_id=data.opd_id,
#         birth_date=data.birth_date,
#         address=data.address,
#         no_employee=data.no_employee,
#         jabatan=data.jabatan,
#         division=data.division,
#         start_date=data.start_date
#     )
#     db.add(new_user)
#     db.commit()
#     db.refresh(new_user)
    
#     # Ambil roles user (default: ["user"] jika belum ada role)
#     from auth.models import Roles, UserRoles
#     roles = (
#         db.query(Roles.role_name)
#         .join(UserRoles, Roles.role_id == UserRoles.role_id)
#         .filter(UserRoles.user_id == new_user.id)
#         .all()
#     )
#     role_names = [r.role_name for r in roles] if roles else ["user"]
    
#     # Generate token
#     access_token = create_access_token(new_user, db)

    
#     logger.info(f"POST /register - User registered successfully: {new_user.email}")
#     return {
#         "message": "User registered successfully",
#         "user_id": str(new_user.id),
#         "token_type": "bearer",
#         "user": {
#             "email": new_user.email,
#             "first_name": new_user.first_name,
#             "last_name": new_user.last_name,
#             "roles": role_names,
#             "opd_id": str(new_user.opd_id) if new_user.opd_id else None,
#             "no_employee": new_user.no_employee,
#             "division": new_user.division
#         }
#     }


@router.post("/register")
async def register(data: RegisterModel, db: Session = Depends(database.get_db)):
    logger.info(f"POST /register - Register request for email: {data.email}")
    
    existing_user = db.query(Users).filter(Users.email == data.email).first()
    if existing_user:
        return {"error": "Email already registered"}
    
    hashed_pw = hash_password(data.password)
    new_user = Users(
        email=data.email,
        password=hashed_pw,
        first_name=data.first_name,
        last_name=data.last_name,
        phone_number=data.phone_number,
        opd_id=data.opd_id,
        nik=data.nik,
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

    from auth.models import Roles, UserRoles

    role = db.query(Roles).filter(Roles.role_name == "masyarakat").first()
    if not role:
        role = Roles(role_name="masyarakat", description="Default role for new users")
        db.add(role)
        db.commit()
        db.refresh(role)

    new_user_role = UserRoles(user_id=new_user.id, role_id=role.role_id)
    db.add(new_user_role)
    db.commit()

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
            "roles": ["masyarakat"],
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
    refresh_token = create_refresh_token(str(user.id), db)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "roles": role_names
        }
    }


@router.post("/refresh")
async def refresh_token(refresh_token: str, db: Session = Depends(get_db)):
    token_record = (
        db.query(RefreshTokens)
        .filter(RefreshTokens.token == refresh_token, RefreshTokens.revoked == False)
        .first()
    )

    if not token_record:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if token_record.expires_at < datetime.utcnow():
        token_record.revoked = True 
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user = db.query(Users).filter(Users.id == token_record.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_access_token = create_access_token(user, db)

    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }

@router.get("/profile", response_model=UserProfileSchema)
async def get_profile(
    current_user: dict = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    user = db.query(Users).filter(Users.id == current_user["id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    roles = (
        db.query(Roles.role_name)
        .join(UserRoles, Roles.role_id == UserRoles.role_id)
        .filter(UserRoles.user_id == user.id)
        .all()
    )
    role_names = [r.role_name for r in roles]

    opd_name = None
    if user.opd_id:
        opd = db.query(Opd).filter(Opd.opd_id == user.opd_id).first()
        opd_name = opd.opd_name if opd else None

    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone_number": user.phone_number,
        "birth_date": user.birth_date,
        "address": user.address,
        "jabatan": user.jabatan,
        "start_date": user.start_date,
        "profile_url": user.profile_url,
        "roles": role_names,
        "opd_id": user.opd_id,
        "nik": user.nik,
        "opd_name": opd_name,
        "no_employee": user.no_employee,
        "division": user.division
    }

@router.put("/profile", response_model=UserProfileSchema)
async def update_profile(
    first_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    phone_number: Optional[str] = Form(None),
    birth_date: Optional[date] = Form(None),
    address: Optional[str] = Form(None),
    file: UploadFile = File(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(Users).filter(Users.id == current_user["id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if first_name is not None:
        user.first_name = first_name
    if last_name is not None:
        user.last_name = last_name
    if phone_number is not None:
        user.phone_number = phone_number
    if birth_date is not None:
        user.birth_date = birth_date
    if address is not None:
        user.address = address

    if file:
        file_extension = file.filename.split(".")[-1]
        file_path = f"avatar/{user.id}_{uuid.uuid4()}.{file_extension}"
        file_data = await file.read()

        content_type, _ = mimetypes.guess_type(file.filename)
        if not content_type:
            content_type = "application/octet-stream"

        supabase.storage.from_("avatar").upload(file_path, file_data, {"content-type": content_type})

        public_url = supabase.storage.from_("avatar").get_public_url(file_path) 
        user.profile_url = public_url

    db.commit()
    db.refresh(user)

    roles = [r.role_name for r in db.query(Roles.role_name)
             .join(UserRoles, Roles.role_id == UserRoles.role_id)
             .filter(UserRoles.user_id == user.id).all()]

    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone_number": user.phone_number,
        "birth_date": user.birth_date,
        "address": user.address,
        "profile_url": user.profile_url,
        "roles": roles,
        "opd_id": user.opd_id,
        "no_employee": user.no_employee,
        "division": user.division,
        "jabatan": user.jabatan,
        "start_date": user.start_date
    }