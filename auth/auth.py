import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
from dotenv import load_dotenv
import os
from fastapi import Header, Depends, HTTPException, status, Security
from jwt import PyJWTError
from sqlalchemy.orm import Session
from auth.schemas import RegisterModel
from . import models, database
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .database import get_db
import uuid
from .models import Users, Roles, Opd, RefreshTokens, Dinas
from jose import JWTError, jwt
import requests
from fastapi import security
import aiohttp
from fastapi.security import OAuth2PasswordBearer

sso_scheme = HTTPBearer(description="Masukkan token SSO di sini")


load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 10080
REFRESH_TOKEN_EXPIRE_DAYS = 7

# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

security = HTTPBearer()


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login/masyarakat")
     

def create_refresh_token(user_id: str, db: Session):
    token = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    new_refresh = RefreshTokens(
        user_id=user_id,
        token=token,
        expires_at=expires_at,
        revoked=False
    )
    db.add(new_refresh)
    db.commit()
    db.refresh(new_refresh)
    return token


def verify_refresh_token(db: Session, token: str):
    record = (
        db.query(RefreshTokens)
        .filter(RefreshTokens.token == token, RefreshTokens.revoked == False)
        .first()
    )

    if not record:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Refresh token expired")

    return record.user_id

def hash_password(password: str) -> str:
    truncated = password.encode("utf-8")[:72] 
    return pwd_context.hash(truncated)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    truncated = plain_password.encode("utf-8")[:72] 
    return pwd_context.verify(truncated, hashed_password)

def create_access_token_simple(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_access_token(user: Users, db: Session, expires_delta: timedelta = None):
    role = db.query(Roles).filter(Roles.role_id == user.role_id).first()
    role_name = role.role_name if role else None

    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role_id": user.role_id,
        "role_name": role_name,
    }

    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload.update({"exp": expire})

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token

def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token: no subject")
        return email
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def register_user(data: RegisterModel, db: Session):
    existing_user = db.query(Users).filter(Users.email == data.email).first()
    if existing_user:
        return {"error": "Email already registered"}

    hashed_pw = hash_password(data.password)
    new_user = Users(
        email=data.email,
        password=hashed_pw,
        full_name=data.full_name,
        phone_number=data.phone_number,
        address=data.address,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User registered successfully", "user_id": str(new_user.id)}


async def get_user_by_email(email: str, db: Session = Depends(database.get_db)):
    user = db.query(models.Users).filter(models.Users.email == email).first()
    return user

ASSET_PROFILE_URL = "https://arise-app.my.id/api/account-management" 

async def get_dinas_id_from_unit_kerja(unit_kerja_id: str, token: str):
    url = "https://arise-app.my.id/api/unit-kerja"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers={"Authorization": f"Bearer {token}"}) as res:
            if res.status != 200:
                raise HTTPException(res.status, await res.text())
            data = await res.json()
            units = data.get("data", [])
            for unit in units:
                if str(unit["id"]) == str(unit_kerja_id):
                    return unit["dinas_id"]
    raise HTTPException(404, f"Unit kerja ID {unit_kerja_id} tidak ditemukan")



async def sync_user_from_aset(db: Session, aset_user: dict, token: str):
    email = aset_user["email"]
    new_user_id_asset = str(aset_user["id"])
    role_id_aset = aset_user.get("role_id")
    unit_kerja_id = aset_user.get("unit_kerja_id")

    dinas_id_aset = None
    if unit_kerja_id:
        dinas_id_aset = await get_dinas_id_from_unit_kerja(unit_kerja_id, token)

    role = db.query(Roles).filter(Roles.role_id == role_id_aset).first()
    if not role:
        raise HTTPException(status_code=400, detail="Role dari API belum terdaftar")

    dinas = None
    if dinas_id_aset:
        dinas = db.query(Dinas).filter(Dinas.id == dinas_id_aset).first()
        if not dinas:
            raise HTTPException(status_code=400, detail="Dinas dari API belum terdaftar")

    user_by_email = db.query(Users).filter(Users.email == email).first()
    user_by_aset_id = db.query(Users).filter(Users.user_id_asset == new_user_id_asset).first()

    if user_by_email and user_by_aset_id and user_by_email.id != user_by_aset_id.id:
        user = user_by_email
        db.delete(user_by_aset_id)
        db.commit()
    elif user_by_email:
        user = user_by_email
    elif user_by_aset_id:
        user = user_by_aset_id
    else:
        user = Users(
            email=email,
            full_name=aset_user.get("name"),
            username_asset=aset_user.get("username"),
            address=aset_user.get("alamat"),
            user_id_asset=new_user_id_asset,
            role_id_asset=role_id_aset,
            opd_id_asset=dinas_id_aset,
            role_id=role.role_id,
            opd_id=dinas.id if dinas else None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    # update 
    user.email = email
    user.full_name = aset_user.get("name")
    user.username_asset = aset_user.get("username")
    user.address = aset_user.get("alamat")
    user.user_id_asset = new_user_id_asset
    user.role_id_asset = role_id_aset
    user.opd_id_asset = dinas_id_aset
    user.role_id = role.role_id
    user.opd_id = dinas.id if dinas else None

    db.commit()
    db.refresh(user)
    return user


async def get_current_user_universal_from_token(token: str):
    db: Session = next(get_db())

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id:
            user = db.query(Users).join(Roles).filter(Users.id == user_id).first()
            if user:
                dinas = db.query(Dinas).filter(Dinas.id == user.opd_id).first()
                return {
                    "id": str(user.id),
                    "email": user.email,
                    "full_name": user.full_name,
                    "role_id": user.role_id,
                    "dinas_id": user.opd_id,
                    "role_name": user.role.role_name if user.role else None,
                    "dinas_name": dinas.nama if dinas else None,
                    "is_sso": False
                }
    except Exception:
        pass

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://arise-app.my.id/api/me",
                headers={"Authorization": f"Bearer {token}"}
            ) as res:
                if res.status != 200:
                    raise Exception("Invalid SSO token")
                data = await res.json()
                aset_user = data.get("user")

        local_user = sync_user_from_aset(db, aset_user)
        dinas = db.query(Dinas).filter(Dinas.id == local_user.opd_id).first()
        return {
            "id": str(local_user.id),
            "email": local_user.email,
            "full_name": local_user.full_name,
            "role_id": local_user.role_id,
            "dinas_id": local_user.opd_id,
            "role_name": local_user.role.role_name if local_user.role else None,
            "dinas_name": dinas.nama if dinas else None,
            "is_sso": True
        }
    except Exception:
        return None


async def get_current_user_universal(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id:
            user = (
                db.query(Users)
                .join(Roles, Users.role_id == Roles.role_id)
                .filter(Users.id == user_id)
                .first()
            )
            if user:
                dinas = db.query(Dinas).filter(Dinas.id == user.opd_id).first()
                return {
                    "id": str(user.id),
                    "email": user.email,
                    "full_name": user.full_name,
                    "role_id": user.role_id,
                    "role_name": user.role.role_name if user.role else None,
                    "dinas_id": user.opd_id,
                    "dinas_name": dinas.nama if dinas else None,
                    "is_sso": False,
                    "access_token": token
                }
    except Exception:
        pass

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://arise-app.my.id/api/me",
                headers={"Authorization": f"Bearer {token}"}
            ) as res:
                if res.status != 200:
                    raise HTTPException(status_code=401, detail="Invalid SSO token")
                data = await res.json()
                aset_user = data.get("user")
                if not aset_user:
                    raise HTTPException(status_code=502, detail="User data not found in Aset API response")

        local_user = await sync_user_from_aset(db, aset_user, token)
        dinas = db.query(Dinas).filter(Dinas.id == local_user.opd_id).first()

        return {
            "id": str(local_user.id),
            "email": local_user.email,
            "full_name": local_user.full_name,
            "role_id": local_user.role_id,
            "role_name": local_user.role.role_name if local_user.role else None,
            "dinas_id": local_user.opd_id,
            "dinas_name": dinas.nama if dinas else None,
            "is_sso": True,
            "access_token": token
        }
    except Exception:
        raise HTTPException(status_code=401, detail="Token tidak valid untuk kedua sistem")


def get_current_user_masyarakat(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub") 
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        user = (
            db.query(Users)
            .join(Roles, Users.role_id == Roles.role_id)
            .with_entities(
                Users.id,
                Users.email,
                Users.full_name,
                Users.phone_number,
                Users.address,
                Users.profile_url,
                Roles.role_id,
                Roles.role_name,
                Users.opd_id,
                Users.nik
            )
            .filter(Users.id == user_id)
            .first()
        )

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        return {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "phone_number": user.phone_number,
            "profile_url": user.profile_url,
            "address": user.address,
            "role_id": user.role_id,
            "dinas_id": user.opd_id,
            "role_name": user.role_name,
            "nik": user.nik
        }

    except PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(sso_scheme),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://arise-app.my.id/api/me",
            headers={"Authorization": f"Bearer {token}"}
        ) as res:

            if res.status == 401:
                raise HTTPException(status_code=401, detail="Token tidak valid / tidak authenticated")
            elif res.status == 403:
                raise HTTPException(status_code=403, detail="Forbidden: akses ditolak")
            elif res.status != 200:
                text = await res.text()
                raise HTTPException(
                    status_code=502,
                    detail=f"Unexpected response from Aset API: {text[:200]}"
                )

            content_type = res.headers.get("Content-Type", "")
            if "application/json" not in content_type:
                text = await res.text()
                raise HTTPException(
                    status_code=502,
                    detail=f"Invalid response format from Aset API: {text[:200]}"
                )

            data = await res.json()
            aset_user = data.get("user")
            if not aset_user:
                raise HTTPException(status_code=502, detail="User data not found in Aset API response")

    local_user = await sync_user_from_aset(db, aset_user, token)

    dinas = db.query(Dinas).filter(Dinas.id == local_user.opd_id).first()

    return {
        "id": str(local_user.id),
        "email": local_user.email,
        "full_name": local_user.full_name,
        "username_asset": local_user.username_asset,
        "role_id": local_user.role_id,
        "role_name": local_user.role.role_name if local_user.role else None,
        "dinas_id": local_user.opd_id,
        "dinas_name": dinas.nama if dinas else None,
        "dinas_id_asset": local_user.opd_id_asset,
        "token": token
    }

