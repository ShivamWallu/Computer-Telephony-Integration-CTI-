from typing import Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from backend.app.models.audit_log import AuditLog
from backend.app.models.user import User

class AuditService:
    @staticmethod
    def log(
        db: Session,
        action: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        changes: Optional[Dict[str, Any]] = None,
        user: Optional[User] = None,
        ip_address: Optional[str] = None,
        status: str = "Success"
    ) -> AuditLog:
        """Create and commit an immutable audit log entry with trusted user snapshot."""
        u_name = user.full_name if user else "System / Webhook"
        u_email = user.email if user else None
        u_role = user.role if user else "system"

        log_entry = AuditLog(
            user_id=user.id if user else None,
            user_name=u_name,
            user_email=u_email,
            user_role=u_role,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            status=status,
            changes=changes or {},
            ip_address=ip_address,
            created_at=datetime.now(timezone.utc)
        )
        db.add(log_entry)
        db.commit()
        return log_entry
