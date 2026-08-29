from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.config import settings
from backend.app.schemas.email import SendEmailRequest
from backend.app.services.email_service import EmailService
from backend.app.services.audit_service import AuditService
from backend.app.utils.security import get_current_user

router = APIRouter(prefix="/emails", tags=["Emails"])

class SMTPTestRequest(BaseModel):
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_tls: Optional[bool] = None
    to_email: Optional[str] = None

class SMTPConfigRequest(BaseModel):
    smtp_user: str
    smtp_password: str
    smtp_host: Optional[str] = "smtp.gmail.com"
    smtp_port: Optional[int] = 587
    smtp_tls: Optional[bool] = True
    email_from: Optional[str] = None

@router.get("/templates")
def get_templates():
    """Retrieve pre-built customer email templates."""
    return EmailService.get_templates()

@router.post("/test-smtp")
def test_smtp(
    req: SMTPTestRequest = None,
    current_user: User = Depends(get_current_user)
):
    """Test SMTP connection and send a verification probe email."""
    data = req.model_dump() if req else {}
    return EmailService.test_smtp_connection(
        smtp_user=data.get("smtp_user"),
        smtp_password=data.get("smtp_password"),
        smtp_host=data.get("smtp_host"),
        smtp_port=data.get("smtp_port"),
        smtp_tls=data.get("smtp_tls"),
        to_email=data.get("to_email")
    )

@router.post("/config")
def update_smtp_config(
    cfg: SMTPConfigRequest,
    current_user: User = Depends(get_current_user)
):
    """Update runtime SMTP credentials (e.g. Gmail App Password)."""
    settings.SMTP_USER = cfg.smtp_user.strip()
    settings.SMTP_PASSWORD = cfg.smtp_password.strip()
    settings.SMTP_HOST = cfg.smtp_host.strip() if cfg.smtp_host else "smtp.gmail.com"
    settings.SMTP_PORT = cfg.smtp_port or 587
    settings.SMTP_TLS = cfg.smtp_tls if cfg.smtp_tls is not None else True
    settings.EMAIL_FROM = (cfg.email_from or cfg.smtp_user).strip()
    settings.EMAIL_PROVIDER = "smtp"

    return {
        "status": "success",
        "message": f"SMTP configuration updated for {settings.SMTP_USER}.",
        "smtp_user": settings.SMTP_USER,
        "smtp_host": settings.SMTP_HOST
    }

@router.post("/send")
@router.post("/send/{customer_id}")
def send_customer_email(
    email_req: SendEmailRequest,
    customer_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Dispatch transactional email directly to customer and log to timeline."""
    target_cust_id = customer_id or email_req.customer_id
    if not target_cust_id:
        raise HTTPException(status_code=400, detail="customer_id is required in URL or body")

    try:
        result = EmailService.send_email(
            db=db,
            customer_id=target_cust_id,
            email_req=email_req,
            sender_user=current_user
        )
        AuditService.log(
            db,
            action="EMAIL_SENT",
            entity_type="email",
            entity_id=str(target_cust_id),
            changes={"to": email_req.to_email, "subject": email_req.subject},
            user=current_user
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email dispatch error: {str(e)}")
