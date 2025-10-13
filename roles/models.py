from sqlalchemy import Column, String, Text, ForeignKey, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from auth.database import Base

# class Roles(Base):
#     __tablename__ = "roles"
#     role_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     role_name = Column(String, unique=True, nullable=False)
#     description = Column(Text)


# class UserRoles(Base):
#     __tablename__ = "user_roles"
#     user_role_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
#     role_id = Column(UUID(as_uuid=True), ForeignKey("roles.role_id"))
#     assigned_at = Column(TIMESTAMP(timezone=True))
