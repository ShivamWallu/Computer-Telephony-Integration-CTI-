from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.app.database import Base

class CustomerInteraction(Base):
    __tablename__ = "customer_interactions"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    interaction_type = Column(String(50), nullable=False, index=True)  # "call", "email", "note", "whatsapp", "meeting", "system", "followup"
    direction = Column(String(20), nullable=True)  # "incoming", "outgoing", "internal"
    subject = Column(String(255), nullable=True)
    content = Column(Text, nullable=True)
    
    # Flexible JSON metadata for channel-specific attributes (duration, email_headers, tags, priority)
    meta_info = Column("metadata", JSON, default=dict)
    
    interaction_time = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    customer = relationship("Customer", back_populates="interactions")
    user = relationship("User", back_populates="interactions")

    __table_args__ = (
        Index("idx_interaction_cust_time", "customer_id", "interaction_time"),
    )
