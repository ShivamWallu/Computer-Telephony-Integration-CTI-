from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from backend.app.models.user import User
from backend.app.models.customer import Customer, CustomerPhoneNumber
from backend.app.models.customer_document import CustomerDocument
from backend.app.models.interaction import CustomerInteraction
from backend.app.models.call import Call
from backend.app.models.follow_up import FollowUp
from backend.app.models.audit_log import AuditLog
from backend.app.models.import_job import ImportJob, ImportError as ImportErrorModel, ImportUpdate
from backend.app.services.phone_normalizer import PhoneNormalizer
from backend.app.utils.security import get_password_hash
import random
import logging

logger = logging.getLogger(__name__)

DEMO_USERS = [
    {
        "email": "infotech@khandelia.com",
        "full_name": "Yogesh Khandelia",
        "role": "admin",
        "password": "admin",
        "allowed_caller_id": "918065908540",
        "vid": "918065908540",
        "phone": "919914565011",
        "agent_id": "506912000010",
        "intercom": "1009",
        "designation": "Director"
    },
    {
        "email": "itchd.kogm@gmail.com",
        "full_name": "Shivam",
        "role": "admin",
        "password": "admin",
        "allowed_caller_id": "918065908540",
        "vid": "918065908540",
        "phone": "+91 78147 49816",
        "agent_id": "ADMIN001",
        "intercom": "1000",
        "designation": "System Admin"
    },
    {
        "email": "kogm.sahildogra@gmail.com",
        "full_name": "Sahil Dogra",
        "role": "employee",
        "password": "12345678",
        "allowed_caller_id": "918065908531",
        "vid": "918065908531",
        "phone": "918146982211",
        "agent_id": "506912000001",
        "intercom": "1001",
        "designation": "Support Agent"
    },
    {
        "email": "bmjagga@khandelia.com",
        "full_name": "BM Jagga",
        "role": "employee",
        "password": "12345678",
        "allowed_caller_id": "918065908532",
        "vid": "918065908532",
        "phone": "917087422511",
        "agent_id": "506912000002",
        "intercom": "1002",
        "designation": "Support Agent"
    },
    {
        "email": "sales.kol@khandelia.com",
        "full_name": "Utpal Pal",
        "role": "employee",
        "password": "12345678",
        "allowed_caller_id": "918065908533",
        "vid": "918065908533",
        "phone": "919830022111",
        "agent_id": "506912000004",
        "intercom": "1004",
        "designation": "Support Agent"
    },
    {
        "email": "sales.gm@khandelia.com",
        "full_name": "Sunil Jain",
        "role": "employee",
        "password": "12345678",
        "allowed_caller_id": "918065908534",
        "vid": "918065908534",
        "phone": "917888814811",
        "agent_id": "506912000003",
        "intercom": "1003",
        "designation": "Support Agent"
    },
    {
        "email": "customercare@khandelia.com",
        "full_name": "Ravi Kumar",
        "role": "employee",
        "password": "12345678",
        "allowed_caller_id": "918065908535",
        "vid": "918065908535",
        "phone": "917814694240",
        "agent_id": "506912000005",
        "intercom": "1005",
        "designation": "Customer Care"
    },
    {
        "email": "account.unit6@khandelia.com",
        "full_name": "Ankush Dingra",
        "role": "employee",
        "password": "12345678",
        "allowed_caller_id": "918065908536",
        "vid": "918065908536",
        "phone": "919784410004",
        "agent_id": "506912000008",
        "intercom": "1007",
        "designation": "Sales"
    },
    {
        "email": "kogm.sonukumar@gmail.com",
        "full_name": "Sonu Kumar",
        "role": "employee",
        "password": "12345678",
        "allowed_caller_id": "918065908538",
        "vid": "918065908538",
        "phone": "919316113211",
        "agent_id": "506912000007",
        "intercom": "1006",
        "designation": "HR manager"
    },
    {
        "email": "storepurchase@khandelia.com",
        "full_name": "Ankush Kapila",
        "role": "employee",
        "password": "12345678",
        "allowed_caller_id": "918065908539",
        "vid": "918065908539",
        "phone": "917696304207",
        "agent_id": "506912000009",
        "intercom": "1008",
        "designation": "store manager"
    },
    {
        "email": "kogm.pankaj@gmail.com",
        "full_name": "Pankaj",
        "role": "employee",
        "password": "12345678",
        "allowed_caller_id": "918065908541",
        "vid": "918065908541",
        "phone": "+917743004676",
        "agent_id": "506912000011",
        "intercom": "1010",
        "designation": "Sales Team"
    }
]

# EXPLICIT LIST OF PURGED DUMMY CUSTOMERS TO PERMANENTLY REMOVE
PURGED_DUMMY_CUSTOMER_CODES = [
    "CUST-1001", "CUST-1002", "CUST-1003", "CUST-1004", "CUST-1005", "CUST-1006"
]

# PRIMARY VERIFIED PRODUCTION CUSTOMER RECORD (SHIVAM)
PRIMARY_SEED_CUSTOMERS = [
    {
        "party_code": "CUST-7814",
        "party_name": "Mashal Oil & Foods Ltd",
        "address_date": "2026-08-24",
        "address_line_1": "Plot No. 12, Industrial Area",
        "address_line_2": "Phase 2, Focal Point",
        "address_line_3": "Near Metro Depot",
        "contact_person_1": "Shivam",
        "email_id_1": "itchd.kogm@gmail.com",
        "country": "India",
        "state": "Punjab",
        "city": "Ludhiana",
        "pincode": "141001",
        "phone_type_1": "Mobile",
        "phone_1": "+91 78147 49816",
        "status": "Active",
        "notes": "Verified VIP Client - Mashal Oil & Foods Ltd."
    }
]

# Backward compatibility alias
EXACT_7_CUSTOMERS = PRIMARY_SEED_CUSTOMERS

def seed_database(db: Session, force_reset: bool = False):
    """Seed verified team members and single primary production customer cleanly."""
    # 0. Explicitly purge unwanted/deleted employees
    deleted_emails = [
        "sunil.varma@company.com", "deepak.c@company.com", "karan.mehra@crm.com",
        "shivam@crm.com", "rahul@crm.com", "amit@crm.com", "priya@crm.com"
    ]
    deleted_names = [
        "Sunil Varma", "Deepak Chopra", "Karan Mehra", "Temporary Support Agent",
        "Rahul Sharma", "Amit Verma", "Priya Patel"
    ]
    deleted_users = db.query(User).filter(
        (User.email.in_(deleted_emails)) |
        (User.full_name.in_(deleted_names)) |
        (User.email.like("temp_agent_%"))
    ).all()
    for du in deleted_users:
        db.query(Customer).filter(Customer.assigned_employee_id == du.id).update({"assigned_employee_id": None}, synchronize_session=False)
        db.query(Call).filter(Call.user_id == du.id).update({"user_id": None}, synchronize_session=False)
        db.query(FollowUp).filter(FollowUp.assigned_user_id == du.id).delete(synchronize_session=False)
        db.query(CustomerInteraction).filter(CustomerInteraction.user_id == du.id).delete(synchronize_session=False)
        db.query(AuditLog).filter(AuditLog.user_id == du.id).delete(synchronize_session=False)
        db.delete(du)
    db.commit()

    # 0.1 Customer records are 100% preserved and never purged on seed

    if force_reset:
        demo_emails = [u["email"] for u in DEMO_USERS]
        db.query(User).filter(User.email.notin_(demo_emails)).delete(synchronize_session=False)

    # 1. Seed Users
    user_objs = []
    for udata in DEMO_USERS:
        existing = db.query(User).filter(
            (User.email == udata["email"]) |
            (User.full_name == udata["full_name"])
        ).first()
        if not existing:
            u = User(
                email=udata["email"],
                hashed_password=get_password_hash(udata["password"]),
                full_name=udata["full_name"],
                role=udata["role"],
                allowed_caller_id=udata.get("allowed_caller_id"),
                vid=udata.get("vid") or udata.get("allowed_caller_id"),
                phone=udata.get("phone"),
                agent_id=udata.get("agent_id"),
                intercom=udata.get("intercom"),
                designation=udata.get("designation"),
                is_active=True
            )
            db.add(u)
            db.flush()
            user_objs.append(u)
        else:
            existing.email = udata["email"]
            existing.full_name = udata["full_name"]
            existing.role = udata["role"]
            existing.allowed_caller_id = udata.get("allowed_caller_id")
            existing.vid = udata.get("vid") or udata.get("allowed_caller_id")
            existing.phone = udata.get("phone")
            existing.agent_id = udata.get("agent_id")
            existing.intercom = udata.get("intercom")
            existing.designation = udata.get("designation")
            if force_reset:
                existing.hashed_password = get_password_hash(udata["password"])
            db.flush()
            user_objs.append(existing)

    admin_user = [u for u in user_objs if u.role == "admin"][0]

    # Ensure Primary Production Customer (CUST-7814 - Shivam) exists
    primary_cust = db.query(Customer).filter(Customer.party_code == "CUST-7814").first()
    if not primary_cust:
        cdata = PRIMARY_SEED_CUSTOMERS[0]
        norm = PhoneNormalizer.normalize(cdata["phone_1"])
        primary_cust = Customer(
            party_code=cdata["party_code"],
            party_name=cdata["party_name"],
            address_date=cdata["address_date"],
            address_line_1=cdata["address_line_1"],
            address_line_2=cdata["address_line_2"],
            address_line_3=cdata["address_line_3"],
            contact_person_1=cdata["contact_person_1"],
            email_id_1=cdata["email_id_1"],
            country=cdata["country"],
            state=cdata["state"],
            city=cdata["city"],
            pincode=cdata["pincode"],
            phone_type_1=cdata["phone_type_1"],
            phone_1=cdata["phone_1"],
            phone_1_normalized=norm,
            status=cdata["status"],
            notes=cdata["notes"],
            assigned_employee_id=admin_user.id,
            is_archived=False,
            created_at=datetime.now(timezone.utc)
        )
        db.add(primary_cust)
        db.commit()
        db.refresh(primary_cust)
    else:
        primary_cust.contact_person_1 = "Shivam"
        primary_cust.email_id_1 = "itchd.kogm@gmail.com"
        db.commit()
