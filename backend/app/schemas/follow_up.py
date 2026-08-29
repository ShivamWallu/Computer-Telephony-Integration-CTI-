from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, Any
from datetime import datetime
from backend.app.schemas.auth import UserOut
from backend.app.schemas.customer import CustomerSearchOut

class FollowUpBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    due_date: datetime
    priority: str = "Medium"  # Low, Medium, High, Urgent
    status: str = "Pending"   # Pending, In Progress, Completed, Cancelled

    @model_validator(mode='before')
    @classmethod
    def map_followup_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "description" not in data and "notes" in data:
                data["description"] = data["notes"]
        return data

class FollowUpCreate(FollowUpBase):
    customer_id: int
    assigned_user_id: Optional[int] = None

class FollowUpUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    assigned_user_id: Optional[int] = None

class FollowUpOut(FollowUpBase):
    id: int
    customer_id: int
    assigned_user_id: Optional[int] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    customer: Optional[CustomerSearchOut] = None
    assigned_user: Optional[UserOut] = None

    model_config = ConfigDict(from_attributes=True)
