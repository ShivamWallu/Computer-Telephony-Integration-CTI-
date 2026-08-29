from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, asc, and_
from datetime import datetime, timezone, timedelta
from backend.app.database import get_db
from backend.app.models.follow_up import FollowUp
from backend.app.models.customer import Customer
from backend.app.models.user import User
from backend.app.schemas.follow_up import FollowUpCreate, FollowUpUpdate, FollowUpOut
from backend.app.services.audit_service import AuditService
from backend.app.utils.security import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/followups", tags=["Follow-ups & Tasks"])

@router.get("", response_model=List[FollowUpOut])
def list_followups(
    filter_type: str = Query("all", description="all, today, overdue, upcoming, completed"),
    priority: Optional[str] = None,
    customer_id: Optional[int] = None,
    assigned_user_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List follow-ups categorized by status and due date."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    query = db.query(FollowUp).options(
        joinedload(FollowUp.customer),
        joinedload(FollowUp.assigned_user)
    )

    if customer_id:
        query = query.filter(FollowUp.customer_id == customer_id)
    if assigned_user_id:
        query = query.filter(FollowUp.assigned_user_id == assigned_user_id)
    if priority:
        query = query.filter(FollowUp.priority == priority)

    if filter_type == "today":
        query = query.filter(
            FollowUp.status.in_(["Pending", "In Progress"]),
            FollowUp.due_date >= today_start,
            FollowUp.due_date < today_end
        ).order_by(asc(FollowUp.due_date))
    elif filter_type == "overdue":
        query = query.filter(
            FollowUp.status.in_(["Pending", "In Progress"]),
            FollowUp.due_date < today_start
        ).order_by(asc(FollowUp.due_date))
    elif filter_type == "upcoming":
        query = query.filter(
            FollowUp.status.in_(["Pending", "In Progress"]),
            FollowUp.due_date >= today_end
        ).order_by(asc(FollowUp.due_date))
    elif filter_type == "completed":
        query = query.filter(FollowUp.status == "Completed").order_by(desc(FollowUp.completed_at))
    else:
        query = query.order_by(asc(FollowUp.due_date))

    items = query.limit(limit).all()
    return [FollowUpOut.model_validate(f) for f in items]

@router.post("", response_model=FollowUpOut, status_code=status.HTTP_201_CREATED)
def create_followup(
    fu_in: FollowUpCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new follow-up task."""
    customer = db.query(Customer).filter(Customer.id == fu_in.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    fu = FollowUp(
        customer_id=fu_in.customer_id,
        assigned_user_id=fu_in.assigned_user_id or current_user.id,
        title=fu_in.title,
        description=fu_in.description,
        due_date=fu_in.due_date,
        priority=fu_in.priority or "Medium",
        status=fu_in.status or "Pending"
    )
    db.add(fu)
    db.commit()
    db.refresh(fu)

    AuditService.log(
        db,
        action="FOLLOWUP_CREATED",
        entity_type="follow_up",
        entity_id=str(fu.id),
        user=current_user
    )

    return FollowUpOut.model_validate(fu)

@router.put("/{id}", response_model=FollowUpOut)
def update_followup(
    id: int,
    fu_update: FollowUpUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update follow-up task status, reschedule due date, or reassign."""
    fu = db.query(FollowUp).filter(FollowUp.id == id).first()
    if not fu:
        raise HTTPException(status_code=404, detail="Follow-up not found")

    if fu_update.title is not None:
        fu.title = fu_update.title
    if fu_update.description is not None:
        fu.description = fu_update.description
    if fu_update.due_date is not None:
        fu.due_date = fu_update.due_date
    if fu_update.priority is not None:
        fu.priority = fu_update.priority
    if fu_update.status is not None:
        fu.status = fu_update.status
        if fu_update.status == "Completed":
            fu.completed_at = datetime.now(timezone.utc)
        elif fu_update.status in ["Pending", "In Progress"]:
            fu.completed_at = None
    if fu_update.assigned_user_id is not None:
        fu.assigned_user_id = fu_update.assigned_user_id

    db.commit()
    db.refresh(fu)

    AuditService.log(
        db,
        action="FOLLOWUP_UPDATED",
        entity_type="follow_up",
        entity_id=str(fu.id),
        changes={"status": fu.status, "due_date": fu.due_date.isoformat() if fu.due_date else None},
        user=current_user
    )

    return FollowUpOut.model_validate(fu)

@router.delete("/{id}")
def delete_followup(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Safely delete an individual follow-up task.
    Customer records, timeline history, and other follow-ups remain 100% untouched.
    """
    fu = db.query(FollowUp).filter(FollowUp.id == id).first()
    if not fu:
        raise HTTPException(status_code=404, detail="Follow-up task not found")

    title = fu.title
    cust_id = fu.customer_id
    db.delete(fu)
    db.commit()

    AuditService.log(
        db,
        action="FOLLOWUP_DELETED",
        entity_type="follow_up",
        entity_id=str(id),
        changes={"title": title, "customer_id": cust_id},
        user=current_user
    )

    logger.info(f"Deleted individual follow-up task #{id} ('{title}') for customer #{cust_id}")
    return {
        "status": "success",
        "deleted_id": id,
        "message": f"Follow-up task '{title}' deleted successfully."
    }
