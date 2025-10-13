from pydantic import BaseModel
from uuid import UUID
from typing import Optional

class RoleSchema(BaseModel):
    role_name: str
    description: Optional[str] = None


class AssignRoleSchema(BaseModel):
    user_id: UUID
    role_id: UUID
