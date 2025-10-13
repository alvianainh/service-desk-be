import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from auth import database
from auth.auth import get_current_user, get_user_by_email
from tickets import models, schemas

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/tickets")
async def create_ticket(
    data: schemas.TicketCreate,
    db: Session = Depends(database.get_db),
    current_user_email: str = Depends(get_current_user)
):
    try:
        user = await get_user_by_email(current_user_email, db)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        logger.info(f"Creating ticket for user: {user.email}")

        new_ticket = models.Ticket(
            title=data.title,
            description=data.description,
            priority=data.priority,
            ticket_type="Incident", 
            status="Open",
            user_id=user.id,
            creates_id=user.id,
            created_at=datetime.utcnow()
        )

        db.add(new_ticket)
        db.commit()
        db.refresh(new_ticket)

        return {
            "message": "Ticket created successfully",
            "ticket": {
                "ticket_id": str(new_ticket.ticket_id),
                "title": new_ticket.title,
                "priority": new_ticket.priority,
                "ticket_type": new_ticket.ticket_type,
                "status": new_ticket.status,
                "created_at": new_ticket.created_at,
            },
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating ticket: {e}")
        raise HTTPException(status_code=500, detail=str(e))
