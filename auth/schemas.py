from pydantic import BaseModel, EmailStr
from typing import Optional
from enum import Enum


class UserRole(str, Enum):
    user = "user"
    admin = "admin"

class RegisterModel(BaseModel):
    email: str
    first_name: str
    last_name: str
    password: str

class LoginModel(BaseModel):
    email: str
    password: str
