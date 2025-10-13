from pydantic import BaseModel
from typing import Optional
from uuid import UUID

class OPDBase(BaseModel):
    opd_name: str
    description: Optional[str] = None

class OPDCreate(OPDBase):
    pass

class OPDResponse(OPDBase):
    opd_id: UUID

    class Config:
        orm_mode = True
