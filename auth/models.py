# from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Enum
from .database import Base
import enum


# class RegisterModel(BaseModel):
#     email: str
#     password: str
#     full_name: str

# class LoginModel(BaseModel):
#     email: str
#     password: str

class UserRole(str, enum.Enum):
    user = "user"
    admin = "admin"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    password = Column(String)
    role = Column(String, nullable=False, default="user")