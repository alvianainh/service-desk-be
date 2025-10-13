from pydantic import BaseModel

class TicketCreate(BaseModel):
    title: str
    description: str | None = None
    priority: str
