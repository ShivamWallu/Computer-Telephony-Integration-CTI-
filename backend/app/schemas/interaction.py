from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, Dict, Any
from datetime import datetime
from backend.app.schemas.auth import UserOut

class InteractionBase(BaseModel):
    interaction_type: str = Field(..., description="call, email, note, whatsapp, meeting, system, followup")
    direction: Optional[str] = "internal"
    subject: Optional[str] = None
    content: Optional[str] = None
    meta_info: Optional[Dict[str, Any]] = None
    interaction_time: Optional[datetime] = None

    @model_validator(mode='before')
    @classmethod
    def map_field_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "interaction_type" not in data and "type" in data:
                data["interaction_type"] = data["type"]
            if "content" not in data and "notes" in data:
                data["content"] = data["notes"]
        return data

class InteractionCreate(InteractionBase):
    customer_id: int
    user_id: Optional[int] = None
    create_follow_up: Optional[bool] = False
    follow_up_due_date: Optional[datetime] = None
    follow_up_title: Optional[str] = None
    follow_up_priority: Optional[str] = "Medium"

class InteractionOut(InteractionBase):
    id: int
    customer_id: int
    user_id: Optional[int] = None
    user: Optional[UserOut] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
