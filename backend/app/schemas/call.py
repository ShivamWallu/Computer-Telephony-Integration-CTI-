from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional
from datetime import datetime, timezone
from backend.app.schemas.auth import UserOut
from backend.app.schemas.customer import CustomerSearchOut

class IncomingCallWebhook(BaseModel):
    phone_number: str = Field(..., description="Caller phone number in any format")
    call_id: Optional[str] = None
    uuid: Optional[str] = None
    call_to_number: Optional[str] = None
    call_time: Optional[datetime] = None
    start_stamp: Optional[str] = None
    direction: str = "incoming"
    provider: Optional[str] = "smartflo"
    caller_name: Optional[str] = None
    agent_extension: Optional[str] = None
    operator: Optional[str] = None
    circle: Optional[str] = None
    agent_name: Optional[str] = None
    agent_number: Optional[str] = None

class OutgoingCallRequest(BaseModel):
    customer_id: Optional[int] = None
    phone_number: str
    vid: Optional[str] = None
    provider: Optional[str] = "smartflo"
    notes: Optional[str] = None

class CallStatusUpdate(BaseModel):
    call_id: str
    status: str
    duration_seconds: Optional[int] = None
    billsec: Optional[int] = None
    recording_url: Optional[str] = None
    hangup_cause: Optional[str] = None
    reason_key: Optional[str] = None
    hangup_code: Optional[str] = None
    hangup_key: Optional[str] = None
    notes: Optional[str] = None

class CallOut(BaseModel):
    id: int
    call_id: str
    uuid: Optional[str] = None
    call_to_number: Optional[str] = None
    customer_id: Optional[int] = None
    user_id: Optional[int] = None
    phone_number: str
    phone_number_normalized: str
    direction: str
    status: str
    operator: Optional[str] = None
    circle: Optional[str] = None
    agent_name: Optional[str] = None
    agent_number: Optional[str] = None
    hangup_cause: Optional[str] = None
    reason_key: Optional[str] = None
    hangup_code: Optional[str] = None
    hangup_key: Optional[str] = None
    billsec: Optional[int] = 0
    provider: Optional[str] = "smartflo"
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: int
    recording_url: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    customer: Optional[CustomerSearchOut] = None
    user: Optional[UserOut] = None

    @field_validator("start_time", "end_time", "created_at", mode="before")
    @classmethod
    def ensure_utc_timezone(cls, v):
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)
            return v.astimezone(timezone.utc)
        return v

    model_config = ConfigDict(from_attributes=True)

class IncomingCallResponse(BaseModel):
    call_id: str
    uuid: Optional[str] = None
    call_to_number: Optional[str] = None
    phone_number: str
    phone_number_normalized: str
    customer_found: bool
    customer: Optional[CustomerSearchOut] = None
    recent_interactions: Optional[list] = []
    pending_followups: Optional[list] = []
    operator: Optional[str] = None
    circle: Optional[str] = None
    agent_name: Optional[str] = None
    agent_user_id: Optional[int] = None
    assigned_employee_name: Optional[str] = None
    start_stamp: Optional[str] = None
    start_time: Optional[datetime] = None
    provider: Optional[str] = "smartflo"
    message: str
