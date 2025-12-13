# from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Enum, ForeignKey, TEXT, TIMESTAMP, Date, Text, func, DateTime, Boolean, BigInteger
from .database import Base
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum
import uuid
from datetime import datetime


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


# class Roles(Base):
#     __tablename__ = "roles"

#     role_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     role_name = Column(String(50), unique=True, nullable=False)
#     description = Column(TEXT)

#     user_roles = relationship("UserRoles", back_populates="role")


class Roles(Base):
    __tablename__ = "roles"

    role_id = Column(BigInteger, primary_key=True, autoincrement=True, index=True)

    role_name = Column(String, unique=True, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),    
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),      
        onupdate=func.now(),          
        nullable=False
    )

    is_local = Column(Boolean, default=False)
    users = relationship("Users", back_populates="role")

    # user_roles = relationship("UserRoles", back_populates="role")


# class UserRoles(Base):
#     __tablename__ = "user_roles"

#     user_role_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
#     role_id = Column(UUID(as_uuid=True), ForeignKey("roles.role_id"))
#     assigned_at = Column(TIMESTAMP)

#     user = relationship("Users", back_populates="user_roles")
#     role = relationship("Roles", back_populates="user_roles")


class Users(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    full_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    profile_url = Column(String, nullable=True)
    nik = Column(String, nullable=True)

    address = Column(String, nullable=True)

    # opd_id = Column(UUID(as_uuid=True), ForeignKey("opd.opd_id"), nullable=True)
    opd_id_asset = Column(Integer, nullable=True)
    role_id = Column(BigInteger, ForeignKey("roles.role_id"), nullable=True)
    opd_id = Column(Integer, ForeignKey("dinas.id"), nullable=True)

    teknisi_level_id = Column(Integer, ForeignKey("teknisi_levels.id"), nullable=True)
    teknisi_tag_id = Column(Integer, ForeignKey("teknisi_tags.id"), nullable=True)
    teknisi_kuota_terpakai = Column(Integer, nullable=True, default=0)


    user_id_asset = Column(String, nullable=True)
    username_asset = Column(String, nullable=True)
    role_id_asset = Column(String, nullable=True)
    # role_name_asset = Column(String, nullable=True)

    # user_roles = relationship("UserRoles", back_populates="user")
    role = relationship("Roles", back_populates="users")

    teknisi_level_obj = relationship("TeknisiLevels", back_populates="users")
    teknisi_tag_obj = relationship("TeknisiTags", back_populates="users")
    # opd = relationship("Opd", back_populates="users")


class Opd(Base):
    __tablename__ = "opd"
    __table_args__ = {'extend_existing': True}

    opd_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opd_name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    file_path = Column(Text, nullable=True)

    id_aset = Column(Integer, unique=True, nullable=True)

    # users = relationship("Users", back_populates="opd")

class Articles(Base):
    __tablename__ = "articles"

    article_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String, default="draft")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    makes_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    approved_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    cover_path = Column(String, nullable=True)

    makes_by = relationship("Users", foreign_keys=[makes_by_id], backref="articles_created")
    approved_by = relationship("Users", foreign_keys=[approved_id], backref="articles_approved")
    tags = relationship("Tags", secondary="article_tags", back_populates="articles")


class ArticleTags(Base):
    __tablename__ = "article_tags"
    article_id = Column(UUID(as_uuid=True), ForeignKey("articles.article_id"), primary_key=True)
    tag_id = Column(UUID(as_uuid=True), ForeignKey("tags.tag_id"), primary_key=True)


class Tags(Base):
    __tablename__ = "tags"

    tag_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tag_name = Column(String, unique=True, nullable=False)

    
    articles = relationship("Articles", secondary="article_tags", back_populates="tags")

class RefreshTokens(Base):
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    revoked = Column(Boolean, default=False)

class Dinas(Base):
    __tablename__ = "dinas"

    id = Column(Integer, primary_key=True, autoincrement=False)
    nama = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)

    file_path = Column(String, nullable=True)


class PasswordResetOTP(Base):
    __tablename__ = "password_reset_otp"

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    otp_code = Column(String(6), nullable=False)
    expired_at = Column(DateTime(timezone=True), nullable=False)

    is_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
