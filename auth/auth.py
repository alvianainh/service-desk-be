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
ACCESS_TOKEN_EXPIRE_MINUTES = 60
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

# def create_access_token(user: Users, db: Session, expires_delta: timedelta = None) -> str:
#     roles = [r.role.role_name for r in user.user_roles]

#     opd_name = None
#     if user.opd_id:
#         opd = db.query(Opd).filter(Opd.opd_id == user.opd_id).first()
#         opd_name = opd.opd_name if opd else None

#     payload = {
#         "sub": user.email,
#         "first_name": user.first_name,
#         "last_name": user.last_name,
#         "roles": roles,
#         "opd_id": str(user.opd_id) if user.opd_id else None,
#         "opd_name": opd_name,
#         "no_employee": user.no_employee,
#         "division": user.division
#     }

#     expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
#     payload.update({"exp": expire})

#     token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
#     return token


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


# async def register_user(data: RegisterModel, db: Session):
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
#     return {"message": "User registered successfully", "user_id": str(new_user.id)}




async def get_user_by_email(email: str, db: Session = Depends(database.get_db)):
    user = db.query(models.Users).filter(models.Users.email == email).first()
    return user

ASSET_PROFILE_URL = "https://arise-app.my.id/api/account-management" 


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
                Roles.role_name
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
            "role_name": user.role_name
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

    local_user = sync_user_from_aset(db, aset_user)

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



def sync_user_from_aset(db: Session, aset_user: dict):
    role_id_aset = aset_user.get("role_id")
    dinas_id_aset = aset_user.get("dinas_id")

    role = db.query(Roles).filter(Roles.role_id == role_id_aset).first()
    if not role:
        raise HTTPException(
            status_code=400,
            detail=f"Role dengan ID {role_id_aset} dari ASET belum terdaftar di tabel roles"
        )

    dinas = None
    if dinas_id_aset is not None:
        dinas = db.query(Dinas).filter(Dinas.id == dinas_id_aset).first()
        if not dinas:
            raise HTTPException(
                status_code=400,
                detail=f"Dinas dengan ID {dinas_id_aset} dari ASET belum terdaftar di tabel Dinas"
            )

    user = db.query(Users).filter(
        Users.user_id_asset == str(aset_user["id"])
    ).first()

    if not user:
        user = Users(
            email=aset_user["email"],
            password=None,
            full_name=aset_user.get("name"),
            username_asset=aset_user.get("username"),
            address=aset_user.get("alamat"),

            opd_id_asset=dinas_id_aset,
            role_id_asset=role_id_aset,
            user_id_asset=str(aset_user["id"]),

            role_id=role.role_id,
            opd_id=dinas.id if dinas else None,
        )
        db.add(user)
    else:
        user.email = aset_user["email"]
        user.full_name = aset_user.get("name")
        user.username_asset = aset_user.get("username")
        user.address = aset_user.get("alamat")

        user.opd_id_asset = dinas_id_aset
        user.role_id_asset = role_id_aset

        user.role_id = role.role_id
        user.opd_id = dinas.id if dinas else None

    db.commit()
    db.refresh(user)

    return user



# async def get_current_user_masyarakat(
#     credentials: HTTPAuthorizationCredentials = Depends(security),
#     db: Session = Depends(get_db)
# ):
#     token = credentials.credentials

#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

#         user_email = payload.get("sub")
#         opd_id = payload.get("opd_id")
#         opd_name = payload.get("opd_name")

#         if not user_email:
#             raise HTTPException(status_code=401, detail="Invalid token")

#         user = db.query(Users).filter(Users.email == user_email).first()
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         roles = (
#             db.query(Roles.role_name)
#             .join(UserRoles, Roles.role_id == UserRoles.role_id)
#             .filter(UserRoles.user_id == user.id)
#             .all()
#         )
#         role_names = [r.role_name for r in roles] if roles else []

#         return {
#             "id": str(user.id),
#             "email": user.email,
#             "full_name": user.full_name,
#             "roles": role_names,     
#             "opd_id": opd_id,        
#             "opd_name": opd_name
#         }

#     except JWTError:
#         raise HTTPException(status_code=401, detail="Invalid token")



# async def get_current_user_masyarakat(
#     credentials: HTTPAuthorizationCredentials = Depends(security),
#     db: Session = Depends(get_db)
# ):
#     token = credentials.credentials
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         user_email = payload.get("sub") 
#         role_names = payload.get("roles")
#         opd_id = payload.get("opd_id")
#         opd_name = payload.get("opd_name")


#         if not user_email:
#             raise HTTPException(status_code=401, detail="Invalid token")

#         user = db.query(Users).filter(Users.email == user_email).first()
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         roles = (
#             db.query(Roles.role_name)
#             .join(UserRoles, Roles.role_id == UserRoles.role_id)
#             .filter(UserRoles.user_id == user.id)
#             .all()
#         )
#         role_names = [r.role_name for r in roles]

#         return {
#             "id": str(user.id),
#             "email": user.email,
#             "roles": role_names,
#             "opd_id": opd_id,  
#             "opd_name": opd_name
#         }

#     except JWTError:
#         raise HTTPException(status_code=401, detail="Invalid token")





# def parse_name(full_name: str):
#     """
#     Pecah nama menjadi first_name + last_name
#     """
#     parts = full_name.split()
#     if len(parts) == 0:
#         return None, None
#     if len(parts) == 1:
#         return parts[0], None
#     return parts[0], " ".join(parts[1:])