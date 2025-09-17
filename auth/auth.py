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

load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

security = HTTPBearer()
     
def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token: no subject")
        return email
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    email = decode_token(token)
    return email

# -------------------------
# REGISTER USER
# -------------------------
async def register_user(data: RegisterModel, db: Session = Depends(database.get_db)):
    existing_user = db.query(models.User).filter(models.User.email == data.email).first()
    if existing_user:
        return {"error": "Email already registered"}

    hashed_pw = hash_password(data.password)
    new_user = models.User(
        email=data.email,
        password=hashed_pw,
        first_name=data.first_name,
        last_name=data.last_name,
        role=data.role  # <-- tambahkan role di sini
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User registered successfully"}


# -------------------------
# GET USER BY EMAIL
# -------------------------
async def get_user_by_email(email: str, db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.email == email).first()
    return user
