from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from enum import Enum
from datetime import date


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    nik: Optional[str] = None
    address: Optional[str] = None

    @field_validator("nik")
    @classmethod
    def validate_nik(cls, v):
        if v is None:
            return v 
        if not v.isdigit():
            raise ValueError("NIK harus berupa angka")
        if len(v) != 16:
            raise ValueError("NIK harus terdiri dari 16 digit")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    

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
    nik: Optional[str] = None
    birth_date: Optional[date] = None
    address: Optional[str] = None
    no_employee: Optional[str] = None
    jabatan: Optional[str] = None
    division: Optional[str] = None
    start_date: Optional[date] = None

class LoginModel(BaseModel):
    email: str
    password: str
