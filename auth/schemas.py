from pydantic import BaseModel, EmailStr
from typing import Optional
from enum import Enum


class UserRole(str, Enum):
    user = "user"
    admin = "admin"

class RegisterModel(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    password: str
    role: Optional[UserRole] = UserRole.user

class LoginModel(BaseModel):
    email: str
    password: str
