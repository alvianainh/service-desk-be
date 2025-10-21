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
    status: str

    class Config:
        orm_mode = True



class TicketForSeksiSchema(BaseModel):
    ticket_id: UUID
    description: Optional[str]
    priority: Optional[str]
    status: str
    created_at: datetime
    updated_at: Optional[datetime]
    closed_at: Optional[datetime]
    opd_id: Optional[UUID]
    category_id: Optional[UUID]
    creates_id: Optional[UUID]
    ticket_source: Optional[str]
    additional_info: Optional[str]
    request_type: Optional[str]

    class Config:
        orm_mode = True


class TicketCategorySchema(BaseModel):
    category_id: UUID
    opd_id: UUID
    category_name: str
    description: Optional[str]

    class Config:
        orm_mode = True

class TicketTrackResponse(BaseModel):
    ticket_id: UUID 
    status: str 
    jenis_laporan: Optional[str]
    opd: Optional[str]

    class Config:
        orm_mode = True
