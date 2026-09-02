from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from backend.app.database import get_db
from backend.app.config import settings
from backend.app.models.user import User
from backend.app.models.customer import Customer
from backend.app.models.audit_log import AuditLog
from backend.app.utils.security import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["Enterprise Integrations"])


@router.get("/tcsion/credentials")
def get_tcsion_credentials(
    customer_id: Optional[int] = Query(None, description="Optional Customer ID to associate with portal launch"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Securely returns configured TCS iON Enterprise Portal credentials
    to authenticated CRM agents and records an audit log event.
    """
    customer_info = None
    if customer_id:
        cust = db.query(Customer).filter(Customer.id == customer_id).first()
        if cust:
            customer_info = {
                "id": cust.id,
                "party_code": cust.party_code or cust.customer_id,
                "party_name": cust.party_name or cust.name
            }

    # Record Audit Log for Security & Compliance
    try:
        audit = AuditLog(
            user_id=current_user.id,
            user_name=current_user.full_name,
            user_email=current_user.email,
            user_role=current_user.role,
            action="INTEGRATION_LAUNCH",
            entity_type="integration",
            entity_id=str(customer_id) if customer_id else "tcsion",
            status="Success",
            changes={
                "portal": "TCS iON Enterprise Portal",
                "customer": customer_info,
                "login_url": settings.TCSION_LOGIN_URL,
                "message": f"User '{current_user.full_name}' launched TCS iON Portal" + (f" for Party: {customer_info['party_name']} ({customer_info['party_code']})" if customer_info else "")
            }
        )
        db.add(audit)
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to record TCS iON launch audit log: {e}")
        db.rollback()

    return {
        "portal_name": "TCS iON Enterprise Portal",
        "login_url": settings.TCSION_LOGIN_URL,
        "username": settings.TCSION_USERNAME,
        "password": settings.TCSION_PASSWORD,
        "customer": customer_info,
        "status": "ready"
    }
