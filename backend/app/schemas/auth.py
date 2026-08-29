from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    email: str
    full_name: str
    role: str = "employee"
    allowed_caller_id: Optional[str] = None
    vid: Optional[str] = None
    phone: Optional[str] = None
    agent_id: Optional[str] = None
    intercom: Optional[str] = None
    designation: Optional[str] = None
    is_active: bool = True

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    allowed_caller_id: Optional[str] = None
    vid: Optional[str] = None
    phone: Optional[str] = None
    agent_id: Optional[str] = None
    intercom: Optional[str] = None
    designation: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

class UserOut(UserBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class LoginRequest(BaseModel):
    email: str  # Accepts Allowed Caller ID, Phone Number, Email, or Username
    password: str

class UserRegister(BaseModel):
    full_name: str
    email: str
    password: str
    allowed_caller_id: Optional[str] = None
    phone: Optional[str] = None

class SwitchAccountRequest(BaseModel):
    email: Optional[str] = None
    user_id: Optional[int] = None
    allowed_caller_id: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
