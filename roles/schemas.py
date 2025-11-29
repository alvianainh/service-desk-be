from pydantic import BaseModel
from uuid import UUID
from typing import Optional
from datetime import datetime

class RoleSchema(BaseModel):
    role_name: str
    # description: Optional[str] = None

class RoleResponse(BaseModel):
    role_id: int
    role_name: str
    is_local: bool
    created_at: Optional[datetime]

    class Config:
        orm_mode = True


class AssignRoleSchema(BaseModel):
    user_id: UUID
    role_id: UUID
