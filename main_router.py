import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.schemas import RegisterModel, LoginModel
from auth.auth import (
    register_user,
    verify_password,
    create_access_token,
    get_user_by_email
)
from auth import database

router = APIRouter()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@router.get("/")
async def root():
    logger.info("GET / - Root endpoint accessed")
    return {"message": "Server is running!"}

@router.post("/register")
async def register(data: RegisterModel, db: Session = Depends(database.get_db)):
    logger.info(f"POST /register - Register request for email: {data.email}")
    result = await register_user(data, db)
    logger.info(f"POST /register - Response: {result}")
    return result

@router.post("/login")
async def login(data: LoginModel, db: Session = Depends(database.get_db)):
    user = await get_user_by_email(data.email, db)
    if not user or not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(
        data={
            "sub": user.email,
            "role": user.role,
            "first_name": user.first_name,
            "last_name": user.last_name,
        }
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role  # kirim role ke frontend
        }
    }
