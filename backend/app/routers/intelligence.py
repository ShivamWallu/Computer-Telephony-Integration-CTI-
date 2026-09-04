import math
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, desc, asc, func
from datetime import datetime, timezone

from backend.app.database import get_db
from backend.app.models.customer import Customer, CustomerRatingHistory
from backend.app.models.user import User
from backend.app.models.call import Call
from backend.app.models.interaction import CustomerInteraction
from backend.app.models.follow_up import FollowUp
from backend.app.schemas.intelligence import (
    CustomerIntelligenceItem,
    CustomerIntelligenceListResponse,
    CustomerRatingUpdate,
    CustomerRatingHistoryItem,
    CustomerIntelligenceDetail,
    IntelligenceKPIs,
    RecentRatingChangeItem
)
from backend.app.services.phone_normalizer import PhoneNormalizer
from backend.app.services.audit_service import AuditService
from backend.app.services.cti_service import broadcast_manager
from backend.app.utils.security import get_current_user

router = APIRouter(prefix="/intelligence", tags=["Customer Intelligence"])

VALID_CATEGORIES = {
    "Top Customer",
    "Premium",
    "Regular",
    "New Customer",
    "Potential",
    "Needs Attention"
}

def get_intelligence_kpis(db: Session) -> IntelligenceKPIs:
    """Compute aggregate Customer Intelligence KPIs across active customers."""
    base = db.query(Customer).filter(Customer.is_archived == False)
    total = base.count()
    
    # Calculate average rating (excluding 0/unrated)
    avg_tuple = db.query(func.avg(Customer.rating)).filter(
        Customer.is_archived == False,
        Customer.rating > 0
    ).first()
    avg_rating = round(float(avg_tuple[0] or 0), 1)

    top_count = base.filter(Customer.category == "Top Customer").count()
    prem_count = base.filter(Customer.category == "Premium").count()
    reg_count = base.filter(Customer.category == "Regular").count()
    new_count = base.filter(Customer.category == "New Customer").count()
    pot_count = base.filter(Customer.category == "Potential").count()
    needs_att = base.filter(Customer.category == "Needs Attention").count()

    return IntelligenceKPIs(
        total_customers=total,
        average_rating=avg_rating,
        top_customers=top_count,
        premium_customers=prem_count,
        regular_customers=reg_count,
        new_customers=new_count,
        potential_customers=pot_count,
        needs_attention=needs_att
    )

@router.get("/stats", response_model=IntelligenceKPIs)
def get_stats_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve high-level summary KPIs for Customer Intelligence view."""
    return get_intelligence_kpis(db)

@router.get("/customers", response_model=CustomerIntelligenceListResponse)
def list_intelligence_customers(
    page: int = Query(1, ge=1),
    limit: int = Query(15, ge=1, le=100),
    sort_order: str = Query("desc", pattern="^(desc|asc)$", description="desc = Highest to Lowest rating; asc = Lowest to Highest"),
    rating: Optional[int] = Query(None, ge=1, le=5, description="Filter by star rating (1 to 5)"),
    category: Optional[str] = Query(None, description="Filter by customer category tier"),
    status: Optional[str] = Query(None, description="Filter by customer status (Active, Lead, Inactive)"),
    search: Optional[str] = Query(None, description="Search by Customer Name or Party Code"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Paginated, ranked list of customers for Customer Intelligence.
    - Default sorting: Highest Rating -> Lowest Rating (sort_order='desc').
    - Alternative sorting: Lowest Rating -> Highest Rating (sort_order='asc').
    - Multi-criteria filtering by Rating, Category, Status, and Search.
    - Guaranteed sequential ranking: Rank is calculated sequentially across pages.
    - Both Admin and Employees can view all active customers.
    """
    query = db.query(Customer).options(
        joinedload(Customer.assigned_employee),
        joinedload(Customer.calls),
        joinedload(Customer.interactions)
    ).filter(Customer.is_archived == False)

    # 1. Filters
    if rating is not None:
        query = query.filter(Customer.rating == rating)

    if category and category.strip() and category.strip().lower() != "all":
        query = query.filter(Customer.category == category.strip())

    if status and status.strip() and status.strip().lower() != "all":
        query = query.filter(Customer.status == status.strip())

    if search and search.strip():
        s = f"%{search.strip()}%"
        digits = PhoneNormalizer.clean_digits(search)
        query = query.filter(
            or_(
                Customer.party_name.ilike(s),
                Customer.party_code.ilike(s),
                Customer.contact_person_1.ilike(s),
                Customer.city.ilike(s),
                Customer.phone_1.like(s),
                Customer.phone_1_normalized.like(f"%{digits}%") if digits else False
            )
        )

    # 2. Count matching total
    total = query.count()

    # 3. Apply Sorting
    if sort_order == "asc":
        # Lowest -> Highest Rating
        query = query.order_by(
            asc(Customer.rating),
            desc(Customer.updated_at),
            asc(Customer.id)
        )
    else:
        # Default: Highest -> Lowest Rating
        query = query.order_by(
            desc(Customer.rating),
            desc(Customer.updated_at),
            asc(Customer.id)
        )

    # 4. Paginate
    offset = (page - 1) * limit
    customers = query.offset(offset).limit(limit).all()

    # 5. Build items with correct global continuous ranking sequence
    out_items = []
    for idx, c in enumerate(customers):
        global_rank = offset + idx + 1
        emp_name = c.assigned_employee.full_name if c.assigned_employee else "Unassigned"
        out_items.append(
            CustomerIntelligenceItem(
                id=c.id,
                rank=global_rank,
                party_code=c.party_code,
                party_name=c.party_name,
                contact_person_1=c.contact_person_1,
                email_id_1=c.email_id_1,
                phone_1=c.phone_1,
                city=c.city,
                state=c.state,
                rating=c.rating or 0,
                category=c.category or "Regular",
                status=c.status or "Active",
                assigned_employee_id=c.assigned_employee_id,
                assigned_employee_name=emp_name,
                total_calls=len(c.calls) if c.calls else 0,
                total_interactions=len(c.interactions) if c.interactions else 0,
                created_at=c.created_at,
                updated_at=c.updated_at
            )
        )

    kpis = get_intelligence_kpis(db)

    return CustomerIntelligenceListResponse(
        items=out_items,
        total=total,
        page=page,
        limit=limit,
        total_pages=math.ceil(total / limit) if total > 0 else 1,
        kpis=kpis
    )

@router.get("/customers/{id}", response_model=CustomerIntelligenceDetail)
def get_customer_intelligence_detail(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve full customer intelligence detail, ratings, stats, and rating history."""
    cust = db.query(Customer).options(
        joinedload(Customer.assigned_employee),
        joinedload(Customer.rating_history).joinedload(CustomerRatingHistory.user)
    ).filter(Customer.id == id).first()

    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    total_calls = db.query(Call).filter(Call.customer_id == id).count()
    total_interactions = db.query(CustomerInteraction).filter(CustomerInteraction.customer_id == id).count()
    pending_fu = db.query(FollowUp).filter(
        FollowUp.customer_id == id,
        FollowUp.status.in_(["Pending", "In Progress"])
    ).count()

    # Format history
    history_items = []
    if cust.rating_history:
        for h in cust.rating_history:
            history_items.append(
                CustomerRatingHistoryItem(
                    id=h.id,
                    customer_id=h.customer_id,
                    previous_rating=h.previous_rating,
                    new_rating=h.new_rating,
                    previous_category=h.previous_category,
                    new_category=h.new_category,
                    user_id=h.user_id,
                    user_name=h.user.full_name if h.user else "System",
                    user_role=h.user.role.upper() if h.user else "ADMIN",
                    notes=h.notes,
                    created_at=h.created_at
                )
            )

    return CustomerIntelligenceDetail(
        id=cust.id,
        party_code=cust.party_code,
        party_name=cust.party_name,
        contact_person_1=cust.contact_person_1,
        email_id_1=cust.email_id_1,
        phone_1=cust.phone_1,
        address_line_1=cust.address_line_1,
        address_line_2=cust.address_line_2,
        address_line_3=cust.address_line_3,
        city=cust.city,
        state=cust.state,
        pincode=cust.pincode,
        country=cust.country or "India",
        rating=cust.rating or 0,
        category=cust.category or "Regular",
        status=cust.status or "Active",
        assigned_employee_id=cust.assigned_employee_id,
        assigned_employee_name=cust.assigned_employee.full_name if cust.assigned_employee else "Unassigned",
        total_calls=total_calls,
        total_interactions=total_interactions,
        pending_followups=pending_fu,
        history=history_items,
        created_at=cust.created_at,
        updated_at=cust.updated_at
    )

@router.get("/customers/{id}/history", response_model=List[CustomerRatingHistoryItem])
def get_customer_rating_history(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve chronologically ordered rating and categorization change history for a customer."""
    cust = db.query(Customer).filter(Customer.id == id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    records = db.query(CustomerRatingHistory).options(
        joinedload(CustomerRatingHistory.user)
    ).filter(
        CustomerRatingHistory.customer_id == id
    ).order_by(desc(CustomerRatingHistory.created_at)).all()

    items = []
    for r in records:
        items.append(
            CustomerRatingHistoryItem(
                id=r.id,
                customer_id=r.customer_id,
                previous_rating=r.previous_rating,
                new_rating=r.new_rating,
                previous_category=r.previous_category,
                new_category=r.new_category,
                user_id=r.user_id,
                user_name=r.user.full_name if r.user else "System",
                user_role=r.user.role.upper() if r.user else "ADMIN",
                notes=r.notes,
                created_at=r.created_at
            )
        )
    return items

@router.get("/recent-changes", response_model=List[RecentRatingChangeItem])
def get_recent_rating_changes(
    limit: int = Query(30, ge=1, le=100),
    user_id: Optional[int] = Query(None, description="Filter changes by user ID"),
    search: Optional[str] = Query(None, description="Search by customer name or code"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve chronologically ordered list of recent rating & tier changes across the system."""
    query = db.query(CustomerRatingHistory).options(
        joinedload(CustomerRatingHistory.customer),
        joinedload(CustomerRatingHistory.user)
    )

    if user_id is not None:
        query = query.filter(CustomerRatingHistory.user_id == user_id)

    if search and search.strip():
        s = f"%{search.strip()}%"
        query = query.join(CustomerRatingHistory.customer).filter(
            or_(
                Customer.party_name.ilike(s),
                Customer.party_code.ilike(s),
                Customer.phone_1.like(s)
            )
        )

    records = query.order_by(desc(CustomerRatingHistory.created_at)).limit(limit).all()

    items = []
    for r in records:
        cust = r.customer
        if not cust:
            continue
        items.append(
            RecentRatingChangeItem(
                id=r.id,
                customer_id=r.customer_id,
                party_code=cust.party_code,
                party_name=cust.party_name,
                phone_1=cust.phone_1,
                city=cust.city,
                state=cust.state,
                previous_rating=r.previous_rating,
                new_rating=r.new_rating,
                previous_category=r.previous_category,
                new_category=r.new_category,
                user_id=r.user_id,
                user_name=r.user.full_name if r.user else "System",
                user_role=r.user.role.upper() if r.user else "ADMIN",
                notes=r.notes,
                created_at=r.created_at
            )
        )
    return items

@router.put("/customers/{id}/rating", response_model=CustomerIntelligenceDetail)
async def update_customer_rating_and_category(
    id: int,
    payload: CustomerRatingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Assign or edit customer rating (1-5 stars) and category.
    Role-based permission enforcement:
    - Admin: Full rights to update any customer.
    - Employees: Permitted for active staff members.
    """
    # Category validation
    category_clean = payload.category.strip()
    if category_clean not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{category_clean}'. Valid categories: {', '.join(sorted(VALID_CATEGORIES))}"
        )

    # Permission check: Admin or authorized staff
    # Both Admin and Employees can update if active; otherwise raise 403
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="Deactivated accounts cannot modify customer intelligence ratings.")

    cust = db.query(Customer).filter(Customer.id == id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    old_rating = cust.rating or 0
    old_category = cust.category or "Regular"

    # Update customer record
    cust.rating = payload.rating
    cust.category = category_clean
    cust.updated_at = datetime.now(timezone.utc)

    # Insert Rating History record with exact accurate timestamp & user info
    history_entry = CustomerRatingHistory(
        customer_id=cust.id,
        previous_rating=old_rating if old_rating > 0 else None,
        new_rating=payload.rating,
        previous_category=old_category,
        new_category=category_clean,
        user_id=current_user.id,
        notes=payload.notes.strip() if payload.notes else f"Updated rating to {payload.rating}★ and category to {category_clean}",
        created_at=datetime.now(timezone.utc)
    )
    db.add(history_entry)

    # Insert Interaction note for customer 360 timeline
    interaction = CustomerInteraction(
        customer_id=cust.id,
        user_id=current_user.id,
        interaction_type="note",
        direction="internal",
        subject=f"Intelligence Rating Updated: {payload.rating}★ ({category_clean})",
        content=f"Updated by {current_user.full_name} ({current_user.role.upper()}). Previous: {old_rating}★ [{old_category}]. {payload.notes or ''}".strip(),
        meta_info={
            "old_rating": old_rating,
            "new_rating": payload.rating,
            "old_category": old_category,
            "new_category": category_clean,
            "updated_by": current_user.full_name,
            "updated_by_role": current_user.role.upper()
        }
    )
    db.add(interaction)

    # Audit Log
    AuditService.log(
        db,
        action="CUSTOMER_RATING_UPDATED",
        entity_type="customer",
        entity_id=str(cust.id),
        changes={
            "party_name": cust.party_name,
            "old_rating": old_rating,
            "new_rating": payload.rating,
            "old_category": old_category,
            "new_category": category_clean,
            "updated_by_user": current_user.full_name,
            "updated_by_role": current_user.role,
            "notes": payload.notes
        },
        user=current_user
    )

    db.commit()
    db.refresh(cust)

    # Live SSE broadcast to all connected Admin and Employee clients
    try:
        await broadcast_manager.broadcast_call({
            "event": "customer_rating_updated",
            "customer_id": cust.id,
            "party_name": cust.party_name,
            "party_code": cust.party_code,
            "old_rating": old_rating,
            "new_rating": payload.rating,
            "old_category": old_category,
            "new_category": category_clean,
            "user_id": current_user.id,
            "user_name": current_user.full_name,
            "user_role": current_user.role.upper(),
            "notes": payload.notes,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    except Exception as broadcast_err:
        pass

    return get_customer_intelligence_detail(cust.id, db, current_user)
