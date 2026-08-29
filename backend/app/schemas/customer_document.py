from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from backend.app.schemas.auth import UserOut

class CustomerDocumentBase(BaseModel):
    category: str = "General"
    description: Optional[str] = None

class CustomerDocumentCreate(CustomerDocumentBase):
    pass

class CustomerDocumentOut(CustomerDocumentBase):
    id: int
    customer_id: int
    uploaded_by_user_id: Optional[int] = None
    filename: str
    file_size_bytes: int
    content_type: str
    storage_provider: str
    storage_url: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    uploaded_by: Optional[UserOut] = None

    model_config = ConfigDict(from_attributes=True)

class CustomerDocumentSummary(BaseModel):
    total_documents: int
    categories: dict
