from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime

class CustomerIntelligenceItem(BaseModel):
    id: int
    rank: int
    party_code: str
    party_name: str
    contact_person_1: Optional[str] = None
    email_id_1: Optional[str] = None
    phone_1: str
    city: Optional[str] = None
    state: Optional[str] = None
    rating: int = Field(default=0, ge=0, le=5)
    category: str = "Regular"
    status: str = "Active"
    assigned_employee_id: Optional[int] = None
    assigned_employee_name: Optional[str] = None
    total_calls: Optional[int] = 0
    total_interactions: Optional[int] = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class IntelligenceKPIs(BaseModel):
    total_customers: int
    average_rating: float
    top_customers: int
    premium_customers: int
    regular_customers: int
    new_customers: int
    potential_customers: int
    needs_attention: int

class CustomerIntelligenceListResponse(BaseModel):
    items: List[CustomerIntelligenceItem]
    total: int
    page: int
    limit: int
    total_pages: int
    kpis: IntelligenceKPIs

class CustomerRatingUpdate(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="1 to 5 star rating")
    category: str = Field(..., min_length=1, max_length=50, description="Customer category")
    notes: Optional[str] = Field(None, max_length=500, description="Optional notes or reason for change")

class CustomerRatingHistoryItem(BaseModel):
    id: int
    customer_id: int
    previous_rating: Optional[int] = None
    new_rating: int
    previous_category: Optional[str] = None
    new_category: str
    user_id: Optional[int] = None
    user_name: Optional[str] = "System"
    user_role: Optional[str] = "Admin"
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class CustomerIntelligenceDetail(BaseModel):
    id: int
    party_code: str
    party_name: str
    contact_person_1: Optional[str] = None
    email_id_1: Optional[str] = None
    phone_1: str
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    address_line_3: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    country: Optional[str] = "India"
    rating: int
    category: str
    status: str
    assigned_employee_id: Optional[int] = None
    assigned_employee_name: Optional[str] = None
    total_calls: int = 0
    total_interactions: int = 0
    pending_followups: int = 0
    history: List[CustomerRatingHistoryItem] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class RecentRatingChangeItem(BaseModel):
    id: int
    customer_id: int
    party_code: str
    party_name: str
    phone_1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    previous_rating: Optional[int] = None
    new_rating: int
    previous_category: Optional[str] = None
    new_category: str
    user_id: Optional[int] = None
    user_name: Optional[str] = "System"
    user_role: Optional[str] = "ADMIN"
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
