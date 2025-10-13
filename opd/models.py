from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import UUID
import uuid
from auth.database import Base

class OPD(Base):
    __tablename__ = "opd"

    opd_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opd_name = Column(String, unique=True, nullable=False)
    description = Column(Text)
