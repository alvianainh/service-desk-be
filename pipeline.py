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

    from auth.models import Roles, UserRoles 
    roles = (
        db.query(Roles.role_name)
        .join(UserRoles, Roles.role_id == UserRoles.role_id)
        .filter(UserRoles.user_id == user.id)
        .all()
    )
    role_names = [r.role_name for r in roles] if roles else ["user"]

    access_token = create_access_token(
        data={
            "sub": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "roles": role_names
        }
    )

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
