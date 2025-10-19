from pydantic import BaseModel

class TicketCreate(BaseModel):
    title: str
    description: str | None = None
    priority: str

class TicketTrackByPasswordRequest(BaseModel):
    ticket_id: UUID
    password: str

class TrackingPageResponse(BaseModel):
    ticket_id: UUID          
    status: str             
    #category_name: str | None = None  
    opd_name: str | None = None       