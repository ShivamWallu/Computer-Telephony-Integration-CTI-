from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator
from typing import Optional, List, Any
from datetime import datetime
from backend.app.schemas.auth import UserOut

class CustomerBase(BaseModel):
    party_code: Optional[str] = None
    party_name: str = Field(..., min_length=1, max_length=255)
    address_date: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    address_line_3: Optional[str] = None
    contact_person_1: Optional[str] = None
    email_id_1: Optional[str] = None
    country: Optional[str] = "India"
    state: Optional[str] = None
    city: Optional[str] = None
    pincode: Optional[str] = None
    phone_type_1: Optional[str] = "Mobile"
    phone_1: str = Field(..., min_length=5, max_length=50)
    status: str = "Active"
    notes: Optional[str] = None
    rating: Optional[int] = 0
    category: Optional[str] = "Regular"

    # Backward compatibility aliases for legacy payload fields
    name: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    address: Optional[str] = None
    customer_id: Optional[str] = None
    customer_type: Optional[str] = "Standard"

    @model_validator(mode="before")
    @classmethod
    def populate_aliases(cls, data: Any):
        if isinstance(data, dict):
            # Map legacy name to party_name if party_name is missing
            if not data.get("party_name") and data.get("name"):
                data["party_name"] = data["name"]
            if not data.get("party_code") and data.get("customer_id"):
                data["party_code"] = data["customer_id"]
            if not data.get("phone_1") and data.get("mobile"):
                data["phone_1"] = data["mobile"]
            if not data.get("email_id_1") and data.get("email"):
                data["email_id_1"] = data["email"]
            if not data.get("address_line_1") and data.get("address"):
                data["address_line_1"] = data["address"]
        return data

class CustomerCreate(CustomerBase):
    assigned_employee_id: Optional[int] = None

class CustomerUpdate(BaseModel):
    party_code: Optional[str] = None
    party_name: Optional[str] = None
    address_date: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    address_line_3: Optional[str] = None
    contact_person_1: Optional[str] = None
    email_id_1: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    pincode: Optional[str] = None
    phone_type_1: Optional[str] = None
    phone_1: Optional[str] = None
    status: Optional[str] = None
    assigned_employee_id: Optional[int] = None
    notes: Optional[str] = None
    rating: Optional[int] = None
    category: Optional[str] = None
    is_archived: Optional[bool] = None

    # Aliases
    name: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    address: Optional[str] = None
    customer_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def populate_aliases(cls, data: Any):
        if isinstance(data, dict):
            if not data.get("party_name") and data.get("name"):
                data["party_name"] = data["name"]
            if not data.get("party_code") and data.get("customer_id"):
                data["party_code"] = data["customer_id"]
            if not data.get("phone_1") and data.get("mobile"):
                data["phone_1"] = data["mobile"]
            if not data.get("email_id_1") and data.get("email"):
                data["email_id_1"] = data["email"]
            if not data.get("address_line_1") and data.get("address"):
                data["address_line_1"] = data["address"]
        return data

class CustomerSearchOut(BaseModel):
    """Ultra-lightweight schema for sub-millisecond search results"""
    id: int
    party_code: str
    party_name: str
    contact_person_1: Optional[str] = None
    email_id_1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    phone_1: str
    phone_1_normalized: str
    status: str
    assigned_employee_name: Optional[str] = None
    match_type: Optional[str] = None
    rating: Optional[int] = 0
    category: Optional[str] = "Regular"

    # Backward compatibility
    customer_id: Optional[str] = None
    name: Optional[str] = None
    company: Optional[str] = None
    mobile: Optional[str] = None
    mobile_normalized: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def sync_aliases(cls, data: Any):
        if hasattr(data, "party_code"):
            data.customer_id = data.party_code
            data.name = data.party_name
            data.company = data.party_name
            data.mobile = data.phone_1
            data.mobile_normalized = data.phone_1_normalized
        elif isinstance(data, dict):
            data["customer_id"] = data.get("party_code") or data.get("customer_id")
            data["name"] = data.get("party_name") or data.get("name")
            data["company"] = data.get("party_name") or data.get("company")
            data["mobile"] = data.get("phone_1") or data.get("mobile")
            data["mobile_normalized"] = data.get("phone_1_normalized") or data.get("mobile_normalized")
        return data

    model_config = ConfigDict(from_attributes=True)

class CustomerPhoneIn(BaseModel):
    phone_number: str = Field(..., min_length=3, max_length=50)
    phone_type: Optional[str] = "Mobile"  # Mobile, Office, WhatsApp, Home, Other
    label: Optional[str] = None
    is_primary: Optional[bool] = False

class CustomerPhoneUpdate(BaseModel):
    phone_number: Optional[str] = None
    phone_type: Optional[str] = None
    label: Optional[str] = None
    is_primary: Optional[bool] = None

class CustomerPhoneOut(BaseModel):
    id: int
    customer_id: int
    phone_number: str
    phone_normalized: str
    phone_type: str
    label: Optional[str] = None
    is_primary: bool
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class CustomerOut(CustomerBase):
    id: int
    party_code: str
    party_name: str
    phone_1: str
    phone_1_normalized: str
    status: str
    assigned_employee_id: Optional[int] = None
    assigned_employee: Optional[UserOut] = None
    is_archived: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    total_calls: Optional[int] = 0
    total_interactions: Optional[int] = 0
    pending_followups: Optional[int] = 0
    phone_numbers: Optional[List[CustomerPhoneOut]] = []

    model_config = ConfigDict(from_attributes=True)

class CustomerListResponse(BaseModel):
    items: List[CustomerOut]
    total: int
    page: int
    limit: int
    total_pages: int
