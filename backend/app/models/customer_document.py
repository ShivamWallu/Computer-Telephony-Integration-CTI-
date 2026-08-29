from sqlalchemy import Column, Integer, String, Text, LargeBinary, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.app.database import Base

class CustomerDocument(Base):
    __tablename__ = "customer_documents"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    filename = Column(String(255), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    content_type = Column(String(100), nullable=False)
    category = Column(String(100), default="General", index=True, nullable=False)  # GST Certificate, PAN Card, Aadhaar, Invoice, Contract, KYC, General
    description = Column(String(500), nullable=True)
    
    # Persistent storage abstraction for Vercel / Cloud / Serverless
    storage_provider = Column(String(50), default="database_blob", nullable=False) # database_blob / vercel_blob / s3
    file_data = Column(LargeBinary, nullable=True)                                  # Binary payload for database_blob
    storage_url = Column(String(500), nullable=True)                                # External CDN / S3 / Vercel Blob URL
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    customer = relationship("Customer", back_populates="documents")
    uploaded_by = relationship("User")

    __table_args__ = (
        Index("idx_doc_customer_category", "customer_id", "category"),
    )
