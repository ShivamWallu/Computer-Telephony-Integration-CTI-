from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.app.database import Base

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)

    # 15 Standardized Columns (Exact Order & Names)
    party_code = Column(String(50), unique=True, index=True, nullable=False)        # 1. Party Code
    party_name = Column(String(255), index=True, nullable=False)                     # 2. Party Name
    address_date = Column(String(50), nullable=True)                                 # 3. Address Date
    address_line_1 = Column(String(255), nullable=True)                              # 4. Address Line 1
    address_line_2 = Column(String(255), nullable=True)                              # 5. Address Line 2
    address_line_3 = Column(String(255), nullable=True)                              # 6. Address Line 3
    contact_person_1 = Column(String(255), index=True, nullable=True)                # 7. Contact Person 1
    email_id_1 = Column(String(255), index=True, nullable=True)                      # 8. Email Id 1
    country = Column(String(100), default="India", nullable=True)                    # 9. Country
    state = Column(String(100), index=True, nullable=True)                           # 10. State
    city = Column(String(100), index=True, nullable=True)                            # 11. City
    pincode = Column(String(20), nullable=True)                                      # 12. Pincode
    phone_type_1 = Column(String(50), default="Mobile", nullable=True)               # 13. Phone Type 1
    phone_1 = Column(String(50), nullable=False)                                     # 14. Phone 1 (Primary contact)
    phone_1_normalized = Column(String(50), index=True, nullable=False)             # Indexed for ultra-fast CTI lookup
    status = Column(String(50), default="Active", index=True, nullable=False)        # 15. Status

    # System & CRM Management Fields
    assigned_employee_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    notes = Column(Text, nullable=True)
    is_archived = Column(Boolean, default=False, index=True, nullable=False)

    # Customer Intelligence Fields
    rating = Column(Integer, default=0, index=True, nullable=False)                  # 1-5 Stars (0 = unrated)
    category = Column(String(50), default="Regular", index=True, nullable=False)    # Top Customer, Premium, Regular, New Customer, Potential, Needs Attention
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    assigned_employee = relationship("User", back_populates="assigned_customers")
    interactions = relationship("CustomerInteraction", back_populates="customer", cascade="all, delete-orphan", order_by="desc(CustomerInteraction.interaction_time)")
    calls = relationship("Call", back_populates="customer", cascade="all, delete-orphan", order_by="desc(Call.start_time)")
    follow_ups = relationship("FollowUp", back_populates="customer", cascade="all, delete-orphan", order_by="FollowUp.due_date")
    documents = relationship("CustomerDocument", back_populates="customer", cascade="all, delete-orphan", order_by="desc(CustomerDocument.created_at)")
    additional_phones = relationship("CustomerPhoneNumber", back_populates="customer", cascade="all, delete-orphan", order_by="desc(CustomerPhoneNumber.is_primary)")
    rating_history = relationship("CustomerRatingHistory", back_populates="customer", cascade="all, delete-orphan", order_by="desc(CustomerRatingHistory.created_at)")

    # Backward compatibility properties & aliases
    @property
    def customer_id(self):
        return self.party_code

    @customer_id.setter
    def customer_id(self, val):
        self.party_code = val

    @property
    def name(self):
        return self.party_name

    @name.setter
    def name(self, val):
        self.party_name = val

    @property
    def company(self):
        return self.party_name

    @company.setter
    def company(self, val):
        self.party_name = val

    @property
    def mobile(self):
        return self.phone_1

    @mobile.setter
    def mobile(self, val):
        self.phone_1 = val

    @property
    def mobile_normalized(self):
        return self.phone_1_normalized

    @mobile_normalized.setter
    def mobile_normalized(self, val):
        self.phone_1_normalized = val

    @property
    def email(self):
        return self.email_id_1

    @email.setter
    def email(self, val):
        self.email_id_1 = val

    @property
    def address(self):
        parts = [p for p in [self.address_line_1, self.address_line_2, self.address_line_3] if p]
        return ", ".join(parts) if parts else None

    @address.setter
    def address(self, val):
        self.address_line_1 = val

    @property
    def customer_type(self):
        return "VIP" if self.status == "VIP" else "Standard"

    @customer_type.setter
    def customer_type(self, val):
        pass

    # Multi-column indexes for fast query execution
    __table_args__ = (
        Index("idx_cust_phone1_norm_archived", "phone_1_normalized", "is_archived"),
        Index("idx_cust_search_composite_v2", "party_name", "party_code", "contact_person_1", "email_id_1"),
    )

class CustomerPhoneNumber(Base):
    __tablename__ = "customer_phone_numbers"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    phone_type = Column(String(50), default="Mobile", nullable=False)  # Mobile, Office, WhatsApp, Home, Other
    phone_number = Column(String(50), nullable=False)
    phone_normalized = Column(String(50), index=True, nullable=False)  # Normalized 10 digits for fast lookup
    is_primary = Column(Boolean, default=False, index=True, nullable=False)
    label = Column(String(100), nullable=True)  # Optional label (e.g. Direct Line, Manager)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    customer = relationship("Customer", back_populates="additional_phones")

    __table_args__ = (
        Index("idx_cust_phone_norm_lookup", "phone_normalized"),
        Index("idx_cust_phone_cust_id", "customer_id", "is_primary"),
    )

class CustomerRatingHistory(Base):
    __tablename__ = "customer_rating_history"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    previous_rating = Column(Integer, nullable=True)
    new_rating = Column(Integer, nullable=False)
    previous_category = Column(String(50), nullable=True)
    new_category = Column(String(50), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    customer = relationship("Customer", back_populates="rating_history")
    user = relationship("User")

    __table_args__ = (
        Index("idx_cust_rating_hist_cust", "customer_id", "created_at"),
    )

