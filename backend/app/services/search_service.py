import time
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_, func
from backend.app.models.customer import Customer, CustomerPhoneNumber
from backend.app.models.user import User
from backend.app.schemas.customer import CustomerSearchOut
from backend.app.services.phone_normalizer import PhoneNormalizer
import logging

logger = logging.getLogger(__name__)

class SearchService:
    @staticmethod
    def search_customers(
        db: Session,
        query: str,
        limit: int = 15,
        user: Optional[User] = None
    ) -> Tuple[List[CustomerSearchOut], float]:
        """
        Ultra-fast prioritized multi-tier search engine:
        1. Exact normalized phone match across Primary & Additional Phone Numbers (Highest Priority)
        2. Exact Party Code match
        3. Exact Email match
        4. Party Name / Contact Person / City match
        5. Substring / partial match
        
        Returns (results, elapsed_milliseconds)
        """
        start_time = time.perf_counter()
        q = (query or "").strip()
        if not q:
            return [], 0.0

        results: List[CustomerSearchOut] = []
        seen_ids = set()
        phone_variants = PhoneNormalizer.get_search_variants(q)
        is_numeric = bool(phone_variants) and len(PhoneNormalizer.clean_digits(q)) >= 3

        # Base filter: not archived
        base_filters = [Customer.is_archived == False]

        # -------------------------------------------------------------
        # TIER 1: Exact Phone Lookup (Primary phone + Additional phones)
        # -------------------------------------------------------------
        if is_numeric and phone_variants:
            # 1a. Search primary phone
            exact_phone_matches = (
                db.query(Customer)
                .options(joinedload(Customer.assigned_employee))
                .filter(
                    *base_filters,
                    Customer.phone_1_normalized.in_(phone_variants)
                )
                .limit(limit)
                .all()
            )
            for c in exact_phone_matches:
                if c.id not in seen_ids:
                    seen_ids.add(c.id)
                    results.append(CustomerSearchOut(
                        id=c.id,
                        party_code=c.party_code,
                        party_name=c.party_name,
                        contact_person_1=c.contact_person_1,
                        email_id_1=c.email_id_1,
                        city=c.city,
                        state=c.state,
                        phone_1=c.phone_1,
                        phone_1_normalized=c.phone_1_normalized,
                        status=c.status,
                        assigned_employee_name=c.assigned_employee.full_name if c.assigned_employee else None,
                        match_type="exact_phone"
                    ))

            # 1b. Search additional phone numbers
            if len(results) < limit:
                additional_phone_matches = (
                    db.query(Customer)
                    .join(CustomerPhoneNumber, Customer.id == CustomerPhoneNumber.customer_id)
                    .options(joinedload(Customer.assigned_employee))
                    .filter(
                        *base_filters,
                        CustomerPhoneNumber.phone_normalized.in_(phone_variants)
                    )
                    .limit(limit - len(results))
                    .all()
                )
                for c in additional_phone_matches:
                    if c.id not in seen_ids:
                        seen_ids.add(c.id)
                        results.append(CustomerSearchOut(
                            id=c.id,
                            party_code=c.party_code,
                            party_name=c.party_name,
                            contact_person_1=c.contact_person_1,
                            email_id_1=c.email_id_1,
                            city=c.city,
                            state=c.state,
                            phone_1=c.phone_1,
                            phone_1_normalized=c.phone_1_normalized,
                            status=c.status,
                            assigned_employee_name=c.assigned_employee.full_name if c.assigned_employee else None,
                            match_type="additional_phone"
                        ))

        # -------------------------------------------------------------
        # TIER 2: Exact Party Code Lookup (Direct Unique Index Hit)
        # -------------------------------------------------------------
        if len(results) < limit:
            exact_id_matches = (
                db.query(Customer)
                .options(joinedload(Customer.assigned_employee))
                .filter(
                    *base_filters,
                    func.lower(Customer.party_code) == q.lower()
                )
                .limit(limit - len(results))
                .all()
            )
            for c in exact_id_matches:
                if c.id not in seen_ids:
                    seen_ids.add(c.id)
                    results.append(CustomerSearchOut(
                        id=c.id,
                        party_code=c.party_code,
                        party_name=c.party_name,
                        contact_person_1=c.contact_person_1,
                        email_id_1=c.email_id_1,
                        city=c.city,
                        state=c.state,
                        phone_1=c.phone_1,
                        phone_1_normalized=c.phone_1_normalized,
                        status=c.status,
                        assigned_employee_name=c.assigned_employee.full_name if c.assigned_employee else None,
                        match_type="exact_code"
                    ))

        # -------------------------------------------------------------
        # TIER 3: Exact Email Lookup (Direct Index Hit)
        # -------------------------------------------------------------
        if len(results) < limit and "@" in q:
            exact_email_matches = (
                db.query(Customer)
                .options(joinedload(Customer.assigned_employee))
                .filter(
                    *base_filters,
                    func.lower(Customer.email_id_1) == q.lower()
                )
                .limit(limit - len(results))
                .all()
            )
            for c in exact_email_matches:
                if c.id not in seen_ids:
                    seen_ids.add(c.id)
                    results.append(CustomerSearchOut(
                        id=c.id,
                        party_code=c.party_code,
                        party_name=c.party_name,
                        contact_person_1=c.contact_person_1,
                        email_id_1=c.email_id_1,
                        city=c.city,
                        state=c.state,
                        phone_1=c.phone_1,
                        phone_1_normalized=c.phone_1_normalized,
                        status=c.status,
                        assigned_employee_name=c.assigned_employee.full_name if c.assigned_employee else None,
                        match_type="exact_email"
                    ))

        # -------------------------------------------------------------
        # TIER 4: Prefix & Substring Match on Party Name, Contact Person, City, Phone
        # -------------------------------------------------------------
        if len(results) < limit:
            search_pattern = f"%{q}%"
            partial_matches = (
                db.query(Customer)
                .options(joinedload(Customer.assigned_employee))
                .filter(
                    *base_filters,
                    or_(
                        Customer.party_name.ilike(search_pattern),
                        Customer.party_code.ilike(search_pattern),
                        Customer.contact_person_1.ilike(search_pattern),
                        Customer.email_id_1.ilike(search_pattern),
                        Customer.city.ilike(search_pattern),
                        Customer.phone_1.like(search_pattern)
                    )
                )
                .limit(limit - len(results))
                .all()
            )
            for c in partial_matches:
                if c.id not in seen_ids:
                    seen_ids.add(c.id)
                    results.append(CustomerSearchOut(
                        id=c.id,
                        party_code=c.party_code,
                        party_name=c.party_name,
                        contact_person_1=c.contact_person_1,
                        email_id_1=c.email_id_1,
                        city=c.city,
                        state=c.state,
                        phone_1=c.phone_1,
                        phone_1_normalized=c.phone_1_normalized,
                        status=c.status,
                        assigned_employee_name=c.assigned_employee.full_name if c.assigned_employee else None,
                        match_type="partial_match"
                    ))

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return results, elapsed_ms

    @staticmethod
    def lookup_by_phone(db: Session, phone_number: str) -> Optional[Customer]:
        """
        Direct, instantaneous single-customer lookup for incoming Smartflo/CTI calls.
        Matches against Primary Phone Number AND all linked Additional Phone Numbers.
        """
        if not phone_number:
            return None

        phone_variants = PhoneNormalizer.get_search_variants(phone_number)
        clean = PhoneNormalizer.clean_digits(phone_number)
        norm = PhoneNormalizer.normalize(phone_number)

        # 1. Primary phone search (phone_1_normalized)
        if phone_variants:
            cust = (
                db.query(Customer)
                .options(joinedload(Customer.assigned_employee))
                .filter(
                    Customer.is_archived == False,
                    Customer.phone_1_normalized.in_(phone_variants)
                )
                .first()
            )
            if cust:
                return cust

        # 2. Additional phone numbers search (CustomerPhoneNumber)
        if phone_variants:
            cust = (
                db.query(Customer)
                .join(CustomerPhoneNumber, Customer.id == CustomerPhoneNumber.customer_id)
                .options(joinedload(Customer.assigned_employee))
                .filter(
                    Customer.is_archived == False,
                    CustomerPhoneNumber.phone_normalized.in_(phone_variants)
                )
                .first()
            )
            if cust:
                return cust

        # 3. Secondary fallback on raw phone_1 or clean digits
        filters = [Customer.phone_1.in_(phone_variants)] if phone_variants else []
        if norm:
            filters.append(Customer.phone_1_normalized == norm)
        if clean:
            filters.append(Customer.phone_1_normalized == clean)
        if clean and len(clean) >= 10:
            last10 = clean[-10:]
            filters.append(Customer.phone_1_normalized.like(f"%{last10}"))

        if filters:
            cust = (
                db.query(Customer)
                .options(joinedload(Customer.assigned_employee))
                .filter(
                    Customer.is_archived == False,
                    or_(*filters)
                )
                .first()
            )
            if cust:
                return cust

        # 4. Fallback search on CustomerPhoneNumber raw digits
        if clean and len(clean) >= 10:
            last10 = clean[-10:]
            cust = (
                db.query(Customer)
                .join(CustomerPhoneNumber, Customer.id == CustomerPhoneNumber.customer_id)
                .options(joinedload(Customer.assigned_employee))
                .filter(
                    Customer.is_archived == False,
                    (CustomerPhoneNumber.phone_normalized.like(f"%{last10}")) |
                    (CustomerPhoneNumber.phone_number.like(f"%{last10}"))
                )
                .first()
            )
            if cust:
                return cust

        return None
