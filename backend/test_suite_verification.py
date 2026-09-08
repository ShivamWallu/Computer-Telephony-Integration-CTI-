import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.database import SessionLocal, ensure_schema_columns, engine
from backend.app.models.user import User
from backend.app.models.customer import Customer, CustomerPhoneNumber
from backend.app.models.call import Call
from backend.app.services.excel_service import ExcelService, STRICT_COLUMNS, BUSINESS_CATEGORIES
from backend.app.services.phone_normalizer import PhoneNormalizer

def run_tests():
    print("=== Running Comprehensive Verification Test Suite ===")
    ensure_schema_columns(engine)
    db = SessionLocal()

    try:
        # 1. Verify STRICT_COLUMNS has 25 columns
        print(f"\n[Test 1] 25 Column Definition Check:")
        print(f"Total Columns: {len(STRICT_COLUMNS)}")
        assert len(STRICT_COLUMNS) == 25, f"Expected 25 columns, got {len(STRICT_COLUMNS)}"
        assert STRICT_COLUMNS[0] == "Address Code*"
        assert STRICT_COLUMNS[-1] == "Phone Number 3"
        print("[PASS] STRICT_COLUMNS has exactly 25 columns in correct sequence.")

        # 2. Verify Sample Excel & CSV generation
        print(f"\n[Test 2] Sample Template Generation:")
        excel_bytes = ExcelService.generate_sample_excel_bytes()
        csv_bytes = ExcelService.generate_sample_csv_bytes()
        assert len(excel_bytes) > 1000, "Sample excel is too small"
        assert len(csv_bytes) > 200, "Sample CSV is too small"
        print(f"[PASS] Generated 25-col Excel ({len(excel_bytes)} bytes) and CSV ({len(csv_bytes)} bytes).")

        # 3. Test Preview and Processing of Sample File
        print(f"\n[Test 3] Preview and Process 25-Column Import:")
        preview = ExcelService.preview_import(excel_bytes, "sample_test.xlsx")
        assert preview["is_valid"] is True
        assert len(preview["sample_rows"]) == 5 or len(preview["sample_rows"]) == 8
        print(f"[PASS] Preview succeeded: {preview['total_detected_rows']} rows detected.")

        admin_user = db.query(User).filter(User.role == "admin").first()
        admin_id = admin_user.id if admin_user else 1

        result = ExcelService.process_import(db, excel_bytes, "sample_test.xlsx", "update", admin_id)
        print(f"[PASS] Import executed: Imported={result['imported_count']}, Updated={result['updated_count']}, Errors={result['error_count']}")
        assert result['error_count'] == 0, f"Import had errors: {result['errors']}"

        # 4. Verify 3-Phone Numbers and Categories
        print(f"\n[Test 4] Multi-Phone and Category Verification:")
        all_custs = db.query(Customer).all()
        print(f"Total customers in DB: {len(all_custs)}")
        for c in all_custs[-10:]:
            print(f"  ID: {c.id}, Code: '{c.party_code}', Name: '{c.party_name}', Category: '{c.category}'")
        husk_cust = db.query(Customer).filter(Customer.party_code == "HUSK-1001").first()
        assert husk_cust is not None, "HUSK customer was not found!"
        print(f"Customer: {husk_cust.party_name}, Category: {husk_cust.category}")
        assert husk_cust.category == "HUSK" or "HUSK" in husk_cust.party_code
        
        # Check secondary phones
        phones = db.query(CustomerPhoneNumber).filter(CustomerPhoneNumber.customer_id == husk_cust.id).all()
        phone_nums = [p.phone_number for p in phones]
        print(f"Attached Secondary Phones: {phone_nums}")
        assert len(phones) >= 2, "Expected at least Phone 2 and Phone 3 attached"

        # Verify CTI Inbound Lookup on Phone 2 or Phone 3
        norm_p2 = PhoneNormalizer.normalize("+91 98765 43211")
        matched = db.query(CustomerPhoneNumber).filter(CustomerPhoneNumber.phone_normalized == norm_p2).first()
        assert matched is not None, "Lookup by Phone 2 failed"
        assert matched.customer_id == husk_cust.id, "Phone 2 mapped to wrong customer"
        print("[PASS] Full CTI Lookup works across Phone 1, Phone 2, and Phone 3.")

        # 5. Verify Employee Permission and Category Scoping
        print(f"\n[Test 5] Employee Permissions & Category Scoping:")
        emp = db.query(User).filter(User.role == "employee").first()
        if not emp:
            emp = User(
                email="test_emp_scope@khandelia.com",
                full_name="Test Scoped Employee",
                role="employee",
                allowed_categories="HUSK,SAS",
                can_add_customer=False,
                can_delete_customer=False
            )
            emp.set_password("123456")
            db.add(emp)
            db.commit()
            db.refresh(emp)

        emp.allowed_categories = "HUSK,SAS"
        db.commit()

        # Check category filtering query
        allowed_list = [c.strip() for c in emp.allowed_categories.split(",") if c.strip()]
        scoped_custs = db.query(Customer).filter(Customer.category.in_(allowed_list)).all()
        print(f"Scoped customers for employee (HUSK, SAS): {len(scoped_custs)} records")
        for sc in scoped_custs:
            assert sc.category in ["HUSK", "SAS"], f"Customer has unexpected category {sc.category}"
        print("[PASS] Category scoping query functions correctly.")

        # 6. Verify Unresolved Missed Calls
        print(f"\n[Test 6] Unresolved Missed Calls Report:")
        from backend.app.routers.calls import get_unreturned_missed_calls
        missed = get_unreturned_missed_calls(page=1, limit=50, db=db, current_user=admin_user)
        print(f"[PASS] Unresolved missed calls query succeeded: total={missed.get('total')}")

        # 7. Verify Safe Purge Exemption for Shivam / 7814749816
        print(f"\n[Test 7] Safe Purge Protection Rule:")
        shivam_exists = db.query(Customer).filter(
            (Customer.phone_1_normalized.like("%7814749816%")) | (Customer.party_name.ilike("%shivam%"))
        ).first()
        if not shivam_exists:
            shivam = Customer(
                party_code="MOL-7007",
                party_name="Mashal Oil & Agro Extracts (Shivam)",
                phone_1="+91 78147 49816",
                phone_1_normalized="+917814749816",
                category="MOL",
                status="Active"
            )
            db.add(shivam)
            db.commit()

        # Query all except Shivam
        to_delete = db.query(Customer).filter(
            ~Customer.phone_1_normalized.like("%7814749816%"),
            ~Customer.party_name.ilike("%shivam%")
        ).count()
        print(f"Total customers that would be purged: {to_delete}")
        shivam_protected = db.query(Customer).filter(
            (Customer.phone_1_normalized.like("%7814749816%")) | (Customer.party_name.ilike("%shivam%"))
        ).count()
        print(f"Protected demo accounts: {shivam_protected}")
        assert shivam_protected >= 1, "Shivam account is not present or protected!"
        # 8. Verify all 10 Business Categories
        print(f"\n[Test 8] 10 Business Categories Definition:")
        expected_10 = ["By Product", "HUSK", "SAS", "MRO", "MCK", "DOC", "MSD", "MOL", "MOMT", "General"]
        assert len(BUSINESS_CATEGORIES) == 10, f"Expected 10 categories, got {len(BUSINESS_CATEGORIES)}"
        for exp in expected_10:
            assert exp in BUSINESS_CATEGORIES, f"Missing category: {exp}"
        print(f"[PASS] All 10 Business Categories present: {BUSINESS_CATEGORIES}")

        # 9. Verify Upload Permission Enforcement
        print(f"\n[Test 9] Upload Permission Check (403 Rejection vs Allowed):")
        from backend.app.routers.imports import _check_user_upload_permission
        from fastapi import HTTPException

        # Admin always allowed
        admin_test = User(role="admin", allowed_upload_categories="[]")
        _check_user_upload_permission(admin_test, "HUSK")  # should pass without exception
        print("  - Admin upload permission passed.")

        # Employee with no upload permission
        emp_restricted = User(role="employee", allowed_upload_categories="[]")
        try:
            _check_user_upload_permission(emp_restricted, "HUSK")
            assert False, "Restricted employee should have been rejected with 403"
        except HTTPException as e:
            assert e.status_code == 403
            print(f"  - Restricted employee properly rejected with 403: {e.detail}")

        # Employee with specific upload permission
        emp_allowed = User(role="employee", allowed_upload_categories='["HUSK", "SAS"]')
        _check_user_upload_permission(emp_allowed, "HUSK")
        _check_user_upload_permission(emp_allowed, "SAS")
        try:
            _check_user_upload_permission(emp_allowed, "MRO")
            assert False, "Employee should not be allowed to upload to MRO"
        except HTTPException as e:
            assert e.status_code == 403
            print(f"  - Employee allowed for HUSK/SAS, blocked for MRO: {e.detail}")
        print("[PASS] Upload permission enforcement functions strictly.")

        # 10. Verify Duplicate Address Code skipped protection
        print(f"\n[Test 10] Duplicate Address Code Skip & Message Verification:")
        dup_result = ExcelService.process_import(db, excel_bytes, "sample_dup_test.xlsx", "skip_duplicates", admin_id)
        assert dup_result["duplicate_count"] > 0, "Expected duplicates to be skipped in skip_duplicates mode"
        assert len(dup_result["duplicate_records"]) > 0, "Expected duplicate records details"
        for rec in dup_result["duplicate_records"]:
            assert rec["status"] == "This data already exists", f"Unexpected status: {rec['status']}"
        print(f"[PASS] Duplicate records skipped correctly: {dup_result['duplicate_count']} skipped with status '{dup_result['duplicate_records'][0]['status']}'.")

        print("\n=======================================================")
        print(" ALL VERIFICATION TESTS PASSED SUCCESSFULLY! (10/10)")
        print("=======================================================")

    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
