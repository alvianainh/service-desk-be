from sqlalchemy import Column, String, Text, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from auth.database import Base
import uuid
from datetime import datetime

# class Ticket(Base):
#     __tablename__ = "tickets"

#     ticket_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     title = Column(String, nullable=False)
#     description = Column(Text)
#     priority = Column(String, nullable=False)
#     ticket_type = Column(String, nullable=False)
#     status = Column(String, nullable=False)
#     created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
#     updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
#     closed_at = Column(TIMESTAMP(timezone=True), nullable=True)

#     user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
#     creates_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))

class Tickets(Base):
    __tablename__ = "tickets"

    ticket_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    description = Column(Text, nullable=True)
    priority = Column(String(50), nullable=True)
    status = Column(String(50), nullable=False, default="Open")
    sla_due = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    asset_id = Column(UUID(as_uuid=True), nullable=True)
    creates_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    assigned_to_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    verified_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    escalated_to_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    opd_id = Column(UUID(as_uuid=True), ForeignKey("opd.opd_id"), nullable=True)
    category_id = Column(UUID(as_uuid=True), ForeignKey("ticket_categories.category_id"), nullable=True)
    additional_info = Column(Text, nullable=True)
    ticket_source = Column(String, nullable=False, default="masyarakat")
    request_type = Column(String, nullable=True)

    opd = relationship("OPD", backref="tickets")
    category = relationship("TicketCategories", backref="tickets")