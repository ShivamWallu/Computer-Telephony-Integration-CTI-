from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.app.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    user_name = Column(String(150), nullable=True, index=True)
    user_email = Column(String(150), nullable=True, index=True)
    user_role = Column(String(50), nullable=True)
    
    action = Column(String(100), nullable=False, index=True)  # "CUSTOMER_CREATED", "CUSTOMER_UPDATED", "CALL_LOGGED", etc.
    entity_type = Column(String(50), nullable=False, index=True)  # "customer", "call", "follow_up", "import", "email"
    entity_id = Column(String(50), nullable=True, index=True)
    status = Column(String(50), default="Success", nullable=True)
    changes = Column(JSON, nullable=True)
    ip_address = Column(String(50), nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    user = relationship("User")
