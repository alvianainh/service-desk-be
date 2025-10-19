from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

# class TicketCreate(BaseModel):
#     title: str
#     description: str | None = None
#     priority: str


# Input schema untuk masyarakat (tanpa title & priority)
class TicketCreateSchema(BaseModel):
    opd_id: UUID
    category_id: UUID
    description: str
    additional_info: Optional[str] = None
    file_url: Optional[str] = None


# Output schema setelah tiket dibuat
class TicketResponseSchema(BaseModel):
    message: str
    ticket_id: UUID
    status: str

    class Config:
        orm_mode = True


# Schema kategori (buat endpoint get categories)
class TicketCategorySchema(BaseModel):
    category_id: UUID
    opd_id: UUID
    category_name: str
    description: Optional[str]

    class Config:
        orm_mode = True