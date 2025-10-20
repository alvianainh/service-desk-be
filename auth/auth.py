import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
from dotenv import load_dotenv
import os
from fastapi import Depends, HTTPException, status
from jwt import PyJWTError
from sqlalchemy.orm import Session
from auth.schemas import RegisterModel
from . import models, database
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .database import get_db
from .models import Users, Roles, UserRoles, Opd
from jose import JWTError, jwt


load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

security = HTTPBearer()
     
# def hash_password(password: str):
#     return pwd_context.hash(password)

def hash_password(password: str):
    password = password.encode("utf-8")[:72]  # truncate
    return pwd_context.hash(password)


# def verify_password(plain_password, hashed_password) -> bool:
#     return pwd_context.verify(plain_password, hashed_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    plain_password = plain_password.encode("utf-8")[:72]
    return pwd_context.verify(plain_password, hashed_password)



# def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
#     to_encode = data.copy()
#     expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
#     to_encode.update({"exp": expire})
#     return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_access_token(user: Users, db: Session, expires_delta: timedelta = None) -> str:
    """
    Generate JWT token containing user's info
    """
    roles = [r.role.role_name for r in user.user_roles]

    opd_name = None
    if user.opd_id:
        opd = db.query(Opd).filter(Opd.opd_id == user.opd_id).first()
        opd_name = opd.opd_name if opd else None

    payload = {
        "sub": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "roles": roles,
        "opd_id": str(user.opd_id) if user.opd_id else None,
        "opd_name": opd_name,
        "no_employee": user.no_employee,
        "division": user.division
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

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_email = payload.get("sub") 
        role_names = payload.get("roles")
        opd_id = payload.get("opd_id")
        opd_name = payload.get("opd_name")


        if not user_email:
            raise HTTPException(status_code=401, detail="Invalid token")

        user = db.query(Users).filter(Users.email == user_email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        roles = (
            db.query(Roles.role_name)
            .join(UserRoles, Roles.role_id == UserRoles.role_id)
            .filter(UserRoles.user_id == user.id)
            .all()
        )
        role_names = [r.role_name for r in roles]

        return {
            "id": str(user.id),
            "email": user.email,
            "roles": role_names,
            "opd_id": opd_id,  
            "opd_name": opd_name
        }

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def register_user(data: RegisterModel, db: Session):
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
    return {"message": "User registered successfully", "user_id": str(new_user.id)}

async def get_user_by_email(email: str, db: Session = Depends(database.get_db)):
    user = db.query(models.Users).filter(models.Users.email == email).first()
    return user
