from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from datetime import datetime, timezone
from backend.app.database import get_db
from backend.app.models.interaction import CustomerInteraction
from backend.app.models.customer import Customer
from backend.app.models.follow_up import FollowUp
from backend.app.models.user import User
from backend.app.schemas.interaction import InteractionCreate, InteractionOut
from backend.app.services.audit_service import AuditService
from backend.app.utils.security import get_current_user

router = APIRouter(prefix="/interactions", tags=["Interactions & Notes"])

@router.post("", response_model=InteractionOut, status_code=status.HTTP_201_CREATED)
def create_interaction(
    interaction_in: InteractionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Log a new interaction (Call note, Email, Meeting, WhatsApp, General Note)."""
    customer = db.query(Customer).filter(Customer.id == interaction_in.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    interaction = CustomerInteraction(
        customer_id=interaction_in.customer_id,
        user_id=current_user.id,
        interaction_type=interaction_in.interaction_type,
        direction=interaction_in.direction or "internal",
        subject=interaction_in.subject or f"{interaction_in.interaction_type.title()} Logged",
        content=interaction_in.content,
        meta_info=interaction_in.meta_info or {},
        interaction_time=interaction_in.interaction_time or datetime.now(timezone.utc)
    )
    db.add(interaction)

    # Optional: Automatically create a follow-up task if requested
    if interaction_in.create_follow_up and interaction_in.follow_up_due_date:
        follow_up = FollowUp(
            customer_id=customer.id,
            assigned_user_id=current_user.id,
            title=interaction_in.follow_up_title or f"Follow-up with {customer.name}",
            description=f"Follow-up regarding note: '{interaction_in.content[:100]}...'",
            due_date=interaction_in.follow_up_due_date,
            priority=interaction_in.follow_up_priority or "Medium",
            status="Pending"
        )
        db.add(follow_up)

    db.commit()
    db.refresh(interaction)

    AuditService.log(
        db,
        action="NOTE_ADDED",
        entity_type="interaction",
        entity_id=str(interaction.id),
        changes={"type": interaction.interaction_type, "customer_id": customer.id},
        user=current_user
    )

    return InteractionOut.model_validate(interaction)

@router.get("", response_model=List[InteractionOut])
def list_interactions(
    customer_id: Optional[int] = None,
    channel: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List recent interactions."""
    query = db.query(CustomerInteraction).options(joinedload(CustomerInteraction.user))
    if customer_id:
        query = query.filter(CustomerInteraction.customer_id == customer_id)
    if channel:
        query = query.filter(CustomerInteraction.interaction_type == channel)

    items = query.order_by(desc(CustomerInteraction.interaction_time)).limit(limit).all()
    return [InteractionOut.model_validate(i) for i in items]
