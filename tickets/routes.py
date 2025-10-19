import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from auth import database
from auth.auth import get_current_user, get_user_by_email, verify_password
from auth.models import Users
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

@router.post("/tickets/track-by-password/page")
async def track_ticket_page(
    data: schemas.TicketTrackByPasswordRequest,
    db: Session = Depends(database.get_db),
):
    ticket = (
        db.query(models.Ticket)
        .filter(models.Ticket.ticket_id == data.ticket_id)
        .first()
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    owner_user_id = ticket.user_id or ticket.creates_id
    if not owner_user_id:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    owner = db.query(Users).filter(Users.id == owner_user_id).first()
    if not owner or not owner.password or not verify_password(data.password, owner.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    latest_status = db.execute(
        text("""
            SELECT status_change
            FROM ticket_updates
            WHERE ticket_id = :tid
            ORDER BY update_time DESC
            LIMIT 1
        """),
        {"tid": str(ticket.ticket_id)}
    ).scalar()
    status_display = latest_status or ticket.status

    opd_name = None
    if getattr(ticket, "opd_id", None):
        opd_name = db.execute(
            text("SELECT opd_name FROM opd WHERE opd_id = :oid"),
            {"oid": str(ticket.opd_id)}
        ).scalar()

    return {
        "ticket_id": str(ticket.ticket_id),
        "status": status_display,
        "opd_name": opd_name
    }