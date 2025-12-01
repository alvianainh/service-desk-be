from sqlalchemy import Column, String, Text, DateTime, ForeignKey, CheckConstraint, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from auth.database import Base
import uuid
from datetime import datetime

# # class Ticket(Base):
# #     __tablename__ = "tickets"

# #     ticket_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
# #     title = Column(String, nullable=False)
# #     description = Column(Text)
# #     priority = Column(String, nullable=False)
# #     ticket_type = Column(String, nullable=False)
# #     status = Column(String, nullable=False)
# #     created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
# #     updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
# #     closed_at = Column(TIMESTAMP(timezone=True), nullable=True)

# #     user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
# #     creates_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))

# class Tickets(Base):
#     __tablename__ = "tickets"

#     ticket_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     description = Column(Text, nullable=True)
#     priority = Column(String(50), nullable=True)
#     status = Column(String(50), nullable=False, default="Open")
#     sla_due = Column(DateTime, nullable=True)
#     created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
#     updated_at = Column(DateTime, nullable=True, default=datetime.utcnow)
#     closed_at = Column(DateTime, nullable=True)
#     asset_id = Column(UUID(as_uuid=True), nullable=True)
#     creates_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
#     assigned_to_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
#     verified_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
#     escalated_to_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
#     opd_id = Column(UUID(as_uuid=True), ForeignKey("opd.opd_id"), nullable=True)
#     category_id = Column(UUID(as_uuid=True), ForeignKey("ticket_categories.category_id"), nullable=True)
#     additional_info = Column(Text, nullable=True)
#     ticket_source = Column(String, nullable=False, default="masyarakat")
#     request_type = Column(String, nullable=True)
#     ticket_stage = Column(String(50), nullable=True, default="user_draft")  

#     attachments = relationship("TicketAttachment", back_populates="ticket", cascade="all, delete-orphan")

#     __table_args__ = (
#         CheckConstraint("status IN ('Draft', 'Open', 'In Progress', 'Resolved', 'Closed', 'On Hold')"),
#         CheckConstraint("ticket_source IN ('masyarakat', 'pegawai')"),
#         CheckConstraint(
#             "request_type IS NULL OR request_type IN ('reset_password', 'permohonan_akses', 'permintaan_perangkat')"
#         ),
#         CheckConstraint(
#              "ticket_stage IN ('user_draft', 'submitted', 'seksi_draft', 'seksi_verified', 'seksi_rejected', 'pending', 'revisi')"
# )

#     )

#     opd = relationship("Opd", backref="tickets")
#     attachments = relationship("TicketAttachment", back_populates="ticket")
#     category = relationship("TicketCategories", back_populates="tickets")


# class TicketAttachment(Base):
#     __tablename__ = "ticket_attachment"

#     attachment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
#     file_path = Column(String, nullable=False)
#     has_id = Column(UUID(as_uuid=True), ForeignKey("tickets.ticket_id"))

#     ticket = relationship("Tickets", back_populates="attachments")



class Tickets(Base):
    __tablename__ = "tickets"

    ticket_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    expected_resolution = Column(Text, nullable=True)
    priority = Column(String(50), nullable=True)
    status = Column(String(50), nullable=False, default="Draft")
    sla_due = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    opd_id_asset = Column(Integer, nullable=True)
    # opd_id_tickets = Column(Integer, nullable=True)
    # role_id_source = Column(Integer, nullable=True)
    lokasi_kejadian = Column(String(50), nullable=True)
    ticket_source = Column(String(20), nullable=True)

    asset_id = Column(Integer, nullable=True)
    kode_bmd_asset = Column(String, nullable=True)
    nomor_seri_asset = Column(String, nullable=True)
    nama_asset = Column(String, nullable=True)
    kategori_asset = Column(String, nullable=True)
    subkategori_id_asset = Column(Integer, nullable=True)
    jenis_asset = Column(String, nullable=True)
    lokasi_asset = Column(JSON, nullable=True)
    metadata_asset = Column(JSON, nullable=True)
    ticket_code = Column(String, unique=True, nullable=True)
    subkategori_nama_asset = Column(String, nullable=True)


    # Relations
    creates_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    assigned_to_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    verified_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    escalated_to_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    opd_id_tickets = Column(Integer, ForeignKey("dinas.id"), nullable=True)
    role_id_source = Column(Integer, ForeignKey("roles.role_id"), nullable=True)

    # opd_id = Column(UUID(as_uuid=True), ForeignKey("opd.opd_id"))
    # category_id = Column(UUID(as_uuid=True), ForeignKey("ticket_categories.category_id"))

    # ticket_source = Column(String, nullable=False, default="masyarakat")

    request_type = Column(String, nullable=True)
    ticket_stage = Column(String(50), nullable=False, default="user_draft")

    attachments = relationship("TicketAttachment", back_populates="ticket", cascade="all, delete-orphan")
    creates_user = relationship("Users", foreign_keys=[creates_id])



    __table_args__ = (
        CheckConstraint(
            "status IN ('Draft', 'Open', 'In Progress', 'Resolved', 'Closed', 'On Hold', 'Verified by Seksi', "
            "'Rejected by Seksi', 'Rejected by Bidang', 'Verified', 'Verified by Bidang', 'Re-open')"
        ),
        # CheckConstraint("ticket_source IN ('masyarakat', 'pegawai')"),
        CheckConstraint(
            "request_type IS NULL OR request_type IN ('reset_password', 'permohonan_akses', 'permintaan_perangkat')"
        ),
        CheckConstraint(
            "ticket_stage IN ('user_draft','user_submit','seksi_draft','seksi_submit','bidang_draft','bidang_submit')"
        )
    )

class TicketAttachment(Base):
    __tablename__ = "ticket_attachment"

    attachment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    file_path = Column(String, nullable=False)
    has_id = Column(UUID(as_uuid=True), ForeignKey("tickets.ticket_id", ondelete="CASCADE"))

    ticket = relationship("Tickets", back_populates="attachments")


class TicketUpdates(Base):
    __tablename__ = "ticket_updates"

    update_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status_change = Column(String(50), nullable=False)
    notes = Column(Text, nullable=True)
    update_time = Column(DateTime, nullable=False, default=datetime.utcnow)

    makes_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)

    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.ticket_id", ondelete="CASCADE"), nullable=True)

    # opd_id = Column(UUID(as_uuid=True), ForeignKey("opd.opd_id", ondelete="CASCADE"), nullable=True)

    user = relationship("Users", backref="ticket_updates", foreign_keys=[makes_by_id])
    ticket = relationship("Tickets", backref="updates", foreign_keys=[ticket_id])
    # opd = relationship("Opd", backref="ticket_updates", foreign_keys=[opd_id])




class TicketCategories(Base):
    __tablename__ = "ticket_categories"

    category_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opd_id = Column(UUID(as_uuid=True), ForeignKey("opd.opd_id"))
    category_name = Column(Text, nullable=False)
    description = Column(Text)

    # tickets = relationship("Tickets", back_populates="category")


# class TicketUpdates(Base):
#     __tablename__ = "ticket_updates"

#     update_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     status_change = Column(String(50), nullable=False)
#     notes = Column(Text, nullable=True)
#     update_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    
#     has_calendar_id = Column(UUID(as_uuid=True), ForeignKey("opd.opd_id", ondelete="CASCADE"), nullable=True)
#     makes_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
#     ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.ticket_id", ondelete="CASCADE"), nullable=True)

#     opd = relationship("Opd", backref="ticket_updates", foreign_keys=[has_calendar_id])
#     user = relationship("Users", backref="ticket_updates", foreign_keys=[makes_by_id])
#     ticket = relationship("Tickets", backref="updates", foreign_keys=[ticket_id])
