from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.app.database import Base

class ImportJob(Base):
    __tablename__ = "import_jobs"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    total_rows = Column(Integer, default=0, nullable=False)
    imported_count = Column(Integer, default=0, nullable=False)
    updated_count = Column(Integer, default=0, nullable=False)
    duplicate_count = Column(Integer, default=0, nullable=False)
    error_count = Column(Integer, default=0, nullable=False)
    
    status = Column(String(50), default="completed")  # "processing", "completed", "failed"
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    uploaded_by = relationship("User", back_populates="import_jobs")
    errors = relationship("ImportError", back_populates="import_job", cascade="all, delete-orphan")
    updates = relationship("ImportUpdate", back_populates="import_job", cascade="all, delete-orphan")


class ImportError(Base):
    __tablename__ = "import_errors"

    id = Column(Integer, primary_key=True, index=True)
    import_job_id = Column(Integer, ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    
    row_number = Column(Integer, nullable=False)
    raw_data = Column(JSON, nullable=True)
    error_reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationship
    import_job = relationship("ImportJob", back_populates="errors")


class ImportUpdate(Base):
    __tablename__ = "import_updates"

    id = Column(Integer, primary_key=True, index=True)
    import_job_id = Column(Integer, ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    
    row_number = Column(Integer, nullable=False)
    party_code = Column(String(100), nullable=True, index=True)
    party_name = Column(String(255), nullable=True)
    previous_data = Column(JSON, nullable=True)
    new_data = Column(JSON, nullable=True)
    changed_fields = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationship
    import_job = relationship("ImportJob", back_populates="updates")

