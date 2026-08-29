from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from backend.app.database import get_db
from backend.app.models.audit_log import AuditLog
from backend.app.models.user import User
from backend.app.utils.security import get_current_user, get_current_admin_user
from backend.app.services.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["Audit Logs"])

@router.get("")
def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    entity_type: Optional[str] = None,
    action: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Admin-only: Retrieve system audit logs."""
    query = db.query(AuditLog).options(joinedload(AuditLog.user))
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if action:
        query = query.filter(AuditLog.action == action)

    logs = query.order_by(desc(AuditLog.created_at)).limit(limit).all()
    return [
        {
            "id": l.id,
            "action": l.action,
            "entity_type": l.entity_type,
            "entity_id": l.entity_id,
            "changes": l.changes,
            "user_id": l.user_id,
            "user_name": l.user_name or (l.user.full_name if l.user else "System / Webhook"),
            "user_email": l.user_email or (l.user.email if l.user else None),
            "user_role": l.user_role or (l.user.role if l.user else "system"),
            "status": l.status or "Success",
            "created_at": (
                (l.created_at.replace(tzinfo=__import__('datetime').timezone.utc) if l.created_at.tzinfo is None else l.created_at).isoformat()
                if l.created_at else None
            )
        }
        for l in logs
    ]

@router.delete("")
def clear_audit_logs(
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Admin-only: Clear system audit trail logs.
    """
    cleared_count = db.query(AuditLog).delete(synchronize_session=False)
    db.commit()

    # Log that audit trail was cleared
    AuditService.log(
        db,
        action="AUDIT_TRAIL_CLEARED",
        entity_type="audit_log",
        changes={"cleared_records_count": cleared_count},
        user=admin_user
    )

    return {
        "status": "success",
        "message": f"Successfully cleared {cleared_count} audit trail log record(s).",
        "cleared_count": cleared_count
    }
