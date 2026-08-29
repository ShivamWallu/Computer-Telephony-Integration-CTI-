from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.app.database import Base

class Call(Base):
    __tablename__ = "calls"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(String(100), unique=True, index=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    phone_number = Column(String(50), nullable=False)
    phone_number_normalized = Column(String(50), index=True, nullable=False)
    direction = Column(String(20), nullable=False, default="incoming")  # "incoming", "outgoing"
    status = Column(String(50), nullable=False, default="ringing")      # "ringing", "answered", "completed", "missed", "busy"
    
    # Tata Smartflo Telephony Metadata
    uuid = Column(String(100), index=True, nullable=True)               # Smartflo unique call UUID (e.g. 6a8fc3a2171d7)
    call_to_number = Column(String(50), index=True, nullable=True)      # Dialed Virtual Number / VID (e.g. 918065908541)
    operator = Column(String(100), nullable=True)                       # Operator (e.g. Reliance)
    circle = Column(String(100), nullable=True)                         # Circle / Billing Circle (e.g. Punjab)
    agent_name = Column(String(100), nullable=True)                     # Agent Name from Smartflo (e.g. Pankaj)
    agent_number = Column(String(50), nullable=True)                    # Agent Phone Number (e.g. +917743004676)
    hangup_cause = Column(String(150), nullable=True)                   # Smartflo Hangup Cause (e.g. No user responding)
    reason_key = Column(String(150), nullable=True)                     # Smartflo Reason Key (e.g. Calls dropped)
    hangup_code = Column(String(50), nullable=True)                     # Smartflo Hangup Code (e.g. 18)
    hangup_key = Column(String(100), nullable=True)                     # Smartflo Hangup Key (e.g. NO_USER_RESPONSE)
    billsec = Column(Integer, default=0)                                # Billed seconds
    provider = Column(String(50), default="smartflo")                   # Provider (smartflo, exotel, generic, twilio)

    is_test = Column(Boolean, default=False, nullable=False)
    start_time = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, default=0)
    recording_url = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    customer = relationship("Customer", back_populates="calls")
    user = relationship("User", back_populates="calls")

    __table_args__ = (
        Index("idx_calls_phone_time", "phone_number_normalized", "start_time"),
    )
