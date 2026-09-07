from typing import List, Optional, Union
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.customer import Customer
from sqlalchemy import func
from backend.app.schemas.auth import UserOut, UserCreate, UserUpdate, UserPermissionsUpdate
from backend.app.utils.security import get_current_user, get_current_admin_user, get_password_hash
from backend.app.services.audit_service import AuditService
from backend.app.services.email_service import EmailService
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employees", tags=["Employee Management"])

def _normalize_allowed_categories(cats) -> str:
    """Normalize allowed_categories to a standard JSON string format like '["HUSK", "SAS"]' or '["*"]'."""
    if cats is None:
        return '["*"]'
    if isinstance(cats, list):
        cleaned = [str(c).strip() for c in cats if str(c).strip() and str(c).strip() not in ('***', "['***']")]
        if not cleaned or "ALL" in [c.upper() for c in cleaned] or "*" in cleaned or len(cleaned) >= 10:
            return '["*"]'
        return json.dumps(cleaned)
    if isinstance(cats, str):
        cats_str = cats.strip()
        if cats_str.startswith('[') and cats_str.endswith(']'):
            try:
                parsed = json.loads(cats_str)
                if isinstance(parsed, list):
                    return _normalize_allowed_categories(parsed)
            except Exception:
                pass
        parts = [p.strip() for p in cats_str.split(',') if p.strip() and p.strip() not in ('***', "['***']")]
        if not parts or "ALL" in [p.upper() for p in parts] or "*" in parts or len(parts) >= 10:
            return '["*"]'
        return json.dumps(parts)
    return '["*"]'

def _normalize_allowed_upload_categories(cats) -> str:
    """Normalize allowed_upload_categories to a standard JSON string format like '["HUSK"]' or '[]'."""
    if cats is None:
        return '[]'
    if isinstance(cats, list):
        cleaned = [str(c).strip() for c in cats if str(c).strip() and str(c).strip() not in ('***', "['***']")]
        if "*" in cleaned or "ALL" in [c.upper() for c in cleaned]:
            return '["*"]'
        return json.dumps(cleaned)
    if isinstance(cats, str):
        cats_str = cats.strip()
        if cats_str.startswith('[') and cats_str.endswith(']'):
            try:
                parsed = json.loads(cats_str)
                if isinstance(parsed, list):
                    return _normalize_allowed_upload_categories(parsed)
            except Exception:
                pass
        parts = [p.strip() for p in cats_str.split(',') if p.strip() and p.strip() not in ('***', "['***']")]
        if "*" in parts or "ALL" in [p.upper() for p in parts]:
            return '["*"]'
        return json.dumps(parts)
    return '[]'

class ReassignCustomersRequest(BaseModel):
    customer_ids: Optional[List[int]] = None
    target_employee_id: Optional[int] = None  # None or 0 means All Employees (Shared Pool)
    reassign_scope: Optional[str] = "all"  # "all", "unassigned", "selected"

@router.get("/assignment-stats")
def get_assignment_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns real-time distribution of assigned customers across all employees,
    including total active customers and unassigned/shared pool customers.
    """
    total = db.query(func.count(Customer.id)).filter(Customer.is_archived == False).scalar() or 0
    
    # Active team employees (role == 'employee')
    employees = db.query(User).filter(User.is_active == True, User.role == "employee").order_by(User.full_name).all()
    emp_ids = [e.id for e in employees]
    
    # Counts for team employees
    counts_raw = (
        db.query(Customer.assigned_employee_id, func.count(Customer.id))
        .filter(Customer.is_archived == False, Customer.assigned_employee_id.in_(emp_ids))
        .group_by(Customer.assigned_employee_id)
        .all()
    ) if emp_ids else []
    counts_map = {emp_id: cnt for emp_id, cnt in counts_raw}
    
    total_assigned_to_employees = sum(counts_map.values())
    unassigned = max(0, total - total_assigned_to_employees)
    
    stats = []
    for emp in employees:
        stats.append({
            "employee_id": emp.id,
            "full_name": emp.full_name,
            "email": emp.email,
            "role": emp.role,
            "designation": emp.designation,
            "assigned_count": counts_map.get(emp.id, 0)
        })
        
    return {
        "total_customers": total,
        "unassigned_customers": unassigned,
        "employees": stats
    }

@router.get("", response_model=List[UserOut])
def list_employees(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List active employees with strict role-based isolation:
    - Admin: sees all active team members across the organization.
    - Employee: sees ONLY their own employee record.
    """
    query = db.query(User).filter(User.is_active == True)
    if current_user.role == "employee":
        query = query.filter(User.id == current_user.id)

    employees = query.order_by(User.full_name).all()
    return [UserOut.model_validate(e) for e in employees]

@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_employee(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Admin-only: Add a new employee and dispatch automatic welcome email."""
    # Guard: Single Admin restriction
    if user_in.role and user_in.role.lower() == "admin":
        raise HTTPException(
            status_code=400,
            detail="Cannot create multiple Admin accounts. The system is restricted to a single primary Director/Admin."
        )

    email_clean = user_in.email.lower().strip()
    existing = db.query(User).filter(User.email == email_clean).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"An employee with email '{email_clean}' already exists")

    if not user_in.password or len(user_in.password.strip()) < 3:
        raise HTTPException(status_code=400, detail="A valid password (minimum 3 characters) is required")

    new_user = User(
        email=email_clean,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name.strip(),
        role="employee",  # Strictly employee role
        allowed_caller_id=user_in.allowed_caller_id,
        vid=user_in.vid or user_in.allowed_caller_id,
        phone=user_in.phone,
        agent_id=user_in.agent_id,
        intercom=user_in.intercom,
        designation=user_in.designation or "Employee",
        tcs_username=user_in.tcs_username,
        tcs_password=user_in.tcs_password,
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Dispatch automatic welcome email with credentials & portal link
    try:
        EmailService.send_employee_welcome_email(
            employee_name=new_user.full_name,
            employee_email=new_user.email,
            password=user_in.password,
            admin_name=admin_user.full_name
        )
    except Exception as e:
        logger.warning(f"Could not deliver welcome email to newly created employee {new_user.email}: {e}")

    AuditService.log(
        db,
        action="EMPLOYEE_CREATED",
        entity_type="user",
        entity_id=str(new_user.id),
        changes={"name": new_user.full_name, "email": new_user.email, "role": new_user.role},
        user=admin_user
    )

    return UserOut.model_validate(new_user)

@router.put("/{id}", response_model=UserOut)
def update_employee(
    id: int,
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Admin-only: Update employee details, password, or active status."""
    employee = db.query(User).filter(User.id == id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Guard: Do not allow promoting an employee to admin
    if user_update.role and user_update.role.lower() == "admin" and employee.role != "admin":
        raise HTTPException(
            status_code=400,
            detail="Cannot promote an employee to Admin. Only one primary Director/Admin is permitted."
        )

    if user_update.full_name:
        employee.full_name = user_update.full_name
    if user_update.role and user_update.role.lower() != "admin":
        employee.role = user_update.role
    if user_update.allowed_caller_id is not None:
        employee.allowed_caller_id = user_update.allowed_caller_id
    if user_update.vid is not None:
        employee.vid = user_update.vid
    if user_update.phone is not None:
        employee.phone = user_update.phone
    if user_update.agent_id is not None:
        employee.agent_id = user_update.agent_id
    if user_update.intercom is not None:
        employee.intercom = user_update.intercom
    if user_update.designation is not None:
        employee.designation = user_update.designation
    if user_update.is_active is not None:
        employee.is_active = user_update.is_active
    if user_update.tcs_username is not None:
        employee.tcs_username = user_update.tcs_username.strip()
    if user_update.tcs_password is not None:
        employee.tcs_password = user_update.tcs_password.strip()
    if user_update.allowed_categories is not None:
        employee.allowed_categories = _normalize_allowed_categories(user_update.allowed_categories)
    if user_update.allowed_upload_categories is not None:
        employee.allowed_upload_categories = _normalize_allowed_upload_categories(user_update.allowed_upload_categories)
    if user_update.can_add_customer is not None:
        employee.can_add_customer = user_update.can_add_customer
    if user_update.can_edit_customer is not None:
        employee.can_edit_customer = user_update.can_edit_customer
    if user_update.can_delete_customer is not None:
        employee.can_delete_customer = user_update.can_delete_customer
    if user_update.can_rate_customer is not None:
        employee.can_rate_customer = user_update.can_rate_customer
    if user_update.can_make_calls is not None:
        employee.can_make_calls = user_update.can_make_calls
    if user_update.can_listen_recordings is not None:
        employee.can_listen_recordings = user_update.can_listen_recordings
    if user_update.can_export_data is not None:
        employee.can_export_data = user_update.can_export_data
    if user_update.can_view_unassigned is not None:
        employee.can_view_unassigned = user_update.can_view_unassigned
    if user_update.password:
        employee.hashed_password = get_password_hash(user_update.password)

    db.commit()
    db.refresh(employee)

    AuditService.log(
        db,
        action="EMPLOYEE_UPDATED",
        entity_type="user",
        entity_id=str(employee.id),
        changes={"name": employee.full_name, "email": employee.email},
        user=admin_user
    )

    return UserOut.model_validate(employee)

@router.put("/{id}/permissions", response_model=UserOut)
def update_employee_permissions(
    id: int,
    perms: Union[UserPermissionsUpdate, UserUpdate],
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Admin-only: Update granular permissions and allowed categories for an employee."""
    employee = db.query(User).filter(User.id == id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    if perms.allowed_categories is not None:
        employee.allowed_categories = _normalize_allowed_categories(perms.allowed_categories)
    if perms.allowed_upload_categories is not None:
        employee.allowed_upload_categories = _normalize_allowed_upload_categories(perms.allowed_upload_categories)
    if perms.can_add_customer is not None:
        employee.can_add_customer = perms.can_add_customer
    if perms.can_edit_customer is not None:
        employee.can_edit_customer = perms.can_edit_customer
    if perms.can_delete_customer is not None:
        employee.can_delete_customer = perms.can_delete_customer
    if perms.can_rate_customer is not None:
        employee.can_rate_customer = perms.can_rate_customer
    if perms.can_make_calls is not None:
        employee.can_make_calls = perms.can_make_calls
    if perms.can_listen_recordings is not None:
        employee.can_listen_recordings = perms.can_listen_recordings
    if perms.can_export_data is not None:
        employee.can_export_data = perms.can_export_data
    if perms.can_view_unassigned is not None:
        employee.can_view_unassigned = perms.can_view_unassigned

    db.commit()
    db.refresh(employee)

    AuditService.log(
        db,
        action="EMPLOYEE_PERMISSIONS_UPDATED",
        entity_type="user",
        entity_id=str(employee.id),
        changes=perms.model_dump(exclude_unset=True),
        user=admin_user
    )

    return UserOut.model_validate(employee)

@router.delete("/{id}")
def delete_employee(
    id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Admin-only: Delete an employee.
    IMPORTANT: All assigned customers are SAFELY PRESERVED and set to Unassigned (None).
    """
    if id == admin_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own active administrator account.")

    employee = db.query(User).filter(User.id == id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee record not found")

    if employee.role == "admin":
        raise HTTPException(status_code=400, detail="Primary administrator account cannot be deleted.")

    employee = db.query(User).filter(User.id == id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee record not found")

    emp_name = employee.full_name
    emp_email = employee.email

    # 1. Safely unassign all customers belonging to this employee so no data is ever lost
    unassigned_count = (
        db.query(Customer)
        .filter(Customer.assigned_employee_id == id)
        .update({Customer.assigned_employee_id: None}, synchronize_session=False)
    )

    # 2. Delete employee record
    db.delete(employee)
    db.commit()

    AuditService.log(
        db,
        action="EMPLOYEE_DELETED",
        entity_type="user",
        entity_id=str(id),
        changes={
            "deleted_user_name": emp_name,
            "deleted_user_email": emp_email,
            "customers_unassigned_safely": unassigned_count
        },
        user=admin_user
    )

    logger.info(f"Admin {admin_user.full_name} deleted employee {emp_name}. {unassigned_count} customers preserved.")
    return {
        "status": "success",
        "message": f"Employee '{emp_name}' deleted successfully. {unassigned_count} assigned customer(s) were preserved and moved to Unassigned status.",
        "customers_preserved": unassigned_count
    }

@router.post("/reassign-customers")
def reassign_customers(
    req: ReassignCustomersRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Admin-only: Bulk or individually assign customers to a specific employee or to All Employees (Shared Pool).
    Assignment notifications are delivered only to the configured test inbox.
    """
    target_emp = None
    assigned_to_name = "All Employees (Shared Pool)"
    assigned_emp_id = None

    if req.target_employee_id and req.target_employee_id > 0:
        target_emp = db.query(User).filter(User.id == req.target_employee_id, User.is_active == True).first()
        if not target_emp:
            raise HTTPException(status_code=404, detail="Target employee not found")
        assigned_to_name = target_emp.full_name
        assigned_emp_id = target_emp.id

    query = db.query(Customer).filter(Customer.is_archived == False)

    if req.customer_ids and len(req.customer_ids) > 0:
        query = query.filter(Customer.id.in_(req.customer_ids))
    elif req.reassign_scope == "unassigned":
        emp_ids = [u.id for u in db.query(User.id).filter(User.is_active == True, User.role == "employee").all()]
        if emp_ids:
            query = query.filter(or_(Customer.assigned_employee_id == None, ~Customer.assigned_employee_id.in_(emp_ids)))

    target_customers = query.all()
    if not target_customers:
        return {
            "status": "success",
            "reassigned_count": 0,
            "assigned_to": assigned_to_name,
            "message": "No matching customers found for reassignment criteria."
        }

    cust_ids = [c.id for c in target_customers]
    updated_count = (
        db.query(Customer)
        .filter(Customer.id.in_(cust_ids))
        .update({Customer.assigned_employee_id: assigned_emp_id}, synchronize_session=False)
    )
    db.commit()

    notification = {"status": "not_applicable"}
    if target_emp:
        notification = EmailService.send_assignment_notification(
            employee_email=target_emp.email,
            employee_name=target_emp.full_name,
            assigned_customers=target_customers,
            admin_name=current_user.full_name
        )

    logger.info(f"Assigned {updated_count} customers to '{assigned_to_name}'. Assignment test notification status: {notification.get('status')}.")

    AuditService.log(
        db,
        action="CUSTOMERS_REASSIGNED",
        entity_type="customer",
        changes={
            "customer_count": updated_count,
            "assigned_to": assigned_to_name,
            "scope": req.reassign_scope,
            "email_dispatched": notification.get("status") == "sent",
            "email_recipient": notification.get("recipient"),
            "email_status": notification.get("status")
        },
        user=current_user
    )

    return {
        "status": "success",
        "reassigned_count": updated_count,
        "assigned_to": assigned_to_name,
        "message": f"Successfully assigned {updated_count} customer(s) to {assigned_to_name}.",
        "notification": notification
    }

@router.post("/clean-production-data")
def clean_production_data_endpoint(
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Admin-only: Safely clean all development and test data prior to master Excel import.
    Preserves Customer 7814749816 and its relationships 100% intact.
    """
    from backend.app.utils.production_cleanup import perform_production_data_cleanup
    summary = perform_production_data_cleanup(db, admin_password="admin")
    return summary
