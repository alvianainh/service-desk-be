import logging
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Header
from sqlalchemy.orm import Session
from auth.database import get_db
# from auth.auth import routes as auth_routes

from auth.schemas import RegisterModel, LoginModel, UserRegister, UserLogin, TokenResponse
from auth.auth import (
    register_user,
    verify_password,
    create_access_token,
    get_user_by_email,
    hash_password,
    get_current_user,
    get_current_user_masyarakat,
    create_refresh_token,
    verify_refresh_token,
    create_access_token_simple
)
from auth import database
from auth.models import Users, Roles, Opd, RefreshTokens
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
import aiohttp

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

SSO_LOGIN_URL = "https://arise-app.my.id/api/login"
ARISE_ME_URL = "https://arise-app.my.id/api/me"

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

class LoginPayload(BaseModel):
    login: str
    password: str


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


@router.post("/register/masyarakat", response_model=TokenResponse)
async def register_user_route(data: UserRegister, db: Session = Depends(get_db)):
    existing_user = db.query(Users).filter(Users.email == data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email sudah digunakan")

    user = Users(
        email=data.email,
        password=hash_password(data.password),
        full_name=data.full_name,
        phone_number=data.phone_number,
        address=data.address,
        nik=data.nik,
        role_id=9 
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user, db)

    return {"access_token": token, "token_type": "bearer"}



@router.post("/login/masyarakat", response_model=TokenResponse)
def login_user(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(Users).filter(Users.email == payload.email).first()
    if not user or not user.password or not verify_password(payload.password, user.password):
        raise HTTPException(status_code=401, detail="Email atau password salah")

    token = create_access_token(user, db)

    return {"access_token": token, "token_type": "bearer"}


@router.post("/login/sso")
async def login_sso(payload: LoginPayload):

    async with aiohttp.ClientSession() as session:
        async with session.post(
            SSO_LOGIN_URL,
            json={
                "login": payload.login,
                "password": payload.password
            },
            headers={
                "accept": "application/json",
                "Content-Type": "application/json"
            }
        ) as response:

            text = await response.text()

            if response.status != 200:
                raise HTTPException(
                    status_code=response.status,
                    detail=f"SSO login failed: {text}"
                )

            data = await response.json()

            return {
                "access_token": data.get("access_token"),
                "token_type": data.get("token_type"),
                "expires_in": data.get("expires_in"),
                "user": data.get("user")
            }


# @router.post("/register")
# async def register(data: RegisterModel, db: Session = Depends(database.get_db)):
#     logger.info(f"POST /register - Register request for email: {data.email}")
    
#     existing_user = db.query(Users).filter(Users.email == data.email).first()
#     if existing_user:
#         return {"error": "Email already registered"}
    
#     hashed_pw = hash_password(data.password)
#     new_user = Users(
#         email=data.email,
#         password=hashed_pw,
#         first_name=data.first_name,
#         last_name=data.last_name,
#         phone_number=data.phone_number,
#         opd_id=data.opd_id,
#         nik=data.nik,
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

#     from auth.models import Roles, UserRoles

#     role = db.query(Roles).filter(Roles.role_name == "masyarakat").first()
#     if not role:
#         role = Roles(role_name="masyarakat", description="Default role for new users")
#         db.add(role)
#         db.commit()
#         db.refresh(role)

#     new_user_role = UserRoles(user_id=new_user.id, role_id=role.role_id)
#     db.add(new_user_role)
#     db.commit()

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
#             "roles": ["masyarakat"],
#             "opd_id": str(new_user.opd_id) if new_user.opd_id else None,
#             "no_employee": new_user.no_employee,
#             "division": new_user.division
#         }
#     }

# @router.post("/login")
# async def login(data: LoginModel, db: Session = Depends(database.get_db)):
#     user = await get_user_by_email(data.email, db)
#     if not user or not verify_password(data.password, user.password):
#         raise HTTPException(status_code=401, detail="Invalid email or password")

#     from auth.models import Roles, UserRoles
#     roles = (
#         db.query(Roles.role_name)
#         .join(UserRoles, Roles.role_id == UserRoles.role_id)
#         .filter(UserRoles.user_id == user.id)
#         .all()
#     )
#     role_names = [r.role_name for r in roles] if roles else ["user"]

#     access_token = create_access_token(user, db)
#     refresh_token = create_refresh_token(str(user.id), db)

#     return {
#         "access_token": access_token,
#         "refresh_token": refresh_token,
#         "token_type": "bearer",
#         "user": {
#             "email": user.email,
#             "first_name": user.first_name,
#             "last_name": user.last_name,
#             "roles": role_names
#         }
#     }


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

# @router.get("/me")
# async def get_profile(current_user: dict = Depends(get_current_user)):
#     """
#     Endpoint untuk melihat data user hasil get_current_user.
#     """
#     return {
#         "message": "Success",
#         "data": current_user
#     }


# @router.get("/me")
# async def get_sso_me(current_user: dict = Depends(get_current_user)):

#     token = current_user["token"]  

#     async with aiohttp.ClientSession() as session:
#         async with session.get(
#             ARISE_ME_URL,
#             headers={
#                 "accept": "application/json",
#                 "Authorization": f"Bearer {token}",
#             }
#         ) as response:

#             text = await response.text()

#             if response.status != 200:
#                 raise HTTPException(
#                     status_code=response.status,
#                     detail=f"Error from Arise: {text}",
#                 )

#             data = await response.json()
#             return data


@router.get("/me")
async def get_sso_me(current_user: dict = Depends(get_current_user)):

    token = current_user["token"]

    # --- STEP 1: GET USER SSO /me ---
    async with aiohttp.ClientSession() as session:
        async with session.get(
            ARISE_ME_URL,
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {token}",
            }
        ) as res_me:

            text_me = await res_me.text()
            if res_me.status != 200:
                raise HTTPException(
                    status_code=res_me.status,
                    detail=f"Error from Arise: {text_me}"
                )

            user_data = await res_me.json()

    # user_data["user"]["unit_kerja_id"] bisa "1" (string)
    unit_kerja_id_raw = user_data.get("user", {}).get("unit_kerja_id")

    if not unit_kerja_id_raw:
        return {
            "user": user_data,
            "opd": None,
            "message": "User tidak memiliki unit_kerja_id"
        }

    try:
        unit_kerja_id = int(unit_kerja_id_raw)   # <-- FIX DI SINI
    except:
        return {
            "user": user_data,
            "opd": None,
            "message": "unit_kerja_id tidak valid"
        }

    # --- STEP 2: GET LIST UNIT KERJA ---
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://arise-app.my.id/api/unit-kerja",
            headers={"accept": "application/json"}
        ) as res_uk:

            text_uk = await res_uk.text()
            if res_uk.status != 200:
                raise HTTPException(
                    status_code=res_uk.status,
                    detail=f"Error fetching unit kerja: {text_uk}"
                )

            unit_kerja_data = await res_uk.json()

    unit_list = unit_kerja_data.get("data", [])

    # --- STEP 3: FIND MAPPING ---
    target_unit = next((u for u in unit_list if int(u["id"]) == unit_kerja_id), None)

    if not target_unit:
        opd_info = None
    else:
        opd_info = {
            "unit_kerja_id": target_unit["id"],
            "unit_kerja_nama": target_unit["nama"],
            "opd_id": int(target_unit["dinas_id"]) if target_unit.get("dinas_id") else None,
            "opd_nama": target_unit["dinas"]["nama"] if target_unit.get("dinas") else None
        }

    return {
        "user": user_data,
        "opd": opd_info
    }




@router.get("/me/masyarakat", summary="Get current logged-in user (Masyarakat)")
def read_current_user(current_user: dict = Depends(get_current_user_masyarakat)):
    user = current_user.copy()

    if user.get("profile_url"):
        try:
            user["profile_url"] = user["profile_url"]
        except Exception:
            user["profile_url"] = None

    user["nik"] = current_user.get("nik")

    return user


@router.put("/me/masyarakat")
async def update_profile(
    full_name: str = Form(None),
    phone_number: str = Form(None),
    address: str = Form(None),
    file: UploadFile = File(None),
    current_user: dict = Depends(get_current_user_masyarakat),
    db: Session = Depends(get_db)
):
    user = db.query(Users).filter(Users.id == current_user["id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if full_name is not None:
        user.full_name = full_name
    if phone_number is not None:
        user.phone_number = phone_number
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

    return {
        "id": user.id,
        "full_name": user.full_name,
        "phone_number": user.phone_number,
        "address": user.address,
        "profile_url": user.profile_url
    }

@router.put("/me/masyarakat/password")
def change_password(
    old_password: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_masyarakat)
):
    user = db.query(Users).filter(Users.id == current_user["id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.password or not verify_password(old_password, user.password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password lama salah")

    user.password = hash_password(new_password)
    db.commit()
    db.refresh(user)

    return {
        "message": "Password berhasil diubah"
    }

@router.delete("/me/masyarakat/avatar", summary="Hapus profile picture")
def delete_profile_picture(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_masyarakat)
):
    user = db.query(Users).filter(Users.id == current_user["id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.profile_url:
        raise HTTPException(status_code=400, detail="User tidak memiliki profile picture")

    file_path = user.profile_url.split("/")[-1] 

    try:
        response = supabase.storage.from_("avatar").remove([file_path])
        if response:  
            raise HTTPException(status_code=500, detail=f"Gagal hapus file: {response}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal hapus file: {str(e)}")

    user.profile_url = None
    db.commit()
    db.refresh(user)

    return {
        "message": "Profile picture berhasil dihapus"
    }
