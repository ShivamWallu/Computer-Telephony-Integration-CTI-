from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="employee")  # "admin", "employee"
    allowed_caller_id = Column(String(100), index=True, nullable=True) # Smartflo Allowed Caller ID (e.g. 918065908531)
    vid = Column(String(100), index=True, nullable=True)               # Alias for Virtual DID
    phone = Column(String(50), nullable=True)                          # Agent mobile/phone (e.g. 918146982211)
    agent_id = Column(String(50), nullable=True)                       # Smartflo Agent ID (e.g. 506912000001)
    intercom = Column(String(50), nullable=True)                       # Smartflo Intercom (e.g. 1001)
    designation = Column(String(100), nullable=True)                   # Designation (e.g. Sales, Director, HR manager)
    tcs_username = Column(String(255), nullable=True)                  # Dedicated TCS iON Login Username/Email
    tcs_password = Column(String(255), nullable=True)                  # Dedicated TCS iON Login Password
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    assigned_customers = relationship("Customer", back_populates="assigned_employee")
    interactions = relationship("CustomerInteraction", back_populates="user")
    calls = relationship("Call", back_populates="user")
    follow_ups = relationship("FollowUp", back_populates="assigned_user")
    import_jobs = relationship("ImportJob", back_populates="uploaded_by")
