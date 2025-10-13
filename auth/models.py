# from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Enum, ForeignKey, TEXT, TIMESTAMP
from .database import Base
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum
import uuid


# class RegisterModel(BaseModel):
#     email: str
#     password: str
#     full_name: str

# class LoginModel(BaseModel):
#     email: str
#     password: str

# class UserRole(str, enum.Enum):
#     user = "user"
#     admin = "admin"


class Roles(Base):
    __tablename__ = "roles"

    role_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_name = Column(String(50), unique=True, nullable=False)
    description = Column(TEXT)

    user_roles = relationship("UserRoles", back_populates="role")


class UserRoles(Base):
    __tablename__ = "user_roles"

    user_role_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.role_id"))
    assigned_at = Column(TIMESTAMP)

    user = relationship("Users", back_populates="user_roles")
    role = relationship("Roles", back_populates="user_roles")


class Users(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    first_name = Column(String)
    last_name = Column(String)
    phone_number = Column(String)
    profile_url = Column(String)

    user_roles = relationship("UserRoles", back_populates="user")