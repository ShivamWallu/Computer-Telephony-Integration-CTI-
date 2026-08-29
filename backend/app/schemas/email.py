from pydantic import BaseModel, EmailStr, Field, model_validator
from typing import Optional, List, Any
from datetime import datetime

class SendEmailRequest(BaseModel):
    to_email: EmailStr
    cc: Optional[List[EmailStr]] = None
    bcc: Optional[List[EmailStr]] = None
    subject: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1)
    template_name: Optional[str] = None
    customer_id: Optional[int] = None

    @model_validator(mode='before')
    @classmethod
    def map_email_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "to_email" not in data and "recipient_email" in data:
                data["to_email"] = data["recipient_email"]
            if "to_email" not in data and "to" in data:
                data["to_email"] = data["to"]
        return data

class EmailOut(BaseModel):
    id: int
    customer_id: int
    sender_email: str
    recipient_email: str
    subject: str
    body_snippet: str
    status: str  # sent, failed, queued
    sent_at: datetime
