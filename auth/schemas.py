from pydantic import BaseModel, EmailStr
from typing import Optional
from enum import Enum
from datetime import date


class UserRole(str, Enum):
    user = "user"
    admin = "admin"

class RegisterModel(BaseModel):
    email: str
    first_name: str
    last_name: str
    password: str
    phone_number: Optional[str] = None
    opd_id: Optional[str] = None
    birth_date: Optional[date] = None
    address: Optional[str] = None
    no_employee: Optional[str] = None
    jabatan: Optional[str] = None
    division: Optional[str] = None
    start_date: Optional[date] = None

class LoginModel(BaseModel):
    email: str
    password: str
