from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from fastapi import Form

class OPDBase(BaseModel):
    opd_name: str
    description: Optional[str] = None
    file_path: Optional[str] = None

class OPDCreate(BaseModel):
    opd_name: str
    description: Optional[str] = None

    @classmethod
    def as_form(
        cls,
        opd_name: str = Form(...),
        description: Optional[str] = Form(None),
    ):
        return cls(opd_name=opd_name, description=description)

class OPDResponse(OPDBase):
    opd_id: UUID

    class Config:
        orm_mode = True
