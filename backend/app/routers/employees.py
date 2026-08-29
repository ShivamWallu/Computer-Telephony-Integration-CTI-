from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.customer import Customer
from backend.app.schemas.auth import UserOut, UserCreate, UserUpdate
from backend.app.utils.security import get_current_user, get_current_admin_user, get_password_hash
from backend.app.services.audit_service import AuditService
from backend.app.services.email_service import EmailService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employees", tags=["Employee Management"])

class ReassignCustomersRequest(BaseModel):
    customer_ids: Optional[List[int]] = None
    target_employee_id: int
    reassign_scope: Optional[str] = "all"  # "all", "unassigned", "individual"

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
    if user_update.password:
        employee.hashed_password = get_password_hash(user_update.password)

    db.commit()
    db.refresh(employee)

    AuditService.log(
        db,
        action="EMPLOYEE_UPDATED",
        entity_type="user",
        entity_id=str(employee.id),
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
    Admin-only: Bulk or individually reassign customers to another employee,
    and automatically trigger email notification to the newly assigned employee.
    """
    target_emp = db.query(User).filter(User.id == req.target_employee_id, User.is_active == True).first()
    if not target_emp:
        raise HTTPException(status_code=404, detail="Target employee not found")

    query = db.query(Customer).filter(Customer.is_archived == False)

    if req.customer_ids and len(req.customer_ids) > 0:
        query = query.filter(Customer.id.in_(req.customer_ids))
    elif req.reassign_scope == "unassigned":
        query = query.filter(Customer.assigned_employee_id == None)

    # Get the target customers to include in email notification
    target_customers = query.all()
    if not target_customers:
        return {
            "status": "success",
            "reassigned_count": 0,
            "assigned_to": target_emp.full_name,
            "message": "No matching customers found for reassignment criteria."
        }

    cust_ids = [c.id for c in target_customers]
    updated_count = (
        db.query(Customer)
        .filter(Customer.id.in_(cust_ids))
        .update({Customer.assigned_employee_id: req.target_employee_id}, synchronize_session=False)
    )
    db.commit()

    # Determine employee password representation
    emp_pwd = target_emp.email.split('@')[0] if target_emp.email else "welcome123"
    if target_emp.email in ["admin@crm.com", "shivam@crm.com"]:
        emp_pwd = "admin"

    # Automatically dispatch notification email to target employee
    try:
        EmailService.send_assignment_notification(
            employee_email=target_emp.email,
            employee_name=target_emp.full_name,
            assigned_customers=target_customers,
            admin_name=current_user.full_name,
            employee_password=emp_pwd
        )
    except Exception as e:
        logger.warning(f"Could not dispatch assignment notification email: {e}")

    AuditService.log(
        db,
        action="CUSTOMERS_REASSIGNED",
        entity_type="customer",
        changes={
            "customer_count": updated_count,
            "target_employee": target_emp.full_name,
            "target_email": target_emp.email,
            "scope": req.reassign_scope
        },
        user=current_user
    )

    return {
        "status": "success",
        "reassigned_count": updated_count,
        "assigned_to": target_emp.full_name,
        "message": f"Successfully reassigned {updated_count} customer(s) to {target_emp.full_name}. Notification email dispatched."
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
