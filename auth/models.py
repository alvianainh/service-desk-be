# from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Enum, ForeignKey, TEXT, TIMESTAMP, Date, Text, func
from .database import Base
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum
import uuid
from datetime import date


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
    opd_id = Column(UUID, ForeignKey("opd.opd_id"), nullable=True)
    birth_date = Column(Date)
    address = Column(String)
    no_employee = Column(String)
    jabatan = Column(String)
    division = Column(String)
    start_date = Column(Date)

    user_roles = relationship("UserRoles", back_populates="user")
    opd = relationship("Opd", back_populates="users")

class Opd(Base):
    __tablename__ = "opd"
    __table_args__ = {'extend_existing': True}

    opd_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opd_name = Column(String, unique=True, nullable=False)
    description = Column(Text)

    # relasi ke Users
    users = relationship("Users", back_populates="opd")

class Articles(Base):
    __tablename__ = "articles"

    article_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String, default="draft")  # draft, pending_review, approved, rejected
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    makes_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    approved_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    makes_by = relationship("Users", foreign_keys=[makes_by_id], backref="articles_created")
    approved_by = relationship("Users", foreign_keys=[approved_id], backref="articles_approved")