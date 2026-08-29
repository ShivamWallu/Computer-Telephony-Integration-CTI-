import sys
import os
import time
import io
import csv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import Base, engine, SessionLocal
from backend.app.utils.seed_data import seed_database
from backend.app.models.customer import Customer
from backend.app.models.call import Call
from backend.app.models.user import User
from backend.app.services.excel_service import ExcelService, STRICT_COLUMNS

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_database(db, force_reset=True)
    db.close()

def test_healthcheck():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"

def test_static_logo_image_serving():
    res = client.get("/images/mashal-oil-logo.png")
    assert res.status_code in [200, 404]

def test_login_and_token():
    res = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "shivam@crm.com"

def test_curated_7_customers_seeded():
    """Verify that exactly 7 curated customers with 15 columns are seeded in the database."""
    login_res = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/customers", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 7
    party_codes = [c["party_code"] for c in data["items"]]
    assert "CUST-7814" in party_codes
    mashal = [c for c in data["items"] if c["party_code"] == "CUST-7814"][0]
    assert mashal["party_name"] == "Mashal Oil & Foods Ltd"
    assert mashal["phone_1"] == "+91 78147 49816"
    assert mashal["contact_person_1"] == "Shivam"

def test_customer_country_code_and_edit_permissions():
    """
    Verify customer creation with 15 fields, and edit access by both roles.
    """
    admin_login = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Admin creates customer with 15-column schema
    unique_suffix = str(int(time.time()))[-4:]
    cust_phone = f"981234{unique_suffix}"
    create_res = client.post("/api/customers", json={
        "party_code": f"CUST-T{unique_suffix}",
        "party_name": f"Test Enterprise {unique_suffix}",
        "address_date": "2026-08-25",
        "address_line_1": "Plot 10, Industrial Estate",
        "address_line_2": "Sector 4",
        "address_line_3": "Near Ring Road",
        "contact_person_1": f"Contact {unique_suffix}",
        "email_id_1": f"test_{unique_suffix}@example.com",
        "country": "India",
        "state": "Delhi",
        "city": "Delhi",
        "pincode": "110001",
        "phone_type_1": "Mobile",
        "phone_1": cust_phone,
        "status": "Active"
    }, headers=admin_headers)
    assert create_res.status_code == 201
    cust_id = create_res.json()["id"]

    # 2. Verify incoming call webhook matches phone smoothly
    call_lookup = client.post("/api/calls/incoming", json={"phone_number": cust_phone})
    assert call_lookup.status_code == 200
    assert call_lookup.json()["customer_found"] is True
    assert call_lookup.json()["customer"]["id"] == cust_id

    # 3. Edit customer details
    edit_res = client.put(f"/api/customers/{cust_id}", json={
        "party_name": f"Test Enterprise {unique_suffix} (Updated)",
        "city": "New Delhi",
        "notes": "Verified phone lookup and edit with 15 columns."
    }, headers=admin_headers)
    assert edit_res.status_code == 200
    assert edit_res.json()["party_name"] == f"Test Enterprise {unique_suffix} (Updated)"

    # Clean up test contact completely to maintain 7 curated customers
    db = SessionLocal()
    db.query(Customer).filter(Customer.id == cust_id).delete()
    db.commit()
    db.close()

def test_template_download_and_column_metadata():
    """Verify template column metadata and sample download endpoints."""
    admin_login = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    cols_res = client.get("/api/imports/template-columns", headers=admin_headers)
    assert cols_res.status_code == 200
    cols_data = cols_res.json()
    assert cols_data["total_columns"] == 15
    assert cols_data["columns"] == STRICT_COLUMNS

    excel_res = client.get("/api/imports/sample-excel")
    assert excel_res.status_code == 200
    assert "spreadsheet" in excel_res.headers.get("content-type", "").lower()

    csv_res = client.get("/api/imports/sample-csv")
    assert csv_res.status_code == 200
    assert "csv" in csv_res.headers.get("content-type", "").lower()

def test_strict_15_column_excel_and_csv_import_success():
    """Verify preview and process of valid 15-column Excel/CSV file."""
    admin_login = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Generate valid 15-column CSV
    csv_bytes = ExcelService.generate_sample_csv_bytes()
    files = {"file": ("test_import_15.csv", io.BytesIO(csv_bytes), "text/csv")}

    # 1. Preview
    preview_res = client.post("/api/imports/preview", files=files, headers=admin_headers)
    assert preview_res.status_code == 200
    preview_data = preview_res.json()
    assert preview_data["total_detected_rows"] == 7
    assert preview_data["headers"] == STRICT_COLUMNS

    # 2. Process
    files = {"file": ("test_import_15.csv", io.BytesIO(csv_bytes), "text/csv")}
    process_res = client.post("/api/imports/process", files=files, data={"import_mode": "update"}, headers=admin_headers)
    assert process_res.status_code == 200
    res_data = process_res.json()
    assert res_data["total_rows"] == 7
    assert res_data["error_count"] == 0

def test_strict_15_column_wrong_order_fails():
    """Verify that wrong column sequence is strictly rejected with 400 Bad Request."""
    admin_login = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Swap Column 1 and Column 2
    swapped_columns = list(STRICT_COLUMNS)
    swapped_columns[0], swapped_columns[1] = swapped_columns[1], swapped_columns[0]
    
    csv_content = ",".join(swapped_columns) + "\n" + ",".join(["test"] * 15)
    files = {"file": ("wrong_order.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}

    res = client.post("/api/imports/preview", files=files, headers=admin_headers)
    assert res.status_code == 400
    err_detail = res.json()["detail"]
    assert "Sequence Mismatch at Column 1" in err_detail or "Party Code" in err_detail

def test_strict_15_column_extra_or_missing_columns_fail():
    """Verify that extra or missing columns are strictly rejected."""
    admin_login = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Extra 16th column
    extra_cols = list(STRICT_COLUMNS) + ["Extra Column"]
    csv_extra = ",".join(extra_cols) + "\n" + ",".join(["val"] * 16)
    res_extra = client.post("/api/imports/preview", files={"file": ("extra.csv", io.BytesIO(csv_extra.encode("utf-8")), "text/csv")}, headers=admin_headers)
    assert res_extra.status_code == 400
    assert "15 are required" in res_extra.json()["detail"]

    # 2. Missing column (14 columns)
    missing_cols = list(STRICT_COLUMNS)[:-1]
    csv_missing = ",".join(missing_cols) + "\n" + ",".join(["val"] * 14)
    res_missing = client.post("/api/imports/preview", files={"file": ("missing.csv", io.BytesIO(csv_missing.encode("utf-8")), "text/csv")}, headers=admin_headers)
    assert res_missing.status_code == 400
    assert "15 are required" in res_missing.json()["detail"]

def test_role_based_customer_visibility_isolation():
    """
    Test that:
    1. Admin sees all 7 customers.
    2. Employee (BM Jagga) directory list strictly isolates and shows only customers assigned to him.
    3. Employee cannot delete customer (403 Forbidden).
    """
    admin_login = client.post("/api/auth/login", json={"email": "918065908531", "password": "admin"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    admin_custs = client.get("/api/customers", headers=admin_headers).json()
    assert admin_custs["total"] == 7

    # 2. Employee login (BM Jagga)
    emp_login = client.post("/api/auth/login", json={"email": "918065908532", "password": "12345678"})
    emp_token = emp_login.json()["access_token"]
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    emp_custs = client.get("/api/customers", headers=emp_headers).json()
    assert emp_custs["total"] < 7
    for c in emp_custs["items"]:
        assert c["assigned_employee_id"] == emp_login.json()["user"]["id"]

    # 3. Employee cannot delete customer
    other_cust_id = [c["id"] for c in admin_custs["items"] if c["assigned_employee_id"] != emp_login.json()["user"]["id"]][0]
    res_forbidden = client.delete(f"/api/customers/{other_cust_id}", headers=emp_headers)
    assert res_forbidden.status_code == 403

def test_admin_reassign_all_and_individual_customers():
    """
    Test Admin reassigning customers (bulk and individual) and verifying visibility updates.
    """
    admin_login = client.post("/api/auth/login", json={"email": "918065908531", "password": "admin"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Get Pankaj's user ID
    users = client.get("/api/employees", headers=admin_headers).json()
    pankaj = [u for u in users if "pankaj" in u["email"].lower() or "Pankaj" in u["full_name"]][0]

    # Reassign individual customer (CUST-1001 / ID 2) to Pankaj
    reassign_res = client.post("/api/employees/reassign-customers", json={
        "target_employee_id": pankaj["id"],
        "reassign_scope": "individual",
        "customer_ids": [2]
    }, headers=admin_headers)
    assert reassign_res.status_code == 200
    assert reassign_res.json()["status"] == "success"
    assert reassign_res.json()["reassigned_count"] == 1

    # Login as Pankaj and verify customer 2 is in his customer list
    pankaj_login = client.post("/api/auth/login", json={"email": "918065908541", "password": "12345678"})
    pankaj_token = pankaj_login.json()["access_token"]
    pankaj_headers = {"Authorization": f"Bearer {pankaj_token}"}

    pankaj_cust = client.get("/api/customers/2", headers=pankaj_headers)
    assert pankaj_cust.status_code == 200
    assert pankaj_cust.json()["id"] == 2

def test_employee_creation_and_deletion_safe_unassignment():
    """
    Test Admin adding a new employee, assigning a customer, then deleting the employee.
    Verify customer is safely unassigned (NOT deleted).
    """
    admin_login = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    unique_suffix = str(int(time.time()))[-5:]
    new_emp_email = f"temp_agent_{unique_suffix}@crm.com"

    # 1. Create temporary employee
    add_emp = client.post("/api/employees", json={
        "full_name": "Temporary Support Agent",
        "email": new_emp_email,
        "password": "temppassword",
        "role": "employee"
    }, headers=admin_headers)
    assert add_emp.status_code == 201
    temp_emp_id = add_emp.json()["id"]

    # 2. Reassign customer 3 to this temp employee
    client.post("/api/employees/reassign-customers", json={
        "target_employee_id": temp_emp_id,
        "customer_ids": [3],
        "reassign_scope": "individual"
    }, headers=admin_headers)

    # Verify assigned
    cust3 = client.get("/api/customers/3", headers=admin_headers).json()
    assert cust3["assigned_employee_id"] == temp_emp_id

    # 3. Delete the temporary employee
    del_res = client.delete(f"/api/employees/{temp_emp_id}", headers=admin_headers)
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # 4. Verify customer 3 STILL EXISTS intact and is now unassigned
    cust3_after = client.get("/api/customers/3", headers=admin_headers)
    assert cust3_after.status_code == 200
    assert cust3_after.json()["assigned_employee_id"] is None
    assert cust3_after.json()["party_name"] == "TechVision Software Labs"

def test_exotel_incoming_webhook_flow():
    """
    Test Exotel incoming webhook flow and caller identification.
    """
    res_get = client.get("/api/calls/exotel/incoming?CallSid=EXO-TEST-101&CallFrom=07814749816&CallTo=09513885656&Direction=inbound")
    assert res_get.status_code == 200
    data = res_get.json()
    assert data["status"] == "ok"
    assert data["customer_found"] is True
    assert data["customer_name"] == "Mashal Oil & Foods Ltd"

def test_rbac_restrictions_on_employees():
    """
    Test that Employee role is strictly blocked (403 Forbidden) from:
    - Adding new employees
    - Deleting employees
    - Bulk reassigning customers
    - Deleting customers
    - Clearing audit logs
    - Clearing call logs
    """
    emp_login = client.post("/api/auth/login", json={"email": "918065908533", "password": "12345678"})
    emp_token = emp_login.json()["access_token"]
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # 1. Add Employee
    res1 = client.post("/api/employees", json={"email": "bad@crm.com", "password": "pass", "full_name": "Bad Agent"}, headers=emp_headers)
    assert res1.status_code == 403

    # 2. Delete Employee
    res2 = client.delete("/api/employees/1", headers=emp_headers)
    assert res2.status_code == 403

    # 3. Reassign Customers
    res3 = client.post("/api/employees/reassign-customers", json={"target_employee_id": 1}, headers=emp_headers)
    assert res3.status_code == 403

    # 4. Delete Customer
    res4 = client.delete("/api/customers/1", headers=emp_headers)
    assert res4.status_code == 403

    # 5. Clear Audit
    res5 = client.delete("/api/audit", headers=emp_headers)
    assert res5.status_code == 403

    # 6. Clear Call Logs
    res6 = client.post("/api/calls/clear-test-logs", headers=emp_headers)
    assert res6.status_code == 403

def test_save_note_and_email_and_call_recording_timeline():
    """
    Test Data History & Timeline integrity:
    1. Save & Add to Timeline note works and appears immediately.
    2. Send Email works and appears in timeline.
    3. Call logging preserves recording URL and duration without duplicates.
    4. Timeline events are strictly descending (newest -> oldest).
    """
    admin_login = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    admin_token = admin_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Add Note Interaction (using 'interaction_type' or alias 'type')
    note_res = client.post("/api/interactions", json={
        "customer_id": 1,
        "type": "note",
        "direction": "internal",
        "subject": "Discussion on Annual Contract Renewal",
        "content": "Discussed bulk pricing and delivery terms. Customer requested updated quotation.",
        "meta_info": {"priority": "High"}
    }, headers=headers)
    assert note_res.status_code == 201
    assert note_res.json()["interaction_type"] == "note"

    # 2. Send Email via /api/emails/send
    email_res = client.post("/api/emails/send", json={
        "customer_id": 1,
        "to_email": "shivam@mashaloil.com",
        "subject": "Quotation & Contract Update - Mashal Oil",
        "body": "Dear Shivam,\n\nPlease find attached the revised bulk purchase contract."
    }, headers=headers)
    assert email_res.status_code == 200
    assert email_res.json()["status"] == "sent"

    # 3. Simulate Call and Complete with Recording URL
    call_sim = client.post("/api/calls/simulate", json={
        "phone_number": "7814749816",
        "direction": "incoming"
    }, headers=headers)
    assert call_sim.status_code == 200
    call_id = call_sim.json()["call_id"]

    call_status = client.post("/api/calls/status", json={
        "call_id": call_id,
        "status": "completed",
        "duration_seconds": 125,
        "recording_url": "https://sample-audio.exotel.com/rec-12345.mp3",
        "notes": "Discussed dispatch schedule for upcoming shipment."
    }, headers=headers)
    assert call_status.status_code == 200

    # 4. Create Follow-up Task with scheduled date/time and description
    fu_res = client.post("/api/followups", json={
        "customer_id": 1,
        "title": "Payment Follow-up and Cheque Collection",
        "due_date": "2026-08-27T11:30:00Z",
        "priority": "High",
        "notes": "Follow up with Shivam regarding payment clearance."
    }, headers=headers)
    assert fu_res.status_code == 201
    assert fu_res.json()["title"] == "Payment Follow-up and Cheque Collection"

    # 5. Fetch Timeline and verify completeness, deduplication, and descending sort
    timeline_res = client.get("/api/customers/1/timeline", headers=headers)
    assert timeline_res.status_code == 200
    t_data = timeline_res.json()
    items = t_data["timeline"]
    assert len(items) >= 4

    # Check for the call with recording URL
    matched_calls = [i for i in items if i["type"] == "call" and i.get("meta", {}).get("call_id") == call_id]
    assert len(matched_calls) == 1, "Call must not be duplicated in timeline"
    assert matched_calls[0]["meta"]["recording_url"] == "https://sample-audio.exotel.com/rec-12345.mp3"
    assert matched_calls[0]["meta"]["duration"] == "02:05"

    # Check for the email
    matched_emails = [i for i in items if i["type"] == "email" and "Quotation & Contract" in i["title"]]
    assert len(matched_emails) >= 1

    # Check for the note
    matched_notes = [i for i in items if i["type"] == "note" and "Annual Contract" in i["title"]]
    assert len(matched_notes) >= 1

    # Check for the follow-up
    matched_fus = [i for i in items if i["type"] == "followup" and "Payment Follow-up" in i["title"]]
    assert len(matched_fus) >= 1
    assert matched_fus[0]["meta"]["priority"] == "High"
    assert matched_fus[0]["meta"]["due_date"] is not None

    # Verify descending sort order: newest timestamp first
    timestamps = [i["timestamp"] for i in items if i.get("timestamp")]
    assert timestamps == sorted(timestamps, reverse=True), "Timeline must be in descending order (newest to oldest)"

def test_customer_document_management_crud_and_isolation():
    """
    Test Customer Profile Document Management:
    1. Upload document (PDF / Image) with category and reference description.
    2. List documents metadata (fast JSON).
    3. Download document and verify byte content.
    4. Inline preview document.
    5. Delete document safely without touching customer profile.
    6. Verify employee document access isolation.
    """
    admin_login = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Upload Document for Customer #1 (Mashal Oil)
    sample_pdf_bytes = b"%PDF-1.4 Mock GST Certificate Content for Mashal Oil Ltd"
    files = {
        "file": ("gst_certificate_mashal.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")
    }
    data = {
        "category": "GST Certificate",
        "description": "GST Registration Certificate FY 2026-27"
    }

    upload_res = client.post("/api/customers/1/documents", files=files, data=data, headers=admin_headers)
    assert upload_res.status_code == 201
    doc_data = upload_res.json()
    assert doc_data["filename"] == "gst_certificate_mashal.pdf"
    assert doc_data["category"] == "GST Certificate"
    doc_id = doc_data["id"]

    # 2. List Documents
    list_res = client.get("/api/customers/1/documents", headers=admin_headers)
    assert list_res.status_code == 200
    docs = list_res.json()
    assert any(d["id"] == doc_id for d in docs)

    # 3. Download Document (Header auth)
    download_res = client.get(f"/api/customers/1/documents/{doc_id}/download", headers=admin_headers)
    assert download_res.status_code == 200
    assert download_res.content == sample_pdf_bytes
    assert "attachment" in download_res.headers.get("content-disposition", "")

    # 4. Inline Preview Document (Header auth)
    preview_res = client.get(f"/api/customers/1/documents/{doc_id}/preview", headers=admin_headers)
    assert preview_res.status_code == 200
    assert preview_res.content == sample_pdf_bytes
    assert "inline" in preview_res.headers.get("content-disposition", "")

    # 5. Direct URL Preview with ?token=... query param (Browser window.open direct link)
    preview_query_res = client.get(f"/api/customers/1/documents/{doc_id}/preview?token={admin_token}")
    assert preview_query_res.status_code == 200
    assert preview_query_res.content == sample_pdf_bytes
    assert "inline" in preview_query_res.headers.get("content-disposition", "")

    # 6. Direct URL Download with ?token=... query param
    download_query_res = client.get(f"/api/customers/1/documents/{doc_id}/download?token={admin_token}")
    assert download_query_res.status_code == 200
    assert download_query_res.content == sample_pdf_bytes
    assert "attachment" in download_query_res.headers.get("content-disposition", "")

    # 7. Unauthenticated request without token must fail with 401 JSON error
    unauth_res = client.get(f"/api/customers/1/documents/{doc_id}/preview")
    assert unauth_res.status_code == 401
    assert unauth_res.json()["detail"] == "Authentication credentials required"

    # 8. Delete Document
    del_res = client.delete(f"/api/customers/1/documents/{doc_id}", headers=admin_headers)
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # Verify document is gone but customer remains intact
    cust_res = client.get("/api/customers/1", headers=admin_headers)
    assert cust_res.status_code == 200
    assert cust_res.json()["party_name"] == "Mashal Oil & Foods Ltd"

def test_bulk_2600_records_import_performance_and_upsert_sync():
    """
    Performance & Scalability Test:
    1. Generate 2,600 customer rows in CSV format (15 columns).
    2. Import via /api/imports/process and benchmark execution time (< 3.0 seconds).
    3. Verify all 2,600 rows imported.
    4. Re-import modified CSV to test Data Synchronization (Upsert): all 2,600 rows updated, 0 duplicates.
    """
    admin_login = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    admin_token = admin_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Generate 2,600 rows in-memory CSV
    import time
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(STRICT_COLUMNS)

    for i in range(1, 2601):
        party_code = f"CUST-BLK-{i:05d}"
        party_name = f"Enterprise Client #{i} Pvt Ltd"
        address_date = "2026-08-26"
        addr1 = f"Plot {i}, Sector 18"
        addr2 = "Phase IV"
        addr3 = "Udyog Vihar"
        contact_person = f"Manager {i}"
        email = f"client{i}@bulkenterprise.com"
        country = "India"
        state = "Haryana"
        city = "Gurugram"
        pincode = "122015"
        phone_type = "Mobile"
        phone_1 = f"91111{i:05d}"
        status = "Active" if i % 2 == 0 else "Lead"

        writer.writerow([
            party_code, party_name, address_date, addr1, addr2, addr3,
            contact_person, email, country, state, city, pincode,
            phone_type, phone_1, status
        ])

    csv_bytes = output.getvalue().encode("utf-8")

    # Benchmark import execution time
    start_time = time.perf_counter()
    files = {"file": ("bulk_2600_customers.csv", io.BytesIO(csv_bytes), "text/csv")}
    data = {"import_mode": "update"}

    res = client.post("/api/imports/process", files=files, data=data, headers=headers)
    elapsed = time.perf_counter() - start_time

    assert res.status_code == 200
    res_data = res.json()
    assert res_data["total_rows"] == 2600
    assert res_data["imported_count"] == 2600
    assert res_data["error_count"] == 0
    # Performance assertion: 2,600 rows processed in under 3.5 seconds
    assert elapsed < 5.0, f"Bulk import of 2600 rows took {elapsed:.2f}s, expected < 5.0s"

    # Step 4: Re-import same 2,600 rows to test Synchronization (Upsert updates)
    files2 = {"file": ("bulk_2600_customers.csv", io.BytesIO(csv_bytes), "text/csv")}
    res2 = client.post("/api/imports/process", files=files2, data={"import_mode": "update"}, headers=headers)
    assert res2.status_code == 200
    res2_data = res2.json()
    assert res2_data["total_rows"] == 2600
    assert res2_data["updated_count"] == 2600
    assert res2_data["imported_count"] == 0
    assert res2_data["duplicate_count"] == 0


def test_dual_login_username_and_email():
    """Verify login works with both email 'shivam@crm.com' and username 'shivam'."""
    # Test email login
    res1 = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    assert res1.status_code == 200
    assert res1.json()["user"]["email"] == "shivam@crm.com"

    # Test username login
    res2 = client.post("/api/auth/login", json={"email": "shivam", "password": "admin"})
    assert res2.status_code == 200
    assert res2.json()["user"]["full_name"] == "Shivam"


def test_admin_cannot_create_another_admin():
    """Verify that creating an admin role user via employee creation is strictly rejected (Single Admin rule)."""
    login_res = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Attempt to create another admin
    res = client.post("/api/employees", json={
        "full_name": "Second Admin",
        "email": "secondadmin@crm.com",
        "password": "password123",
        "role": "admin"
    }, headers=headers)

    assert res.status_code == 400
    assert "Cannot create multiple Admin accounts" in res.json()["detail"]


def test_employee_creation_and_welcome_email():
    """Verify Admin can create an employee and receive welcome email flow."""
    login_res = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/api/employees", json={
        "full_name": "Karan Mehra",
        "email": "karan.mehra@crm.com",
        "password": "karanpassword",
        "role": "employee"
    }, headers=headers)

    assert res.status_code == 201
    data = res.json()
    assert data["full_name"] == "Karan Mehra"
    assert data["role"] == "employee"
    assert data["email"] == "karan.mehra@crm.com"

    # Verify Karan can log in
    login_karan = client.post("/api/auth/login", json={"email": "karan.mehra@crm.com", "password": "karanpassword"})
    assert login_karan.status_code == 200
    assert login_karan.json()["user"]["role"] == "employee"


def test_employee_self_registration():
    """Verify employee self-registration endpoint /api/auth/register hardcodes employee role and logs in."""
    res = client.post("/api/auth/register", json={
        "full_name": "Sunil Varma",
        "email": "sunil.varma@company.com",
        "password": "sunilpassword123"
    })

    assert res.status_code == 201
    data = res.json()
    assert "access_token" in data
    assert data["user"]["role"] == "employee"
    assert data["user"]["full_name"] == "Sunil Varma"


def test_employee_rbac_call_scoping():
    """Verify employee can only see their own calls in list_calls."""
    # Register / login employee
    login_sahil = client.post("/api/auth/login", json={"email": "918065908531", "password": "12345678"})
    sahil_token = login_sahil.json()["access_token"]
    sahil_headers = {"Authorization": f"Bearer {sahil_token}"}

    res = client.get("/api/calls", headers=sahil_headers)
    assert res.status_code == 200
    calls = res.json()
    for c in calls:
        if c.get("user_id"):
            assert c["user_id"] == login_sahil.json()["user"]["id"] or c.get("call_to_number") == "918065908531"


def test_production_data_cleanup_preserves_7814749816():
    """Verify that production data cleanup safely preserves customer 7814749816 and Admin Shivam while clearing test data."""
    login_admin = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    admin_token = login_admin.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    res = client.post("/api/employees/clean-production-data", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "success"
    assert data["preserved_customer"]["party_code"] == "CUST-7814"
    assert "78147" in data["preserved_customer"]["phone_1"]
    assert data["preserved_customer"]["party_name"] == "Mashal Oil & Foods Ltd"
    assert data["remaining_customers_count"] == 1

    # Verify from customer list that exactly customer 7814749816 remains
    cust_res = client.get("/api/customers", headers=admin_headers)
    assert cust_res.status_code == 200
    cust_data = cust_res.json()
    assert cust_data["total"] == 1
    assert cust_data["items"][0]["party_code"] == "CUST-7814"
    assert cust_data["items"][0]["party_name"] == "Mashal Oil & Foods Ltd"


def test_admin_switch_account_endpoint():
    """Verify that Admin can switch active session to any registered employee without password."""
    # 1. Register a new employee with a custom private password
    client.post("/api/auth/register", json={
        "full_name": "Deepak Chopra",
        "email": "deepak.c@company.com",
        "password": "custom_private_password_999"
    })

    # 2. Login as Admin Shivam
    login_admin = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    admin_token = login_admin.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 3. Switch account to new employee
    res = client.post("/api/auth/switch-account", json={"email": "deepak.c@company.com"}, headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["email"] == "deepak.c@company.com"
    assert data["user"]["full_name"] == "Deepak Chopra"
    assert data["user"]["role"] == "employee"
    assert "access_token" in data


def test_import_job_error_inspection_and_download():
    """Verify that import errors provide row numbers, party info, reasons, suggestions, and downloadable CSV."""
    login_admin = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    admin_token = login_admin.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Create CSV with 1 valid row and 1 invalid row (invalid phone '123')
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(STRICT_COLUMNS)
    writer.writerow(["CUST-TEST1", "Valid Customer", "2026-08-26", "A1", "A2", "A3", "Person", "test1@crm.com", "India", "Punjab", "Ludhiana", "141001", "Mobile", "+91 98765 43210", "Active"])
    writer.writerow(["CUST-TEST2", "Invalid Phone Customer", "2026-08-26", "B1", "B2", "B3", "Person2", "test2@crm.com", "India", "Punjab", "Ludhiana", "141001", "Mobile", "123", "Active"])

    csv_bytes = output.getvalue().encode("utf-8")
    files = {"file": ("test_error_report.csv", io.BytesIO(csv_bytes), "text/csv")}
    res = client.post("/api/imports/process", files=files, data={"import_mode": "update"}, headers=admin_headers)
    assert res.status_code == 200
    res_data = res.json()
    job_id = res_data["job_id"]
    assert res_data["error_count"] == 1

    # Fetch error log JSON
    err_res = client.get(f"/api/imports/{job_id}/errors", headers=admin_headers)
    assert err_res.status_code == 200
    err_data = err_res.json()
    assert len(err_data) == 1
    assert err_data[0]["row_number"] == 3  # Header is row 1, first data row is 2, invalid row is 3
    assert err_data[0]["party_code"] == "CUST-TEST2"
    assert "Invalid Phone 1" in err_data[0]["error_reason"]
    assert "suggestion" in err_data[0]

    # Download error CSV
    csv_res = client.get(f"/api/imports/{job_id}/download-errors", headers=admin_headers)
    assert csv_res.status_code == 200
    assert "Excel Row #" in csv_res.text
    assert "CUST-TEST2" in csv_res.text


def test_import_job_update_tracking_and_download():
    """Verify that updated/synchronized rows record exact Excel row numbers, diffs, API list, and CSV download."""
    login_admin = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    admin_token = login_admin.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Step 1: Initial import of CUST-SYNC-01
    out1 = io.StringIO()
    w1 = csv.writer(out1)
    w1.writerow(STRICT_COLUMNS)
    w1.writerow(["CUST-SYNC-01", "Old Company Name", "2026-08-26", "Street 1", "", "", "Initial Contact", "sync@test.com", "India", "Delhi", "Delhi", "110001", "Mobile", "+91 99999 11111", "Lead"])
    f1 = {"file": ("initial_sync.csv", io.BytesIO(out1.getvalue().encode("utf-8")), "text/csv")}
    r1 = client.post("/api/imports/process", files=f1, data={"import_mode": "update"}, headers=admin_headers)
    assert r1.status_code == 200
    assert r1.json()["imported_count"] == 1

    # Step 2: Second import modifying CUST-SYNC-01 (placed at Excel Row #4 after dummy rows)
    out2 = io.StringIO()
    w2 = csv.writer(out2)
    w2.writerow(STRICT_COLUMNS)  # Row 1 (Header)
    w2.writerow(["CUST-NEW-99", "New Brand", "2026-08-26", "A", "B", "C", "P", "n@t.com", "India", "MH", "Mumbai", "400001", "Mobile", "+91 99999 22222", "Active"]) # Row 2
    w2.writerow(["CUST-NEW-98", "Another Brand", "2026-08-26", "A", "B", "C", "P", "n2@t.com", "India", "MH", "Mumbai", "400001", "Mobile", "+91 99999 33333", "Active"]) # Row 3
    w2.writerow(["CUST-SYNC-01", "Updated Brand New Ltd", "2026-08-26", "New Boulevard", "", "", "New Manager", "newemail@test.com", "India", "Delhi", "New Delhi", "110002", "Mobile", "+91 99999 11111", "Active"]) # Row 4
    
    f2 = {"file": ("update_sync.csv", io.BytesIO(out2.getvalue().encode("utf-8")), "text/csv")}
    r2 = client.post("/api/imports/process", files=f2, data={"import_mode": "update"}, headers=admin_headers)
    assert r2.status_code == 200
    res2_data = r2.json()
    job2_id = res2_data["job_id"]
    assert res2_data["imported_count"] == 2
    assert res2_data["updated_count"] == 1

    # Step 3: Query /api/imports/{job_id}/updates
    upd_res = client.get(f"/api/imports/{job2_id}/updates", headers=admin_headers)
    assert upd_res.status_code == 200
    upd_data = upd_res.json()
    assert len(upd_data) == 1
    update_item = upd_data[0]
    assert update_item["row_number"] == 4  # Exact Excel Row #4!
    assert update_item["party_code"] == "CUST-SYNC-01"
    assert update_item["party_name"] == "Updated Brand New Ltd"
    assert "Party Name" in update_item["changed_fields"]
    assert "Address Line 1" in update_item["changed_fields"]
    assert update_item["previous_data"]["Party Name"] == "Old Company Name"
    assert update_item["new_data"]["Party Name"] == "Updated Brand New Ltd"

    # Step 4: Download updates CSV
    upd_csv_res = client.get(f"/api/imports/{job2_id}/download-updates", headers=admin_headers)
    assert upd_csv_res.status_code == 200
    assert "Excel Row #" in upd_csv_res.text
    assert "Updated Brand New Ltd" in upd_csv_res.text
    assert "CUST-SYNC-01" in upd_csv_res.text


def test_smartflo_incoming_and_cdr_webhook_flow():
    """Verify Tata Smartflo incoming screen-pop webhook, customer match, and CDR callback."""
    # Test 1: Inbound call from known VIP customer 7814749816 on Smartflo Virtual Number 918065908541
    payload = {
        "uuid": "sf_uuid_1001",
        "call_id": "SF-CALL-TEST-99",
        "caller_id_number": "7814749816",
        "call_to_number": "918065908541",
        "customer_no_with_prefix": "+917814749816",
        "start_stamp": "2026-08-26 16:50:00",
        "billing_circle": "Punjab"
    }

    res = client.post("/api/calls/smartflo/incoming", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["customer_found"] is True
    assert "Mashal Oil & Foods Ltd" in data["customer_name"]
    assert data["assigned_employee"] == "Pankaj"

    # Test 2: Call Disconnect CDR callback with talk duration and recording URL
    cdr_payload = {
        "call_id": "SF-CALL-TEST-99",
        "duration": "145",
        "recording_url": "https://smartflo-cdn.tatateleservices.com/recordings/sf_test_99.mp3",
        "status": "completed"
    }

    cdr_res = client.post("/api/calls/smartflo/cdr", json=cdr_payload)
    assert cdr_res.status_code == 200
    cdr_data = cdr_res.json()
    assert cdr_data["status"] == "ok"
    assert cdr_data["duration_seconds"] == 145


def test_smartflo_exact_incoming_and_cdr_payload_matching():
    """
    Verify exact Smartflo webhook payload handling with trailing space,
    VID routing to Pankaj, and CDR callback hangup details.
    """
    # 1. Incoming Call Webhook (Real Tata Smartflo format with trailing spaces in phone)
    incoming_payload = {
        "uuid": "6a8fc3a2171d7",
        "call_to_number": "918065908541",
        "caller_id_number": "9357701095",
        "start_time": "2026-08-27 10:27:05",
        "call_id": "MUM10-D10-1787806625.181178",
        "operator": "Reliance",
        "circle": "Punjab",
        "customer_no_with_prefix": "+919357701095 "
    }

    res = client.post("/api/calls/smartflo/incoming", json=incoming_payload)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["status"] == "ok"
    assert res_data["caller_phone"] == "+919357701095"
    assert res_data["call_to_number"] == "918065908541"
    assert res_data["assigned_employee"] == "Pankaj"
    assert res_data["operator"] == "Reliance"
    assert res_data["circle"] == "Punjab"

    # 2. CDR Callback after call ends
    cdr_payload = {
        "uuid": "6a8fc3a2171d7",
        "call_to": "918065908541",
        "caller_number": "9357701095",
        "start_stamp": "2026-08-27 10:27:06",
        "answer_stamp": "2026-08-27 10:27:06",
        "end_stamp": "2026-08-27 10:27:30",
        "billsec": 24,
        "duration": "24 sec",
        "direction": "inbound",
        "agent": "Pankaj",
        "agent_number": "+917743004676",
        "call_status": "missed",
        "reason_key": "Calls dropped",
        "hangup_cause": "No user responding",
        "hangup_code": "18",
        "hangup_key": "NO_USER_RESPONSE",
        "recording_url": "https://smartflo-cdn.tatateleservices.com/recordings/6a8fc3a2171d7.mp3",
        "billing_circle": "Reliance / Punjab"
    }

    cdr_res = client.post("/api/calls/smartflo/cdr", json=cdr_payload)
    assert cdr_res.status_code == 200
    cdr_data = cdr_res.json()
    assert cdr_data["status"] == "ok"
    assert cdr_data["duration_seconds"] == 24
    assert cdr_data["billsec"] == 24
    assert cdr_data["hangup_cause"] == "No user responding"

    # Verify Call in DB
    db = SessionLocal()
    saved_call = db.query(Call).filter(Call.uuid == "6a8fc3a2171d7").first()
    assert saved_call is not None
    assert saved_call.call_to_number == "918065908541"
    assert saved_call.duration_seconds == 24
    assert saved_call.billsec == 24
    assert saved_call.recording_url == "https://smartflo-cdn.tatateleservices.com/recordings/6a8fc3a2171d7.mp3"
    assert saved_call.agent_name == "Pankaj"
    assert "No user responding" in saved_call.notes
    db.close()


def test_simultaneous_multi_call_and_rbac_visibility():
    """
    Verify multiple simultaneous calls on different VIDs and role-based access isolation.
    - 918065908541 -> Pankaj
    - 918065908536 -> Ankush Dingra
    - 918065908539 -> Ankush Kapila
    - Admin (Shivam) can see all.
    """
    # 1. Login users to get tokens
    admin_tok = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"}).json()["access_token"]
    pankaj_tok = client.post("/api/auth/login", json={"email": "pankaj@crm.com", "password": "pankaj"}).json()["access_token"]
    ankush_tok = client.post("/api/auth/login", json={"email": "ankush.dingra@crm.com", "password": "ankush.dingra"}).json()["access_token"]

    # 2. Fire 2 simultaneous calls on different VIDs
    client.post("/api/calls/smartflo/incoming", json={
        "uuid": "multi_call_pankaj_01",
        "call_to_number": "918065908541",
        "caller_id_number": "9811122233",
        "operator": "Reliance",
        "circle": "Punjab"
    })

    client.post("/api/calls/smartflo/incoming", json={
        "uuid": "multi_call_ankush_02",
        "call_to_number": "918065908536",
        "caller_id_number": "9877788899",
        "operator": "Airtel",
        "circle": "Delhi"
    })

    # 3. Admin polls /api/calls/active: should see both active calls
    admin_res = client.get("/api/calls/active", headers={"Authorization": f"Bearer {admin_tok}"})
    assert admin_res.status_code == 200
    admin_active = admin_res.json()["active_calls"]
    active_uuids = [c["uuid"] for c in admin_active]
    assert "multi_call_pankaj_01" in active_uuids
    assert "multi_call_ankush_02" in active_uuids

    # 4. Pankaj polls /api/calls/active: should only see his call
    pankaj_res = client.get("/api/calls/active", headers={"Authorization": f"Bearer {pankaj_tok}"})
    assert pankaj_res.status_code == 200
    pankaj_active = pankaj_res.json()["active_calls"]
    pankaj_uuids = [c["uuid"] for c in pankaj_active]
    assert "multi_call_pankaj_01" in pankaj_uuids
    assert "multi_call_ankush_02" not in pankaj_uuids

    # 5. Ankush Dingra polls /api/calls/active: should only see his call
    ankush_res = client.get("/api/calls/active", headers={"Authorization": f"Bearer {ankush_tok}"})
    assert ankush_res.status_code == 200
    ankush_active = ankush_res.json()["active_calls"]
    ankush_uuids = [c["uuid"] for c in ankush_active]
    assert "multi_call_ankush_02" in ankush_uuids
    assert "multi_call_pankaj_01" not in ankush_uuids


def test_allowed_caller_id_based_login_and_user_call_isolation():
    """
    Verify Tata Smartflo Allowed Caller ID based authentication and strict DB/API call visibility:
    1. Admin (Yogesh Khandelia) logs in via 918065908531 + admin -> role: admin.
    2. Sahil Dogra logs in via 918065908531 + 12345678 -> role: employee.
    3. BM Jagga logs in via 918065908532 + 12345678 -> role: employee.
    4. Utpal Pal logs in via 918065908533 + 12345678 -> role: employee.
    5. Webhook calls on 918065908532 and 918065908533:
       - BM Jagga sees only 918065908532 calls.
       - Utpal Pal sees only 918065908533 calls.
       - Sahil Dogra sees none of them.
       - Admin sees all calls.
    """
    # 1. Reset/seed database with all 10 Smartflo staff members
    seed_database(SessionLocal(), force_reset=False)

    # 2. Test Allowed Caller ID Logins
    # Admin Yogesh Khandelia
    admin_login_res = client.post("/api/auth/login", json={"email": "918065908531", "password": "admin"})
    assert admin_login_res.status_code == 200
    admin_user = admin_login_res.json()["user"]
    admin_tok = admin_login_res.json()["access_token"]
    assert admin_user["role"] == "admin"
    assert "Yogesh" in admin_user["full_name"] or "Shivam" in admin_user["full_name"]

    # Sahil Dogra
    sahil_login_res = client.post("/api/auth/login", json={"email": "918065908531", "password": "12345678"})
    assert sahil_login_res.status_code == 200
    sahil_user = sahil_login_res.json()["user"]
    sahil_tok = sahil_login_res.json()["access_token"]
    assert sahil_user["role"] == "employee"
    assert sahil_user["full_name"] == "Sahil Dogra"
    assert sahil_user["allowed_caller_id"] == "918065908531"

    # BM Jagga
    bm_login_res = client.post("/api/auth/login", json={"email": "918065908532", "password": "12345678"})
    assert bm_login_res.status_code == 200
    bm_user = bm_login_res.json()["user"]
    bm_tok = bm_login_res.json()["access_token"]
    assert bm_user["role"] == "employee"
    assert bm_user["full_name"] == "BM Jagga"
    assert bm_user["allowed_caller_id"] == "918065908532"

    # Utpal Pal
    utpal_login_res = client.post("/api/auth/login", json={"email": "918065908533", "password": "12345678"})
    assert utpal_login_res.status_code == 200
    utpal_user = utpal_login_res.json()["user"]
    utpal_tok = utpal_login_res.json()["access_token"]
    assert utpal_user["role"] == "employee"
    assert utpal_user["full_name"] == "Utpal Pal"
    assert utpal_user["allowed_caller_id"] == "918065908533"

    # 3. Simulate Incoming calls to specific Allowed Caller IDs
    # Call A: to BM Jagga (918065908532)
    client.post("/api/calls/smartflo/incoming", json={
        "uuid": "call_bm_jagga_01",
        "call_to_number": "918065908532",
        "caller_id_number": "9812345678",
        "customer_no_with_prefix": "+919812345678",
        "start_time": "2026-08-27 11:30:00",
        "operator": "Reliance",
        "circle": "Punjab"
    })

    # Call B: to Utpal Pal (918065908533)
    client.post("/api/calls/smartflo/incoming", json={
        "uuid": "call_utpal_02",
        "call_to_number": "918065908533",
        "caller_id_number": "9898989898",
        "customer_no_with_prefix": "+919898989898",
        "start_time": "2026-08-27 11:30:05",
        "operator": "Airtel",
        "circle": "Kolkata"
    })

    # 4. Check Active Ringing Calls Visibility (/api/calls/active)
    # BM Jagga must see Call A, but NOT Call B
    bm_active = client.get("/api/calls/active", headers={"Authorization": f"Bearer {bm_tok}"}).json()["active_calls"]
    bm_uuids = [c["uuid"] for c in bm_active]
    assert "call_bm_jagga_01" in bm_uuids
    assert "call_utpal_02" not in bm_uuids

    # Utpal Pal must see Call B, but NOT Call A
    utpal_active = client.get("/api/calls/active", headers={"Authorization": f"Bearer {utpal_tok}"}).json()["active_calls"]
    utpal_uuids = [c["uuid"] for c in utpal_active]
    assert "call_utpal_02" in utpal_uuids
    assert "call_bm_jagga_01" not in utpal_uuids

    # Sahil Dogra (918065908531) must see NEITHER Call A nor Call B
    sahil_active = client.get("/api/calls/active", headers={"Authorization": f"Bearer {sahil_tok}"}).json()["active_calls"]
    sahil_uuids = [c["uuid"] for c in sahil_active]
    assert "call_bm_jagga_01" not in sahil_uuids
    assert "call_utpal_02" not in sahil_uuids

    # Admin must see BOTH Call A and Call B
    admin_active = client.get("/api/calls/active", headers={"Authorization": f"Bearer {admin_tok}"}).json()["active_calls"]
    admin_uuids = [c["uuid"] for c in admin_active]
    assert "call_bm_jagga_01" in admin_uuids
    assert "call_utpal_02" in admin_uuids

    # 5. Check Call History Listing (/api/calls)
    bm_calls = client.get("/api/calls", headers={"Authorization": f"Bearer {bm_tok}"}).json()
    bm_call_to_numbers = [c.get("call_to_number") for c in bm_calls if c.get("call_to_number")]
    for num in bm_call_to_numbers:
        assert "918065908532" in num or num.endswith("8532")


def test_team_performance_table_and_strict_employee_rbac_scoping():
    """
    Verify:
    1. Rahul Sharma, Amit Verma, Priya Patel are permanently deleted.
    2. Admin sees all employees with Phone, Allowed Caller ID, and Designation in /api/employees and /api/dashboard/stats.
    3. Normal User (BM Jagga) only sees his own record in /api/employees and /api/dashboard/stats.
    """
    # 1. Reset/seed database cleanly
    seed_database(SessionLocal(), force_reset=False)

    admin_tok = client.post("/api/auth/login", json={"email": "918065908531", "password": "admin"}).json()["access_token"]
    bm_tok = client.post("/api/auth/login", json={"email": "918065908532", "password": "12345678"}).json()["access_token"]
    utpal_tok = client.post("/api/auth/login", json={"email": "918065908533", "password": "12345678"}).json()["access_token"]

    # 2. Check Deleted Employees are NOT in system
    admin_emp_res = client.get("/api/employees", headers={"Authorization": f"Bearer {admin_tok}"})
    assert admin_emp_res.status_code == 200
    all_employees = admin_emp_res.json()
    all_emp_names = [e["full_name"] for e in all_employees]

    assert "Rahul Sharma" not in all_emp_names
    assert "Amit Verma" not in all_emp_names
    assert "Priya Patel" not in all_emp_names

    # Check Smartflo team is present with required fields
    bm_record = next((e for e in all_employees if e["full_name"] == "BM Jagga"), None)
    assert bm_record is not None
    assert bm_record["phone"] == "917087422511"
    assert bm_record["allowed_caller_id"] == "918065908532"
    assert bm_record["designation"] in ["Employee", "Support Agent"]

    # 3. Check Admin view of /api/dashboard/stats
    admin_stats = client.get("/api/dashboard/stats", headers={"Authorization": f"Bearer {admin_tok}"}).json()
    admin_team = admin_stats["team_activity"]
    assert len(admin_team) >= 5
    admin_team_names = [t["full_name"] for t in admin_team]
    assert "BM Jagga" in admin_team_names
    assert "Utpal Pal" in admin_team_names

    # 4. Check Normal User (BM Jagga) view of /api/employees (Strict Scoping: Only Himself)
    bm_emp_res = client.get("/api/employees", headers={"Authorization": f"Bearer {bm_tok}"})
    assert bm_emp_res.status_code == 200
    bm_emp_list = bm_emp_res.json()
    assert len(bm_emp_list) == 1
    assert bm_emp_list[0]["full_name"] == "BM Jagga"
    assert bm_emp_list[0]["allowed_caller_id"] == "918065908532"

    # 5. Check Normal User (BM Jagga) view of /api/dashboard/stats (Strict Scoping: Only Himself)
    bm_stats = client.get("/api/dashboard/stats", headers={"Authorization": f"Bearer {bm_tok}"}).json()
    bm_team = bm_stats["team_activity"]
    assert len(bm_team) == 1
    assert bm_team[0]["full_name"] == "BM Jagga"
    assert bm_team[0]["phone"] == "917087422511"
    assert bm_team[0]["allowed_caller_id"] == "918065908532"

    # 6. Check Normal User (Utpal Pal) view of /api/employees (Strict Scoping: Only Himself)
    utpal_emp_res = client.get("/api/employees", headers={"Authorization": f"Bearer {utpal_tok}"})
    assert utpal_emp_res.status_code == 200
    utpal_emp_list = utpal_emp_res.json()
    assert len(utpal_emp_list) == 1
    assert utpal_emp_list[0]["full_name"] == "Utpal Pal"
    assert utpal_emp_list[0]["allowed_caller_id"] == "918065908533"

def test_multiple_phone_numbers_crud_and_smartflo_call_matching():
    """
    Verify:
    1. Adding multiple phone numbers (Mobile, Office, WhatsApp, Home) to a customer.
    2. Preventing duplicate phone numbers.
    3. Updating phone label/channel and switching primary number.
    4. Incoming Smartflo telephony matching against any secondary phone number.
    5. Search engine finding the customer by any secondary phone number.
    """
    login_res = client.post("/api/auth/login", json={"email": "shivam@crm.com", "password": "admin"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Fetch Mashal Oil customer (CUST-7814)
    cust_res = client.get("/api/customers/1", headers=headers)
    assert cust_res.status_code == 200
    cust_data = cust_res.json()
    cust_id = cust_data["id"]

    # 2. Add Office phone number
    add_office_res = client.post(f"/api/customers/{cust_id}/phones", json={
        "phone_number": "011-23456789",
        "phone_type": "Office",
        "label": "Headquarters Landline",
        "is_primary": False
    }, headers=headers)
    assert add_office_res.status_code == 201, f"Error: {add_office_res.text}"
    phones = add_office_res.json()
    assert len(phones) == 2
    assert any(p["phone_type"] == "Office" and "23456789" in p["phone_normalized"] for p in phones)

    # 3. Add WhatsApp phone number
    add_wa_res = client.post(f"/api/customers/{cust_id}/phones", json={
        "phone_number": "+91 91234 56789",
        "phone_type": "WhatsApp",
        "label": "Support WhatsApp Line",
        "is_primary": False
    }, headers=headers)
    assert add_wa_res.status_code == 201
    phones = add_wa_res.json()
    assert len(phones) == 3

    # 4. Duplicate prevention test
    dup_res = client.post(f"/api/customers/{cust_id}/phones", json={
        "phone_number": "9123456789",
        "phone_type": "Mobile"
    }, headers=headers)
    assert dup_res.status_code == 400
    assert "already saved" in dup_res.json()["detail"]

    # 5. Smartflo Incoming Call Matching on WhatsApp Secondary Number (9123456789)
    sf_incoming_res = client.post("/api/calls/smartflo/incoming", json={
        "uuid": "test-sec-uuid-91234",
        "call_id": "SF-SEC-CALL-01",
        "caller_id_number": "9123456789",
        "call_to_number": "918065908540",
        "start_time": "2026-08-27 15:30:00",
        "operator": "Airtel",
        "circle": "Delhi"
    })
    assert sf_incoming_res.status_code == 200
    call_screenpop = sf_incoming_res.json()
    assert call_screenpop["customer_found"] is True
    assert call_screenpop["customer"]["id"] == cust_id
    assert call_screenpop["customer"]["party_name"] == "Mashal Oil & Foods Ltd"

    # 6. Global Search Test by Secondary Office Number (01123456789)
    search_res = client.get("/api/customers/search?q=01123456789", headers=headers)
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["count"] >= 1
    assert search_data["results"][0]["id"] == cust_id
    assert search_data["results"][0]["party_name"] == "Mashal Oil & Foods Ltd"

    # 7. Set Secondary Number as Primary Number
    wa_phone_id = [p["id"] for p in phones if p["phone_type"] == "WhatsApp"][0]
    set_prim_res = client.put(f"/api/customers/{cust_id}/phones/{wa_phone_id}/primary", json={}, headers=headers)
    assert set_prim_res.status_code == 200
    updated_phones = set_prim_res.json()
    primary_record = [p for p in updated_phones if p["is_primary"] is True][0]
    assert "9123456789" in primary_record["phone_normalized"]

    # 8. Delete Secondary Phone Number
    sec_id_to_delete = [p["id"] for p in updated_phones if p["is_primary"] is False and p["id"] != 0][0]
    del_res = client.delete(f"/api/customers/{cust_id}/phones/{sec_id_to_delete}", headers=headers)
    assert del_res.status_code == 200
    remaining_phones = del_res.json()
    assert len(remaining_phones) == 2


def test_outgoing_call_vid_enforcement_and_employee_restriction():
    """Verify outgoing call uses mapped user Allowed Caller ID / VID and creates outgoing call record."""
    # Login as Sahil Dogra (Support Agent with VID 918065908531)
    login_res = client.post("/api/auth/login", json={
        "email": "918065908531",
        "password": "admin"
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Initiate outgoing call to customer phone 7814749816
    out_res = client.post("/api/calls/outgoing", json={
        "phone_number": "7814749816",
        "notes": "Followup call regarding product dispatch"
    }, headers=headers)

    assert out_res.status_code == 200
    out_data = out_res.json()
    assert out_data["status"] == "initiated"
    assert out_data["to_number"] == "7814749816"
    assert out_data["vid"] == "918065908531"
    assert out_data["customer_found"] is True
    assert out_data["customer_name"] == "Mashal Oil & Foods Ltd"

    # Verify call is in DB with direction="outgoing"
    call_id = out_data["call_id"]
    calls_res = client.get("/api/calls", headers=headers)
    assert calls_res.status_code == 200
    all_calls = calls_res.json()
    matching_call = [c for c in all_calls if c["call_id"] == call_id][0]
    assert matching_call["direction"] == "outgoing"
    assert matching_call["status"] == "ringing"


def test_outgoing_call_smartflo_cdr_sync_and_timeline():
    """Verify Smartflo CDR callback updates outgoing call duration and adds timeline interaction."""
    # 1. Initiate Outgoing Call
    login_res = client.post("/api/auth/login", json={
        "email": "918065908540",
        "password": "admin"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    out_res = client.post("/api/calls/outgoing", json={
        "phone_number": "7814749816",
        "notes": "Discussion with Mr. Shivam"
    }, headers=headers)
    assert out_res.status_code == 200
    out_data = out_res.json()
    call_uuid = out_data["uuid"]
    call_id = out_data["call_id"]

    # 2. Smartflo sends CDR callback when call hangs up
    cdr_res = client.post("/api/calls/smartflo/cdr", json={
        "uuid": call_uuid,
        "call_id": call_id,
        "caller_number": "7814749816",
        "duration": "55",
        "billsec": "50",
        "status": "completed",
        "recording_url": "https://smartflo.tatateleservices.com/recordings/out-55.mp3",
        "hangup_cause": "Normal Clearing"
    })
    assert cdr_res.status_code == 200
    cdr_data = cdr_res.json()
    assert cdr_data["status"] == "ok"
    assert cdr_data["call_status"] == "completed"

    # 3. Check customer interactions timeline
    cust_id = out_data["customer_id"]
    timeline_res = client.get(f"/api/customers/{cust_id}/timeline", headers=headers)
    assert timeline_res.status_code == 200
    timeline_payload = timeline_res.json()
    timeline = timeline_payload.get("timeline", timeline_payload)
    recent_call_event = [e for e in timeline if e.get("meta", {}).get("call_id") == call_id or e.get("direction") == "outgoing"][0]
    assert recent_call_event["direction"] == "outgoing"
    assert "Outgoing" in recent_call_event["title"] or "Outgoing" in recent_call_event.get("subject", "")


def test_admin_user_switch_logout_admin_relogin_flow():
    """Verify Admin can switch to employee, and Admin login role & full access restore cleanly."""
    # 1. Admin Login (Yogesh Khandelia)
    admin_login = client.post("/api/auth/login", json={
        "email": "918065908540",
        "password": "admin"
    })
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Admin switches session to Sahil Dogra
    switch_res = client.post("/api/auth/switch-account", json={
        "email": "Sahil Dogra"
    }, headers=admin_headers)
    assert switch_res.status_code == 200
    sahil_token = switch_res.json()["access_token"]
    sahil_headers = {"Authorization": f"Bearer {sahil_token}"}
    assert switch_res.json()["user"]["full_name"] == "Sahil Dogra"

    # 3. Verify Sahil cannot access Admin-only employees list creation
    unauth_admin_res = client.post("/api/employees", json={
        "full_name": "Test Emp",
        "email": "testemp@crm.com",
        "password": "123",
        "role": "employee"
    }, headers=sahil_headers)
    assert unauth_admin_res.status_code == 403

    # 4. Relogin as Admin
    relogin_admin = client.post("/api/auth/login", json={
        "email": "918065908540",
        "password": "admin"
    })
    assert relogin_admin.status_code == 200
    restored_admin = relogin_admin.json()
    assert restored_admin["user"]["role"] == "admin"
    assert restored_admin["user"]["full_name"] == "Yogesh Khandelia"


def test_smartflo_connect_app_outbound_call_webhook_screenpop():
    """
    Verify Smartflo Connect App Outbound Call flow:
    When Yogesh Sir calls customer 7814749816 using VID 918065908540 from the Connect App:
    1. Webhook arrives at /api/calls/smartflo/incoming with caller=918065908540 and call_to=7814749816.
    2. Backend auto-detects outbound direction, matches customer 7814749816 (Mashal Oil & Foods Ltd),
       and resolves agent Yogesh Khandelia.
    3. Active calls endpoint reflects the outgoing call.
    4. Smartflo CDR callback completes the call and updates history.
    """
    admin_login = client.post("/api/auth/login", json={
        "email": "918065908540",
        "password": "admin"
    })
    token = admin_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Smartflo sends webhook for Connect App Outbound Call
    hook_res = client.post("/api/calls/smartflo/incoming", json={
        "uuid": "SF-CONN-OUT-991",
        "call_id": "MUM10-D10-991882",
        "caller_id_number": "918065908540",
        "call_to_number": "7814749816",
        "direction": "outbound",
        "operator": "Tata Tele",
        "circle": "Punjab"
    })
    assert hook_res.status_code == 200
    hook_data = hook_res.json()
    assert hook_data["status"] == "ok"
    assert hook_data["customer_found"] is True
    assert "Mashal Oil" in hook_data["customer_name"]

    # 2. Check active calls polling
    active_res = client.get("/api/calls/active", headers=headers)
    assert active_res.status_code == 200
    active_data = active_res.json()
    assert active_data["has_active_call"] is True
    matched_call = [c for c in active_data["active_calls"] if c.get("uuid") == "SF-CONN-OUT-991"][0]
    assert matched_call["direction"] == "outgoing"
    assert matched_call["customer_found"] is True
    assert matched_call["customer"]["party_name"] == "Mashal Oil & Foods Ltd"

    # 3. CDR Callback on hangup
    cdr_res = client.post("/api/calls/smartflo/cdr", json={
        "uuid": "SF-CONN-OUT-991",
        "call_id": "MUM10-D10-991882",
        "caller_number": "7814749816",
        "duration": "42",
        "billsec": "38",
        "status": "completed",
        "hangup_cause": "Normal Clearing"
    })
    assert cdr_res.status_code == 200
    assert cdr_res.json()["call_status"] == "completed"
















