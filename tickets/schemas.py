from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

# class TicketCreate(BaseModel):
#     title: str
#     description: str | None = None
#     priority: str


class TicketCreateSchema(BaseModel):
    opd_id: UUID
    category_id: UUID
    description: str
    additional_info: Optional[str] = None
    file_url: Optional[str] = None


class TicketResponseSchema(BaseModel):
    message: str
    ticket_id: UUID
    status_change: str
    ticket_stage: str

    class Config:
        from_attributes = True

class TicketForSeksiSchema(BaseModel):
    ticket_id: UUID
    title: Optional[str] = None
    description: Optional[str]
    priority: Optional[str]
    status: str
    ticket_stage: str
    created_at: datetime
    #updated_at: Optional[datetime]
    #closed_at: Optional[datetime]
    #opd_id: Optional[UUID]
    category_id: Optional[UUID]
    category_name: Optional[str] = None
    #creates_id: Optional[UUID]
    #ticket_source: Optional[str]
    additional_info: Optional[str]
    request_type: Optional[str]
    assigned_to_id: Optional[UUID]

    creator_name: Optional[str] = None  
    attachments: list[str] = []    

    class Config:
        from_attributes = True

class TicketBidangVerifySchema(BaseModel):
    ticket_id: UUID
    priority: Optional[str]
    notes: Optional[str] = None
    is_revisi: Optional[bool] = False
    is_reject: Optional[bool] = False
    status: str  # Draft / Verified by Bidang

    class Config:
        from_attributes = True
class TicketBidangSubmitResponse(BaseModel):
    message: str
    ticket_id: UUID
    status: str
    priority: Optional[str]
    is_revisi: Optional[bool] = False
    is_reject: Optional[bool] = False

    class Config:
        from_attributes = True


class TicketCategorySchema(BaseModel):
    category_id: UUID
    opd_id: UUID
    category_name: str
    description: Optional[str]

    class Config:
        from_attributes = True
class TicketTrackResponse(BaseModel):
    ticket_id: UUID 
    status: str 
    jenis_laporan: Optional[str]
    opd: Optional[str]

    class Config:
        from_attributes = True