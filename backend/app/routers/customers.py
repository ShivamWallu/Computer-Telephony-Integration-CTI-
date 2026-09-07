import math
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, desc, asc
from backend.app.database import get_db
from backend.app.models.customer import Customer
from backend.app.models.user import User
from backend.app.models.interaction import CustomerInteraction
from backend.app.models.call import Call
from backend.app.models.follow_up import FollowUp
from backend.app.schemas.customer import (
    CustomerCreate, CustomerUpdate, CustomerOut, CustomerSearchOut, CustomerListResponse, AssignCustomerRequest
)
from backend.app.services.search_service import SearchService
from backend.app.services.phone_normalizer import PhoneNormalizer
from backend.app.services.audit_service import AuditService
from backend.app.services.email_service import EmailService
from backend.app.services.excel_service import ExcelService
from backend.app.utils.security import get_current_user, get_current_admin_user


router = APIRouter(prefix="/customers", tags=["Customers"])

@router.get("/search")
def search_customers(
    q: str = Query(..., min_length=1, description="Phone, Party Name, Contact Person, Email, or Party Code"),
    limit: int = Query(15, ge=1, le=50),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Ultra-Fast prioritized customer search for live incoming call identification.
    Returns matched results and execution latency in milliseconds.
    """
    results, elapsed_ms = SearchService.search_customers(db, q, limit=limit, user=current_user)
    if response:
        response.headers["X-Search-Latency-Ms"] = str(elapsed_ms)
    return {
        "query": q,
        "latency_ms": elapsed_ms,
        "count": len(results),
        "results": results
    }

@router.get("", response_model=CustomerListResponse)
def list_customers(
    page: int = Query(1, ge=1),
    limit: int = Query(15, ge=1, le=500),
    status: Optional[str] = None,
    customer_type: Optional[str] = None,
    category: Optional[str] = None,
    assigned_employee_id: Optional[int] = None,
    assigned_role: Optional[str] = None,
    search: Optional[str] = None,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List and filter customers with pagination and category permissions."""
    query = db.query(Customer).options(
        joinedload(Customer.assigned_employee)
    )

    if not include_archived:
        query = query.filter(Customer.is_archived == False)

    # Scoping by employee permissions
    if current_user.role == "employee":
        if not getattr(current_user, "can_view_unassigned", True) and assigned_employee_id in (-1, 0):
            raise HTTPException(status_code=403, detail="You do not have permission to view the unassigned customer pool.")

        if current_user.allowed_categories:
            import json
            try:
                allowed = json.loads(current_user.allowed_categories) if isinstance(current_user.allowed_categories, str) else current_user.allowed_categories
                if allowed and "*" not in allowed:
                    query = query.filter(Customer.category.in_(allowed))
            except Exception:
                pass

    if assigned_employee_id is not None:
        if assigned_employee_id in (-1, 0):
            emp_ids = [u.id for u in db.query(User.id).filter(User.is_active == True, User.role == "employee").all()]
            if emp_ids:
                query = query.filter(or_(Customer.assigned_employee_id == None, ~Customer.assigned_employee_id.in_(emp_ids)))
        else:
            query = query.filter(Customer.assigned_employee_id == assigned_employee_id)
    elif assigned_role:
        query = query.join(Customer.assigned_employee).filter(User.role == assigned_role)

    if status:
        query = query.filter(Customer.status == status)

    if category:
        query = query.filter(Customer.category == category)

    if search:
        s = f"%{search.strip()}%"
        digits = PhoneNormalizer.clean_digits(search)
        query = query.filter(
            or_(
                Customer.party_name.ilike(s),
                Customer.party_code.ilike(s),
                Customer.contact_person_1.ilike(s),
                Customer.email_id_1.ilike(s),
                Customer.city.ilike(s),
                Customer.phone_1.like(s),
                Customer.phone_1_normalized.like(f"%{digits}%") if digits else False
            )
        )

    total = query.count()
    items = (
        query.order_by(desc(Customer.updated_at))
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    out_items = [CustomerOut.model_validate(c) for c in items]

    return CustomerListResponse(
        items=out_items,
        total=total,
        page=page,
        limit=limit,
        total_pages=math.ceil(total / limit) if total > 0 else 1
    )

@router.get("/purge-preview")
def purge_preview(
    category: Optional[str] = Query(None, description="Category to inspect or None for all"),
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Admin-only: Preview count of customers that would be purged for selected scope."""
    cat_clean = (category or "").strip()
    is_all = not cat_clean or cat_clean.upper() in ["ALL", "*"]
    
    protected_phone_norm = "7814749816"
    query = db.query(Customer).filter(
        ~Customer.phone_1_normalized.like(f"%{protected_phone_norm}%"),
        ~Customer.party_name.ilike("%shivam%")
    )
    if not is_all:
        query = query.filter(Customer.category == cat_clean)
        
    count = query.count()
    norm_tag = cat_clean.upper().replace(" ", "-") if not is_all else "ALL"
    expected_phrase = f"DELETE-{norm_tag}"
    
    return {
        "category": cat_clean if not is_all else "ALL",
        "is_all": is_all,
        "customer_count": count,
        "expected_confirmation": expected_phrase
    }

@router.delete("/purge-all")
def purge_all_customers(
    confirmation: Optional[str] = Query(None, description="Must match required confirmation phrase"),
    confirm_phrase: Optional[str] = Query(None, description="Alternative param name"),
    category: Optional[str] = Query(None, description="Specific Business Category to purge (or None for ALL)"),
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Admin-only: Permanently delete customers individually by Business Category or across all categories,
    EXCEPT the protected demo customer: Shivam (Phone: 7814749816).
    """
    phrase = (confirmation or confirm_phrase or "").strip().upper()
    cat_clean = (category or "").strip()
    is_all = not cat_clean or cat_clean.upper() in ["ALL", "*"]
    
    norm_tag = cat_clean.upper().replace(" ", "-") if not is_all else "ALL"
    expected_phrase = f"DELETE-{norm_tag}"

    if phrase != expected_phrase:
        raise HTTPException(
            status_code=400,
            detail=f"Confirmation phrase '{expected_phrase}' is required to execute permanent deletion."
        )

    protected_phone_norm = "7814749816"

    query = db.query(Customer).filter(
        ~Customer.phone_1_normalized.like(f"%{protected_phone_norm}%"),
        ~Customer.party_name.ilike("%shivam%")
    )

    if not is_all:
        query = query.filter(Customer.category == cat_clean)

    customers_to_delete = query.all()
    deleted_count = len(customers_to_delete)
    
    for cust in customers_to_delete:
        db.delete(cust)

    db.commit()

    action_label = f"CATEGORY_{norm_tag}_PURGED" if not is_all else "ALL_CUSTOMERS_PURGED"
    AuditService.log(
        db,
        action=action_label,
        entity_type="customer",
        changes={"purged_count": deleted_count, "category": cat_clean if not is_all else "ALL", "preserved": "Shivam (7814749816)"},
        user=admin_user
    )

    scope_name = f"category '{cat_clean}'" if not is_all else "all categories"
    return {
        "status": "success",
        "category": cat_clean if not is_all else "ALL",
        "purged_customers": deleted_count,
        "deleted_customers": deleted_count,
        "message": f"Successfully deleted {deleted_count} customer records in {scope_name}. Demo account 'Shivam' (7814749816) was safely preserved.",
        "protected_customer_preserved": True
    }

@router.get("/export")
def export_customers(
    format: str = Query("xlsx", description="xlsx or csv"),
    status: Optional[str] = None,
    category: Optional[str] = None,
    assigned_employee_id: Optional[int] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Export all customer records to official Excel (.xlsx) or CSV (.csv).
    Includes all 25 master columns, intelligence category, rating, and assigned agent.
    """
    if current_user.role != "admin" and not getattr(current_user, "can_export_data", True):
        raise HTTPException(status_code=403, detail="You do not have permission to export customer data.")

    from backend.app.services.excel_service import ExcelService
    from datetime import datetime

    query = db.query(Customer).options(
        joinedload(Customer.assigned_employee)
    ).filter(Customer.is_archived == False)

    if current_user.role == "employee" and current_user.allowed_categories:
        import json
        try:
            allowed = json.loads(current_user.allowed_categories) if isinstance(current_user.allowed_categories, str) else current_user.allowed_categories
            if allowed and "*" not in allowed:
                query = query.filter(Customer.category.in_(allowed))
        except Exception:
            pass

    if assigned_employee_id is not None:
        if assigned_employee_id in (-1, 0):
            emp_ids = [u.id for u in db.query(User.id).filter(User.is_active == True, User.role == "employee").all()]
            if emp_ids:
                query = query.filter(or_(Customer.assigned_employee_id == None, ~Customer.assigned_employee_id.in_(emp_ids)))
        else:
            query = query.filter(Customer.assigned_employee_id == assigned_employee_id)

    if status:
        query = query.filter(Customer.status == status)

    if category:
        query = query.filter(Customer.category == category)

    if search:
        s = f"%{search.strip()}%"
        digits = PhoneNormalizer.clean_digits(search)
        query = query.filter(
            or_(
                Customer.party_name.ilike(s),
                Customer.party_code.ilike(s),
                Customer.contact_person_1.ilike(s),
                Customer.email_id_1.ilike(s),
                Customer.city.ilike(s),
                Customer.phone_1.like(s),
                Customer.phone_1_normalized.like(f"%{digits}%") if digits else False
            )
        )

    customers = query.order_by(desc(Customer.updated_at)).all()
    timestamp_str = datetime.now().strftime("%Y-%m-%d")

    if format.lower() == "csv":
        file_bytes = ExcelService.generate_customers_csv_bytes(customers)
        filename = f"Khandelia_Customers_Directory_{timestamp_str}.csv"
        media_type = "text/csv; charset=utf-8"
    else:
        file_bytes = ExcelService.generate_customers_excel_bytes(customers)
        filename = f"Khandelia_Customers_Directory_{timestamp_str}.xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )

from backend.app.models.customer import Customer, CustomerPhoneNumber
from backend.app.schemas.customer import (
    CustomerCreate, CustomerUpdate, CustomerOut, CustomerSearchOut, CustomerListResponse,
    CustomerPhoneIn, CustomerPhoneUpdate, CustomerPhoneOut
)

def get_customer_all_phones(customer: Customer) -> List[CustomerPhoneOut]:
    """Compile primary phone and all additional phone numbers for a customer."""
    phones = [
        CustomerPhoneOut(
            id=0,  # 0 indicates primary customer table record
            customer_id=customer.id,
            phone_number=customer.phone_1,
            phone_normalized=customer.phone_1_normalized,
            phone_type=customer.phone_type_1 or "Mobile",
            label="Primary Contact",
            is_primary=True,
            created_at=customer.created_at
        )
    ]
    if hasattr(customer, "additional_phones") and customer.additional_phones:
        for p in customer.additional_phones:
            phones.append(CustomerPhoneOut.model_validate(p))
    return phones

@router.get("/{id}", response_model=CustomerOut)
def get_customer(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch complete customer details by ID with all phone numbers and stats."""
    customer = (
        db.query(Customer)
        .options(
            joinedload(Customer.assigned_employee),
            joinedload(Customer.additional_phones)
        )
        .filter(Customer.id == id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    out = CustomerOut.model_validate(customer)
    out.phone_numbers = get_customer_all_phones(customer)
    out.total_calls = db.query(Call).filter(Call.customer_id == id).count()
    out.total_interactions = db.query(CustomerInteraction).filter(CustomerInteraction.customer_id == id).count()
    out.pending_followups = db.query(FollowUp).filter(
        FollowUp.customer_id == id,
        FollowUp.status.in_(["Pending", "In Progress"])
    ).count()
    return out

@router.get("/{id}/phones", response_model=List[CustomerPhoneOut])
def get_customer_phones(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all primary and additional phone numbers for a customer."""
    customer = db.query(Customer).options(joinedload(Customer.additional_phones)).filter(Customer.id == id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return get_customer_all_phones(customer)

@router.post("/{id}/phones", response_model=List[CustomerPhoneOut], status_code=status.HTTP_201_CREATED)
def add_customer_phone(
    id: int,
    phone_in: CustomerPhoneIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add a new phone number (Mobile, Office, WhatsApp, Home, Other) to customer."""
    customer = db.query(Customer).options(joinedload(Customer.additional_phones)).filter(Customer.id == id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    raw_phone = phone_in.phone_number.strip()
    norm_phone = PhoneNormalizer.normalize(raw_phone)
    if not norm_phone or len(norm_phone) < 3:
        raise HTTPException(status_code=400, detail="A valid phone number is required")

    # Duplicate check on this customer
    all_existing_norms = [customer.phone_1_normalized] + [p.phone_normalized for p in customer.additional_phones]
    if norm_phone in all_existing_norms:
        raise HTTPException(status_code=400, detail=f"Phone number '{raw_phone}' is already saved for this customer")

    if phone_in.is_primary:
        # Move current primary phone to additional phones
        old_primary = CustomerPhoneNumber(
            customer_id=customer.id,
            phone_type=customer.phone_type_1 or "Mobile",
            phone_number=customer.phone_1,
            phone_normalized=customer.phone_1_normalized,
            label="Previous Primary",
            is_primary=False
        )
        db.add(old_primary)

        # Update customer primary phone
        customer.phone_1 = raw_phone
        customer.phone_1_normalized = norm_phone
        customer.phone_type_1 = phone_in.phone_type or "Mobile"
    else:
        new_phone = CustomerPhoneNumber(
            customer_id=customer.id,
            phone_type=phone_in.phone_type or "Mobile",
            phone_number=raw_phone,
            phone_normalized=norm_phone,
            label=phone_in.label or f"{phone_in.phone_type or 'Additional'} Number",
            is_primary=False
        )
        db.add(new_phone)

    db.commit()
    db.refresh(customer)

    AuditService.log(
        db,
        action="CUSTOMER_PHONE_ADDED",
        entity_type="customer",
        entity_id=str(customer.id),
        changes={"phone_number": raw_phone, "type": phone_in.phone_type, "is_primary": phone_in.is_primary},
        user=current_user
    )

    return get_customer_all_phones(customer)

@router.put("/{id}/phones/{phone_id}", response_model=List[CustomerPhoneOut])
def update_customer_phone(
    id: int,
    phone_id: int,
    phone_in: CustomerPhoneUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Edit an existing customer phone number or label/type."""
    customer = db.query(Customer).options(joinedload(Customer.additional_phones)).filter(Customer.id == id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    if phone_id == 0:
        # Update primary phone on Customer model
        if phone_in.phone_number:
            raw = phone_in.phone_number.strip()
            norm = PhoneNormalizer.normalize(raw)
            if not norm:
                raise HTTPException(status_code=400, detail="Invalid phone number")
            customer.phone_1 = raw
            customer.phone_1_normalized = norm
        if phone_in.phone_type:
            customer.phone_type_1 = phone_in.phone_type
    else:
        phone_record = db.query(CustomerPhoneNumber).filter(
            CustomerPhoneNumber.id == phone_id,
            CustomerPhoneNumber.customer_id == id
        ).first()
        if not phone_record:
            raise HTTPException(status_code=404, detail="Phone record not found")

        if phone_in.phone_number:
            raw = phone_in.phone_number.strip()
            norm = PhoneNormalizer.normalize(raw)
            if not norm:
                raise HTTPException(status_code=400, detail="Invalid phone number")
            phone_record.phone_number = raw
            phone_record.phone_normalized = norm
        if phone_in.phone_type:
            phone_record.phone_type = phone_in.phone_type
        if phone_in.label is not None:
            phone_record.label = phone_in.label

    db.commit()
    db.refresh(customer)
    return get_customer_all_phones(customer)

@router.delete("/{id}/phones/{phone_id}", response_model=List[CustomerPhoneOut])
def delete_customer_phone(
    id: int,
    phone_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an additional phone number from a customer."""
    if phone_id == 0:
        raise HTTPException(status_code=400, detail="Cannot delete Primary phone number directly. Set another number as Primary first.")

    phone_record = db.query(CustomerPhoneNumber).filter(
        CustomerPhoneNumber.id == phone_id,
        CustomerPhoneNumber.customer_id == id
    ).first()
    if not phone_record:
        raise HTTPException(status_code=404, detail="Phone record not found")

    db.delete(phone_record)
    db.commit()

    customer = db.query(Customer).options(joinedload(Customer.additional_phones)).filter(Customer.id == id).first()
    return get_customer_all_phones(customer)

@router.put("/{id}/phones/{phone_id}/primary", response_model=List[CustomerPhoneOut])
def set_primary_customer_phone(
    id: int,
    phone_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Set an additional phone number as the Primary number for the customer."""
    if phone_id == 0:
        return get_customer_all_phones(db.query(Customer).filter(Customer.id == id).first())

    customer = db.query(Customer).options(joinedload(Customer.additional_phones)).filter(Customer.id == id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    target_phone = db.query(CustomerPhoneNumber).filter(
        CustomerPhoneNumber.id == phone_id,
        CustomerPhoneNumber.customer_id == id
    ).first()
    if not target_phone:
        raise HTTPException(status_code=404, detail="Phone record not found")

    # Swap: old primary values become the target_phone record, and target_phone values become customer.phone_1
    old_phone_num = customer.phone_1
    old_phone_norm = customer.phone_1_normalized
    old_phone_type = customer.phone_type_1 or "Mobile"

    customer.phone_1 = target_phone.phone_number
    customer.phone_1_normalized = target_phone.phone_normalized
    customer.phone_type_1 = target_phone.phone_type

    target_phone.phone_number = old_phone_num
    target_phone.phone_normalized = old_phone_norm
    target_phone.phone_type = old_phone_type
    target_phone.label = f"Secondary ({old_phone_type})"
    target_phone.is_primary = False

    db.commit()
    db.refresh(customer)

    AuditService.log(
        db,
        action="CUSTOMER_PRIMARY_PHONE_CHANGED",
        entity_type="customer",
        entity_id=str(customer.id),
        changes={"new_primary_phone": customer.phone_1},
        user=current_user
    )

    return get_customer_all_phones(customer)

@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(
    customer_in: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new customer with normalized phone numbers and duplicate prevention."""
    raw_phone = customer_in.phone_1 or customer_in.mobile
    raw_name = customer_in.party_name or customer_in.name
    raw_code = customer_in.party_code or customer_in.customer_id

    if not raw_name:
        raise HTTPException(status_code=400, detail="Party Name is required")
    if not raw_phone:
        raise HTTPException(status_code=400, detail="Phone 1 is required")

    phone_norm = PhoneNormalizer.normalize(raw_phone)
    if not phone_norm:
        raise HTTPException(status_code=400, detail="A valid Phone 1 number is required")

    # Duplicate check
    existing = db.query(Customer).filter(
        Customer.phone_1_normalized == phone_norm,
        Customer.is_archived == False
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Customer with phone '{raw_phone}' already exists ({existing.party_name}, Code: {existing.party_code})"
        )

    # Generate party_code if not provided
    if not raw_code:
        total_cust = db.query(Customer).count() + 1001
        raw_code = f"CUST-{total_cust}"

    new_cust = Customer(
        party_code=raw_code,
        party_name=raw_name,
        address_date=customer_in.address_date,
        address_line_1=customer_in.address_line_1 or customer_in.address,
        address_line_2=customer_in.address_line_2,
        address_line_3=customer_in.address_line_3,
        country=customer_in.country or "India",
        state=customer_in.state,
        district=customer_in.district,
        city=customer_in.city,
        pincode=customer_in.pincode,
        zone=customer_in.zone,
        company_website=customer_in.company_website,
        sales_region_code=customer_in.sales_region_code,
        contact_person_1=customer_in.contact_person_1 or raw_name,
        email_id_1=customer_in.email_id_1 or customer_in.email,
        phone_type_1=customer_in.phone_type_1 or "Mobile",
        phone_1=raw_phone,
        phone_1_normalized=phone_norm,
        contact_person_2=customer_in.contact_person_2,
        email_id_2=customer_in.email_id_2,
        contact_person_3=customer_in.contact_person_3,
        email_id_3=customer_in.email_id_3,
        status=customer_in.status or "Active",
        category=customer_in.category or "General",
        assigned_employee_id=customer_in.assigned_employee_id or current_user.id,
        notes=customer_in.notes,
        is_archived=False
    )
    db.add(new_cust)
    db.flush()

    # Sync Phone 2 & Phone 3 if provided
    if customer_in.phone_2 or customer_in.phone_3:
        ExcelService._sync_customer_secondary_phones(db, new_cust.id, customer_in.phone_2, customer_in.phone_3, phone_norm)

    db.commit()
    db.refresh(new_cust)

    # Log initial interaction and audit log
    init_interaction = CustomerInteraction(
        customer_id=new_cust.id,
        user_id=current_user.id,
        interaction_type="system",
        direction="internal",
        subject="Customer Profile Created",
        content=f"Customer account created by {current_user.full_name}."
    )
    db.add(init_interaction)

    AuditService.log(
        db,
        action="CUSTOMER_CREATED",
        entity_type="customer",
        entity_id=str(new_cust.id),
        changes={"party_code": new_cust.party_code, "party_name": new_cust.party_name, "phone_1": new_cust.phone_1},
        user=current_user
    )

    out = CustomerOut.model_validate(new_cust)
    out.phone_numbers = get_customer_all_phones(new_cust)
    return out

@router.put("/{id}", response_model=CustomerOut)
def update_customer(
    id: int,
    update_in: CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update customer details across all 25 master enterprise fields."""
    customer = db.query(Customer).options(joinedload(Customer.additional_phones)).filter(Customer.id == id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    changes = {}
    new_name = update_in.party_name or update_in.name
    if new_name is not None and new_name != customer.party_name:
        changes["party_name"] = {"old": customer.party_name, "new": new_name}
        customer.party_name = new_name

    new_code = update_in.party_code or update_in.customer_id
    if new_code is not None and new_code != customer.party_code:
        changes["party_code"] = {"old": customer.party_code, "new": new_code}
        customer.party_code = new_code

    new_phone = update_in.phone_1 or update_in.mobile
    if new_phone is not None and new_phone != customer.phone_1:
        norm = PhoneNormalizer.normalize(new_phone)
        changes["phone_1"] = {"old": customer.phone_1, "new": new_phone}
        customer.phone_1 = new_phone
        customer.phone_1_normalized = norm

    if update_in.address_date is not None:
        customer.address_date = update_in.address_date
    if update_in.address_line_1 is not None or update_in.address is not None:
        customer.address_line_1 = update_in.address_line_1 or update_in.address
    if update_in.address_line_2 is not None:
        customer.address_line_2 = update_in.address_line_2
    if update_in.address_line_3 is not None:
        customer.address_line_3 = update_in.address_line_3
    if update_in.contact_person_1 is not None:
        customer.contact_person_1 = update_in.contact_person_1
    if update_in.email_id_1 is not None or update_in.email is not None:
        customer.email_id_1 = update_in.email_id_1 or update_in.email
    if update_in.country is not None:
        customer.country = update_in.country
    if update_in.state is not None:
        customer.state = update_in.state
    if update_in.district is not None:
        customer.district = update_in.district
    if update_in.city is not None:
        customer.city = update_in.city
    if update_in.pincode is not None:
        customer.pincode = update_in.pincode
    if update_in.zone is not None:
        customer.zone = update_in.zone
    if update_in.company_website is not None:
        customer.company_website = update_in.company_website
    if update_in.sales_region_code is not None:
        customer.sales_region_code = update_in.sales_region_code
    if update_in.contact_person_2 is not None:
        customer.contact_person_2 = update_in.contact_person_2
    if update_in.email_id_2 is not None:
        customer.email_id_2 = update_in.email_id_2
    if update_in.contact_person_3 is not None:
        customer.contact_person_3 = update_in.contact_person_3
    if update_in.email_id_3 is not None:
        customer.email_id_3 = update_in.email_id_3
    if update_in.phone_type_1 is not None:
        customer.phone_type_1 = update_in.phone_type_1
    if update_in.status is not None:
        customer.status = update_in.status
    if update_in.category is not None:
        changes["category"] = {"old": customer.category, "new": update_in.category}
        customer.category = update_in.category
    old_assigned_employee_id = customer.assigned_employee_id
    if update_in.assigned_employee_id is not None:
        customer.assigned_employee_id = update_in.assigned_employee_id
    if update_in.notes is not None:
        customer.notes = update_in.notes
    if update_in.is_archived is not None:
        customer.is_archived = update_in.is_archived

    if update_in.phone_2 is not None or update_in.phone_3 is not None:
        ExcelService._sync_customer_secondary_phones(db, customer.id, update_in.phone_2, update_in.phone_3, customer.phone_1_normalized)

    db.commit()
    db.refresh(customer)

    # If assigned employee changed via update, trigger email notification
    if update_in.assigned_employee_id is not None and update_in.assigned_employee_id != old_assigned_employee_id:
        emp = db.query(User).filter(User.id == update_in.assigned_employee_id).first()
        if emp:
            try:
                EmailService.send_assignment_notification(
                    employee_email=emp.email,
                    employee_name=emp.full_name,
                    customer_name=customer.party_name,
                    customer_code=customer.party_code,
                    customer_phone=customer.phone_1,
                    assigned_by=current_user.full_name,
                    instruction_notes=update_in.notes,
                    priority_level="Special Attention"
                )
            except Exception as e:
                print(f"Error sending assignment email on update: {e}")

    AuditService.log(
        db,
        action="CUSTOMER_UPDATED",
        entity_type="customer",
        entity_id=str(customer.id),
        changes=changes,
        user=current_user
    )

    out = CustomerOut.model_validate(customer)
    out.phone_numbers = get_customer_all_phones(customer)
    return out

@router.post("/{id}/assign", response_model=CustomerOut)
def assign_customer(
    id: int,
    assign_in: AssignCustomerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Assign or re-assign customer to an employee with optional instruction notes and priority level.
    Sends automated priority email notification via SMTP.
    """
    customer = db.query(Customer).options(
        joinedload(Customer.assigned_employee),
        joinedload(Customer.additional_phones)
    ).filter(Customer.id == id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    employee = db.query(User).filter(User.id == assign_in.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    old_employee_id = customer.assigned_employee_id
    customer.assigned_employee_id = employee.id

    # Append note if provided
    if assign_in.instruction_notes and assign_in.instruction_notes.strip():
        new_note = f"[{assign_in.priority_level or 'High Attention'}] {assign_in.instruction_notes.strip()}"
        if customer.notes:
            customer.notes = f"{new_note}\n\n---\n{customer.notes}"
        else:
            customer.notes = new_note

    # Create a timeline interaction log
    interaction = CustomerInteraction(
        customer_id=customer.id,
        user_id=current_user.id,
        interaction_type="note",
        direction="internal",
        subject=f"🎯 Assigned to {employee.full_name} ({assign_in.priority_level or 'High Attention'})",
        content=(
            f"Assigned by {current_user.full_name}.\n"
            f"Priority: {assign_in.priority_level or 'High Attention'}\n"
            f"Instructions: {assign_in.instruction_notes.strip() if assign_in.instruction_notes else 'Pay special focus and high attention to this customer profile.'}"
        ),
        meta_info={
            "assigned_by": current_user.full_name,
            "assigned_to": employee.full_name,
            "priority": assign_in.priority_level or "High Attention",
            "notes": assign_in.instruction_notes
        }
    )
    db.add(interaction)
    db.commit()
    db.refresh(customer)

    # Send email notification
    try:
        EmailService.send_assignment_notification(
            employee_email=employee.email,
            employee_name=employee.full_name,
            customer_name=customer.party_name,
            customer_code=customer.party_code,
            customer_phone=customer.phone_1,
            assigned_by=current_user.full_name,
            instruction_notes=assign_in.instruction_notes,
            priority_level=assign_in.priority_level or "High Attention"
        )
    except Exception as e:
        print(f"Failed to send assignment notification email: {e}")

    AuditService.log(
        db,
        action="CUSTOMER_ASSIGNED",
        entity_type="customer",
        entity_id=str(customer.id),
        changes={
            "old_employee_id": old_employee_id,
            "new_employee_id": employee.id,
            "employee_name": employee.full_name,
            "priority": assign_in.priority_level
        },
        user=current_user
    )

    out = CustomerOut.model_validate(customer)
    out.phone_numbers = get_customer_all_phones(customer)
    return out


@router.delete("/{id}", status_code=status.HTTP_200_OK)
def delete_customer(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Admin-only: Safely soft-archive a customer."""
    customer = db.query(Customer).filter(Customer.id == id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer.is_archived = True
    db.commit()

    AuditService.log(
        db,
        action="CUSTOMER_ARCHIVED",
        entity_type="customer",
        entity_id=str(customer.id),
        changes={"party_name": customer.party_name, "party_code": customer.party_code},
        user=current_user
    )

    return {"status": "success", "message": f"Customer '{customer.party_name}' has been archived."}

@router.get("/{id}/timeline")
def get_customer_timeline(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve full chronological unified timeline of calls, emails, notes, and follow-ups.
    Features:
    - Real-time call logs with recording player links & accurate durations
    - Sent emails via SMTP
    - User interaction notes
    - Strictly sorted in descending order (newest -> oldest)
    - Zero duplicate entries
    """
    customer = db.query(Customer).filter(Customer.id == id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    timeline_items = []
    seen_call_sids = set()

    # 1. Authoritative Calls (Linked by customer_id or matching normalized phone)
    from sqlalchemy import or_
    call_query = db.query(Call).options(joinedload(Call.user)).filter(
        or_(
            Call.customer_id == id,
            (Call.phone_number_normalized == customer.phone_1_normalized) if customer.phone_1_normalized else False,
            (Call.phone_number == customer.phone_1) if customer.phone_1 else False
        )
    )
    calls = call_query.all()

    for call in calls:
        if call.call_id:
            seen_call_sids.add(str(call.call_id).strip())
        direction = (call.direction or "incoming").capitalize()
        status = (call.status or "completed").capitalize()
        duration_formatted = f"{call.duration_seconds // 60:02d}:{call.duration_seconds % 60:02d}"
        iso_time = call.start_time.isoformat() if call.start_time else None

        timeline_items.append({
            "id": f"call_{call.id}",
            "type": "call",
            "direction": call.direction or "incoming",
            "title": f"📞 {direction} Call ({status})",
            "content": call.notes or f"Call duration: {duration_formatted} (Status: {status})",
            "description": call.notes or f"Call duration: {duration_formatted} (Status: {status})",
            "time": iso_time,
            "timestamp": iso_time,
            "user_name": call.user.full_name if call.user else "System",
            "meta": {
                "call_id": call.call_id or f"CALL-{call.id}",
                "duration": duration_formatted,
                "duration_seconds": call.duration_seconds,
                "status": status,
                "direction": call.direction,
                "phone": call.phone_number,
                "recording_url": call.recording_url
            }
        })

    # 2. Interactions (Emails, Notes, WhatsApp, Meetings) - Deduplicated from calls
    interactions = (
        db.query(CustomerInteraction)
        .options(joinedload(CustomerInteraction.user))
        .filter(CustomerInteraction.customer_id == id)
        .all()
    )
    for inter in interactions:
        # Prevent duplicate entries if a call already logged this via Call model
        inter_call_id = str(inter.meta_info.get("call_id") or "").strip() if inter.meta_info else ""
        if inter.interaction_type == "call" and (inter_call_id in seen_call_sids or not inter.subject):
            continue

        iso_time = inter.interaction_time.isoformat() if inter.interaction_time else None
        timeline_items.append({
            "id": f"inter_{inter.id}",
            "type": inter.interaction_type,
            "direction": inter.direction or "internal",
            "title": inter.subject or f"{inter.interaction_type.title()} Logged",
            "content": inter.content or "No details recorded",
            "description": inter.content or "No details recorded",
            "time": iso_time,
            "timestamp": iso_time,
            "user_name": inter.user.full_name if inter.user else "System",
            "meta": inter.meta_info or {}
        })

    # 3. Follow-up Tasks
    followups = (
        db.query(FollowUp)
        .options(joinedload(FollowUp.assigned_user))
        .filter(FollowUp.customer_id == id)
        .all()
    )
    for fu in followups:
        iso_created = fu.created_at.isoformat() if fu.created_at else (fu.due_date.isoformat() if fu.due_date else None)
        iso_due = fu.due_date.isoformat() if fu.due_date else None
        timeline_items.append({
            "id": f"fu_{fu.id}",
            "type": "followup",
            "direction": "internal",
            "title": f"⏰ Follow-up: {fu.title} ({fu.status})",
            "content": fu.description or f"Scheduled due: {iso_due} (Priority: {fu.priority})",
            "description": fu.description or f"Scheduled due: {iso_due} (Priority: {fu.priority})",
            "time": iso_created,
            "timestamp": iso_created,
            "user_name": fu.assigned_user.full_name if fu.assigned_user else "System",
            "meta": {
                "priority": fu.priority,
                "status": fu.status,
                "due_date": iso_due,
                "created_at": iso_created
            }
        })

    # 4. Strictly sort descending: newest timestamp first
    timeline_items.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

    return {
        "customer_id": id,
        "party_name": customer.party_name,
        "party_code": customer.party_code,
        "total_events": len(timeline_items),
        "timeline": timeline_items
    }
