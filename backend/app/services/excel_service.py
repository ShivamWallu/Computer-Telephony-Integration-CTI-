import io
import csv
import openpyxl
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session
from backend.app.models.customer import Customer, CustomerPhoneNumber
from backend.app.models.user import User
from backend.app.models.import_job import ImportJob, ImportError, ImportUpdate
from backend.app.services.phone_normalizer import PhoneNormalizer
import re
import logging

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")

# Exact 25 Standard Columns in Exact Sequence
STRICT_COLUMNS = [
    "Address Code*",
    "Address Description*",
    "Address Date(DD/MM/YYYY)*",
    "Address Line 1*",
    "Address Line 2*",
    "Address Line 3",
    "Country*",
    "State*",
    "State",
    "City*",
    "City",
    "Pincode*",
    "District",
    "Zone",
    "Company Website",
    "Sales Region Code",
    "Contact Person 1",
    "Email-Id 1",
    "Phone Number 1",
    "Contact Person 2",
    "Email-Id 2",
    "Phone Number 2",
    "Contact Person 3",
    "Email-Id 3",
    "Phone Number 3"
]

# Legacy 15 column support for backward compatibility
LEGACY_15_COLUMNS = [
    "Party Code", "Party Name", "Address Date", "Address Line 1", "Address Line 2",
    "Address Line 3", "Contact Person 1", "Email Id 1", "Country", "State",
    "City", "Pincode", "Phone Type 1", "Phone 1", "Status"
]

BUSINESS_CATEGORIES = ["By Product", "HUSK", "SAS", "MRO", "MCK", "DOC", "MSD", "MOL", "MOMT", "General"]

class ExcelService:
    @staticmethod
    def normalize_col_header(h: str) -> str:
        """Normalize header name for fuzzy matching."""
        return re.sub(r"[^a-zA-Z0-9]", "", str(h or "").lower())

    @classmethod
    def validate_headers(cls, headers: List[str]) -> Tuple[bool, Optional[str]]:
        """
        Validate uploaded file headers.
        Checks for the 25-column standard format or the legacy 15-column format.
        Strict requirement: 'Address Code*' (or 'Party Code') must be present.
        """
        cleaned_headers = [str(h).strip() if h is not None else "" for h in headers]
        while cleaned_headers and cleaned_headers[-1] == "":
            cleaned_headers.pop()

        if not cleaned_headers:
            return False, "Uploaded file is empty or has no header row."

        # Check if Address Code or Party Code exists
        norm_headers = [cls.normalize_col_header(h) for h in cleaned_headers]
        has_address_code = any(
            h in ("addresscode", "partycode", "customercode", "code", "partyid")
            for h in norm_headers
        )

        if not has_address_code:
            return False, "Missing mandatory column: 'Address Code*' (or 'Party Code') was not found in the header row."

        return True, None

    @classmethod
    def read_file_rows(cls, file_bytes: bytes, filename: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        """Read .xlsx or .csv into header list and raw rows."""
        headers = []
        rows = []

        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            sheet = wb.active
            iter_rows = list(sheet.iter_rows(values_only=True))
            if not iter_rows:
                return [], []
            
            # Find first non-empty header row
            header_row_idx = 0
            for i, row in enumerate(iter_rows):
                if any(row):
                    header_row_idx = i
                    headers = [str(c).strip() if c is not None else "" for c in row]
                    while headers and headers[-1] == "":
                        headers.pop()
                    break
            
            for row in iter_rows[header_row_idx + 1:]:
                if any(row):
                    row_dict = {}
                    for idx, h in enumerate(headers):
                        val = row[idx] if idx < len(row) else ""
                        row_dict[h] = str(val).strip() if val is not None else ""
                    rows.append(row_dict)

        elif filename.endswith(".csv"):
            decoded_content = file_bytes.decode("utf-8", errors="replace")
            reader = csv.reader(io.StringIO(decoded_content))
            raw_lines = [r for r in reader if any(r)]
            if not raw_lines:
                return [], []
            
            headers = [h.strip() for h in raw_lines[0]]
            while headers and headers[-1] == "":
                headers.pop()

            for line in raw_lines[1:]:
                if any(line):
                    row_dict = {}
                    for idx, h in enumerate(headers):
                        val = line[idx] if idx < len(line) else ""
                        row_dict[h] = val.strip()
                    rows.append(row_dict)
        else:
            raise ValueError("Unsupported file format. Please upload an Excel (.xlsx) or CSV (.csv) file.")

        return headers, rows

    @classmethod
    def preview_import(cls, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """Preview file headers, validate mandatory Address Code, and return sample rows."""
        headers, rows = cls.read_file_rows(file_bytes, filename)
        is_valid, validation_error = cls.validate_headers(headers)
        
        if not is_valid:
            raise ValueError(validation_error)

        return {
            "filename": filename,
            "total_detected_rows": len(rows),
            "headers": headers,
            "expected_columns": STRICT_COLUMNS,
            "is_valid": True,
            "sample_rows": rows[:5]
        }

    @classmethod
    def process_import(
        cls,
        db: Session,
        file_bytes: bytes,
        filename: str,
        import_mode: str = "update",  # "update", "skip"
        user_id: Optional[int] = None,
        target_category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        High-performance 25-column schema import with O(1) hash indexing,
        non-blocking batch processing, deduplication, and 3-phone support.
        Only 'Address Code*' is strictly mandatory.
        """
        headers, rows = cls.read_file_rows(file_bytes, filename)
        is_valid, validation_error = cls.validate_headers(headers)
        if not is_valid:
            raise ValueError(validation_error)

        # Build fuzzy column index mapping from headers
        # Handles duplicate columns like 'State' / 'State*' or 'City' / 'City*'
        header_map: Dict[str, List[str]] = {}
        for h in headers:
            norm = cls.normalize_col_header(h)
            if norm not in header_map:
                header_map[norm] = []
            header_map[norm].append(h)

        def get_col_val(row: Dict[str, Any], aliases: List[str], instance_idx: int = 0) -> str:
            for alias in aliases:
                norm = cls.normalize_col_header(alias)
                if norm in header_map:
                    matching_headers = header_map[norm]
                    if instance_idx < len(matching_headers):
                        h_name = matching_headers[instance_idx]
                        val = str(row.get(h_name, "")).strip()
                        if val:
                            return val
                    elif matching_headers:
                        val = str(row.get(matching_headers[0], "")).strip()
                        if val:
                            return val
            return ""

        # Create Import Job Record
        import_job = ImportJob(
            filename=filename,
            uploaded_by_user_id=user_id,
            total_rows=len(rows),
            status="processing"
        )
        db.add(import_job)
        db.flush()

        # Performance Optimization: Preload existing customer index into memory
        existing_customers = db.query(Customer).all()
        by_party_code: Dict[str, Customer] = {c.party_code.strip().upper(): c for c in existing_customers if c.party_code}

        imported_count = 0
        updated_count = 0
        duplicate_count = 0
        error_count = 0
        error_records = []
        duplicate_records = []

        BATCH_SIZE = 500

        for idx, row in enumerate(rows, start=2):
            try:
                # 1. Address Code* (Mandatory)
                raw_address_code = get_col_val(row, ["Address Code*", "Address Code", "Party Code", "Code", "Customer Code"])
                if not raw_address_code:
                    raise ValueError("Missing mandatory field: 'Address Code*' cannot be blank.")

                # 2. Address Description*
                raw_desc = get_col_val(row, ["Address Description*", "Address Description", "Party Name", "Name", "Company Name"])
                if not raw_desc:
                    raw_desc = f"Party {raw_address_code}"

                # 3. Address Date
                raw_address_date = get_col_val(row, ["Address Date(DD/MM/YYYY)*", "Address Date", "Date"])

                # 4-6. Address Lines
                raw_addr1 = get_col_val(row, ["Address Line 1*", "Address Line 1", "Address 1", "Address"])
                raw_addr2 = get_col_val(row, ["Address Line 2*", "Address Line 2", "Address 2"])
                raw_addr3 = get_col_val(row, ["Address Line 3", "Address 3"])

                # 7-11. Country, State, City
                raw_country = get_col_val(row, ["Country*", "Country"]) or "India"
                raw_state1 = get_col_val(row, ["State*"], 0)
                raw_state2 = get_col_val(row, ["State"], 1) or get_col_val(row, ["State"], 0)
                raw_state = raw_state1 or raw_state2

                raw_city1 = get_col_val(row, ["City*"], 0)
                raw_city2 = get_col_val(row, ["City"], 1) or get_col_val(row, ["City"], 0)
                raw_city = raw_city1 or raw_city2

                # 12-16. Pincode, District, Zone, Website, Sales Region
                raw_pincode = get_col_val(row, ["Pincode*", "Pincode", "Pin Code", "Postal Code"])
                raw_district = get_col_val(row, ["District"])
                raw_zone = get_col_val(row, ["Zone"])
                raw_website = get_col_val(row, ["Company Website", "Website"])
                raw_sales_region = get_col_val(row, ["Sales Region Code", "Region Code", "Sales Region"])

                # 17-19. Contact 1, Email 1, Phone 1
                raw_contact1 = get_col_val(row, ["Contact Person 1", "Contact Person", "Contact 1"])
                raw_email1 = get_col_val(row, ["Email-Id 1", "Email Id 1", "Email 1", "Email"])
                raw_phone1 = get_col_val(row, ["Phone Number 1", "Phone 1", "Mobile 1", "Phone", "Mobile"])

                # 20-22. Contact 2, Email 2, Phone 2
                raw_contact2 = get_col_val(row, ["Contact Person 2", "Contact 2"])
                raw_email2 = get_col_val(row, ["Email-Id 2", "Email Id 2", "Email 2"])
                raw_phone2 = get_col_val(row, ["Phone Number 2", "Phone 2", "Mobile 2"])

                # 23-25. Contact 3, Email 3, Phone 3
                raw_contact3 = get_col_val(row, ["Contact Person 3", "Contact 3"])
                raw_email3 = get_col_val(row, ["Email-Id 3", "Email Id 3", "Email 3"])
                raw_phone3 = get_col_val(row, ["Phone Number 3", "Phone 3", "Mobile 3"])

                # Also detect Category if present in row or default / target_category
                if target_category and target_category.strip() and target_category.strip().lower() not in ("auto", "all", ""):
                    raw_category = target_category.strip()
                else:
                    raw_category = get_col_val(row, ["Category", "Business Category"])
                    if not raw_category:
                        desc_upper = (raw_desc + " " + raw_address_code).upper()
                        found_cat = next((cat for cat in BUSINESS_CATEGORIES if cat in desc_upper), None)
                        raw_category = found_cat if found_cat else "General"

                # Normalize Phone 1
                phone_1_norm = None
                if raw_phone1:
                    phone_1_norm = PhoneNormalizer.normalize(raw_phone1)
                    if not phone_1_norm:
                        clean_digits = PhoneNormalizer.clean_digits(raw_phone1)
                        if len(clean_digits) >= 10:
                            phone_1_norm = f"+91{clean_digits[-10:]}"
                if not phone_1_norm:
                    phone_1_norm = "0000000000"

                code_key = raw_address_code.strip().upper()

                # Unique Entity Identifier: Match strictly by Address Code* (Party Code)
                if code_key in by_party_code:
                    existing_customer = by_party_code[code_key]
                else:
                    existing_customer = None

                if existing_customer:
                    prev_diff = {}
                    new_diff = {}
                    changed_cols = []

                    def track_change(col_title: str, field_attr: str, new_val: Any):
                        curr_val = getattr(existing_customer, field_attr, None)
                        curr_str = str(curr_val or "").strip()
                        new_str = str(new_val or "").strip()
                        if new_str and new_str != curr_str:
                            prev_diff[col_title] = curr_val if curr_val is not None else ""
                            new_diff[col_title] = new_val
                            changed_cols.append(col_title)

                    track_change("Address Code", "party_code", raw_address_code)
                    track_change("Address Description", "party_name", raw_desc)
                    track_change("Address Date", "address_date", raw_address_date)
                    track_change("Address Line 1", "address_line_1", raw_addr1)
                    track_change("Address Line 2", "address_line_2", raw_addr2)
                    track_change("Address Line 3", "address_line_3", raw_addr3)
                    track_change("Country", "country", raw_country)
                    track_change("State", "state", raw_state)
                    track_change("City", "city", raw_city)
                    track_change("Pincode", "pincode", raw_pincode)
                    track_change("District", "district", raw_district)
                    track_change("Zone", "zone", raw_zone)
                    track_change("Company Website", "company_website", raw_website)
                    track_change("Sales Region Code", "sales_region_code", raw_sales_region)
                    track_change("Contact Person 1", "contact_person_1", raw_contact1)
                    track_change("Email-Id 1", "email_id_1", raw_email1)
                    track_change("Phone Number 1", "phone_1", raw_phone1)
                    track_change("Contact Person 2", "contact_person_2", raw_contact2)
                    track_change("Email-Id 2", "email_id_2", raw_email2)
                    track_change("Contact Person 3", "contact_person_3", raw_contact3)
                    track_change("Email-Id 3", "email_id_3", raw_email3)
                    if raw_category and raw_category != "General":
                        track_change("Category", "category", raw_category)

                    # Check secondary phones
                    phone_changed = cls._sync_customer_secondary_phones(db, existing_customer.id, raw_phone2, raw_phone3, existing_customer.phone_1_normalized)
                    if phone_changed:
                        changed_cols.append("Secondary Phones")

                    # If ALL column data is exact 100% identical:
                    if not changed_cols:
                        duplicate_count += 1
                        duplicate_records.append({
                            "row_number": idx,
                            "address_code": raw_address_code,
                            "customer_name": raw_desc,
                            "party_name": raw_desc,
                            "phone": raw_phone1 or "—",
                            "status": "This data already exists",
                            "message": "This data already exists"
                        })
                    else:
                        # Any column is different or has new data: Update / enrich record
                        existing_customer.party_code = raw_address_code or existing_customer.party_code
                        existing_customer.party_name = raw_desc or existing_customer.party_name
                        existing_customer.address_date = raw_address_date or existing_customer.address_date
                        existing_customer.address_line_1 = raw_addr1 or existing_customer.address_line_1
                        existing_customer.address_line_2 = raw_addr2 or existing_customer.address_line_2
                        existing_customer.address_line_3 = raw_addr3 or existing_customer.address_line_3
                        existing_customer.country = raw_country or existing_customer.country
                        existing_customer.state = raw_state or existing_customer.state
                        existing_customer.city = raw_city or existing_customer.city
                        existing_customer.pincode = raw_pincode or existing_customer.pincode
                        existing_customer.district = raw_district or existing_customer.district
                        existing_customer.zone = raw_zone or existing_customer.zone
                        existing_customer.company_website = raw_website or existing_customer.company_website
                        existing_customer.sales_region_code = raw_sales_region or existing_customer.sales_region_code
                        existing_customer.contact_person_1 = raw_contact1 or existing_customer.contact_person_1
                        existing_customer.email_id_1 = raw_email1 or existing_customer.email_id_1
                        if raw_phone1:
                            existing_customer.phone_1 = raw_phone1
                            existing_customer.phone_1_normalized = phone_1_norm
                        existing_customer.contact_person_2 = raw_contact2 or existing_customer.contact_person_2
                        existing_customer.email_id_2 = raw_email2 or existing_customer.email_id_2
                        existing_customer.contact_person_3 = raw_contact3 or existing_customer.contact_person_3
                        existing_customer.email_id_3 = raw_email3 or existing_customer.email_id_3
                        if raw_category and raw_category != "General":
                            existing_customer.category = raw_category

                        update_log = ImportUpdate(
                            import_job_id=import_job.id,
                            row_number=idx,
                            party_code=raw_address_code,
                            party_name=raw_desc,
                            previous_data=prev_diff,
                            new_data=new_diff,
                            changed_fields=changed_cols
                        )
                        db.add(update_log)

                        by_party_code[code_key] = existing_customer
                        updated_count += 1
                else:
                    new_cust = Customer(
                        party_code=raw_address_code,
                        party_name=raw_desc,
                        address_date=raw_address_date or None,
                        address_line_1=raw_addr1 or None,
                        address_line_2=raw_addr2 or None,
                        address_line_3=raw_addr3 or None,
                        country=raw_country,
                        state=raw_state or None,
                        city=raw_city or None,
                        pincode=raw_pincode or None,
                        district=raw_district or None,
                        zone=raw_zone or None,
                        company_website=raw_website or None,
                        sales_region_code=raw_sales_region or None,
                        contact_person_1=raw_contact1 or None,
                        email_id_1=raw_email1 or None,
                        phone_type_1="Mobile",
                        phone_1=raw_phone1 or "—",
                        phone_1_normalized=phone_1_norm,
                        contact_person_2=raw_contact2 or None,
                        email_id_2=raw_email2 or None,
                        contact_person_3=raw_contact3 or None,
                        email_id_3=raw_email3 or None,
                        status="Active",
                        category=raw_category,
                        is_archived=False
                    )
                    db.add(new_cust)
                    db.flush()

                    # Add Phone 2 & Phone 3
                    cls._sync_customer_secondary_phones(db, new_cust.id, raw_phone2, raw_phone3, new_cust.phone_1_normalized)

                    by_party_code[code_key] = new_cust
                    imported_count += 1

                if (imported_count + updated_count) % BATCH_SIZE == 0:
                    db.flush()

            except Exception as e:
                error_count += 1
                err_msg = str(e)
                err_record = ImportError(
                    import_job_id=import_job.id,
                    row_number=idx,
                    raw_data=row,
                    error_reason=err_msg
                )
                db.add(err_record)
                error_records.append({
                    "row_number": idx,
                    "customer_name": row.get("Address Description*", row.get("Address Description", "N/A")),
                    "address_code": row.get("Address Code*", row.get("Address Code", "N/A")),
                    "error": err_msg
                })

        import_job.imported_count = imported_count
        import_job.updated_count = updated_count
        import_job.duplicate_count = duplicate_count
        import_job.error_count = error_count
        import_job.status = "completed"

        db.commit()

        return {
            "job_id": import_job.id,
            "filename": filename,
            "total_rows": len(rows),
            "imported_count": imported_count,
            "updated_count": updated_count,
            "duplicate_count": duplicate_count,
            "duplicate_records": duplicate_records,
            "error_count": error_count,
            "errors": error_records,
            "status": "completed",
            "created_at": import_job.created_at
        }

    @staticmethod
    def _sync_customer_secondary_phones(db: Session, customer_id: int, phone2_raw: str, phone3_raw: str, primary_norm: str) -> bool:
        """Helper to sync phone 2 and phone 3 into CustomerPhoneNumber table. Returns True if any new phone was attached."""
        changed = False
        if phone2_raw and phone2_raw.strip() and phone2_raw.strip() != "—":
            p2_norm = PhoneNormalizer.normalize(phone2_raw)
            if p2_norm and p2_norm != primary_norm:
                existing = db.query(CustomerPhoneNumber).filter(
                    CustomerPhoneNumber.customer_id == customer_id,
                    CustomerPhoneNumber.phone_normalized == p2_norm
                ).first()
                if not existing:
                    db.add(CustomerPhoneNumber(
                        customer_id=customer_id,
                        phone_number=phone2_raw.strip(),
                        phone_normalized=p2_norm,
                        phone_type="Secondary Mobile",
                        label="Phone 2",
                        is_primary=False
                    ))
                    changed = True

        if phone3_raw and phone3_raw.strip() and phone3_raw.strip() != "—":
            p3_norm = PhoneNormalizer.normalize(phone3_raw)
            if p3_norm and p3_norm != primary_norm:
                existing = db.query(CustomerPhoneNumber).filter(
                    CustomerPhoneNumber.customer_id == customer_id,
                    CustomerPhoneNumber.phone_normalized == p3_norm
                ).first()
                if not existing:
                    db.add(CustomerPhoneNumber(
                        customer_id=customer_id,
                        phone_number=phone3_raw.strip(),
                        phone_normalized=p3_norm,
                        phone_type="Office / Alternate",
                        label="Phone 3",
                        is_primary=False
                    ))
                    changed = True

        return changed

    @classmethod
    def generate_sample_excel_bytes(cls) -> bytes:
        """Generate official 25-column sample Excel (.xlsx) file bytes with sample records across all 8 business categories."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Customers"
        ws.append(STRICT_COLUMNS)

        sample_rows = [
            ["PROD-001", "By Product Agro Feed Solutions", "23/08/2026", "Industrial Hub 10", "National Highway 1", "Near Grain Market", "India", "Punjab", "Punjab", "Khanna", "Khanna", "141401", "Ludhiana", "North", "www.byproductagro.com", "REG-PB00", "Simranjit Singh", "simran@byproductagro.com", "+91 98880 11223", "Baljit Singh", "baljit@byproductagro.com", "+91 98880 11224", "Head Office", "info@byproductagro.com", "01628-223344"],
            ["HUSK-1001", "Agro Rice Mills Husk Division", "24/08/2026", "Plot 12, Focal Point Phase 2", "G.T. Road", "Near Toll Plaza", "India", "Punjab", "Punjab", "Ludhiana", "Ludhiana", "141010", "Ludhiana", "North", "www.agroricemills.com", "REG-PB01", "Gurpreet Singh", "gurpreet@agrorice.com", "+91 98765 43210", "Harjot Singh", "harjot@agrorice.com", "+91 98765 43211", "Office Helpdesk", "info@agrorice.com", "0161-2554400"],
            ["SAS-2002", "SAS Automation & Power Corp", "25/08/2026", "Building 4, Cyber Valley", "Sector 62", "Tech Hub", "India", "Uttar Pradesh", "Uttar Pradesh", "Noida", "Noida", "201309", "Gautam Buddha Nagar", "North", "www.sasautomation.in", "REG-UP02", "Vikram Malhotra", "vikram@sasautomation.in", "+91 98112 33445", "Amit Saxena", "amit@sasautomation.in", "+91 98112 33446", "Desk Reception", "desk@sasautomation.in", "0120-4455667"],
            ["MRO-3003", "Apex MRO Industrial Supplies", "26/08/2026", "Shed 88, Peenya Industrial Area", "Phase 3, 2nd Cross", "Opposite Substation", "India", "Karnataka", "Karnataka", "Bengaluru", "Bengaluru", "560058", "Bengaluru Urban", "South", "www.apexmro.com", "REG-KA01", "Suresh Nair", "suresh@apexmro.com", "+91 97420 11223", "Deepak Rao", "deepak@apexmro.com", "+91 97420 11224", "Branch Line", "support@apexmro.com", "080-28394455"],
            ["MCK-4004", "MCK Precision Machinery Ltd", "27/08/2026", "Survey 45/2, Bhosari MIDC", "Telco Road", "Behind Tata Motors", "India", "Maharashtra", "Maharashtra", "Pune", "Pune", "411026", "Pune", "West", "www.mckmachinery.com", "REG-MH03", "Rahul Deshmukh", "rahul@mckmachinery.com", "+91 98230 55667", "Nitin Kulkarni", "nitin@mckmachinery.com", "+91 98230 55668", "Sales Office", "sales@mckmachinery.com", "020-27123344"],
            ["DOC-5005", "DocuMatrix Global Logistics", "28/08/2026", "Container Terminal Road", "Willingdon Island", "Near Port Gate 2", "India", "Kerala", "Kerala", "Kochi", "Kochi", "682003", "Ernakulam", "South", "www.documatrix.com", "REG-KL01", "George Varghese", "george@documatrix.com", "+91 94470 99887", "Manoj Kumar", "manoj@documatrix.com", "+91 94470 99888", "Customer Care", "care@documatrix.com", "0484-2667788"],
            ["MSD-6006", "MSD Steels & Fasteners", "29/08/2026", "Plot 104, Transport Nagar", "Industrial Estate", "Ring Road Bypass", "India", "Rajasthan", "Rajasthan", "Jaipur", "Jaipur", "302013", "Jaipur", "North-West", "www.msdsteels.com", "REG-RJ01", "Mahesh Sharma", "mahesh@msdsteels.com", "+91 94140 77665", "Pooja Sharma", "pooja@msdsteels.com", "+91 94140 77666", "Accounts Desk", "accounts@msdsteels.com", "0141-2334455"],
            ["MOL-7007", "Mashal Oil & Agro Extracts", "30/08/2026", "Plot No. 12, Industrial Area", "Phase 2, Focal Point", "Near Metro Depot", "India", "Punjab", "Punjab", "Ludhiana", "Ludhiana", "141001", "Ludhiana", "North", "www.mashaloil.com", "REG-PB02", "Shivam", "shivam@mashaloil.com", "+91 78147 49816", "Raman Singla", "raman@mashaloil.com", "+91 78147 49817", "Main Plant Line", "contact@mashaloil.com", "0161-4556677"],
            ["MOMT-8008", "MOMT Heavy Tools & Dies", "31/08/2026", "Sector 25, HSIIDC Industrial Estate", "Ballabgarh", "Mathura Road", "India", "Haryana", "Haryana", "Faridabad", "Faridabad", "121004", "Faridabad", "North", "www.momttools.com", "REG-HR01", "Anil Chauhan", "anil@momttools.com", "+91 98100 22334", "Rajesh Verma", "rajesh@momttools.com", "+91 98100 22335", "Board Line", "info@momttools.com", "0129-2233445"],
            ["GEN-9009", "General Allied Trading Enterprises", "01/09/2026", "Commercial Complex 8", "Connaught Place", "Barakhamba Road", "India", "Delhi", "Delhi", "New Delhi", "New Delhi", "110001", "Central Delhi", "North", "www.generalallied.com", "REG-DL01", "Karan Kapoor", "karan@generalallied.com", "+91 98101 55667", "Rohan Mehra", "rohan@generalallied.com", "+91 98101 55668", "Customer Help", "help@generalallied.com", "011-23344556"]
        ]

        for r in sample_rows:
            ws.append(r)

        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()

    @classmethod
    def generate_sample_csv_bytes(cls) -> bytes:
        """Generate official 25-column sample CSV file bytes with UTF-8 BOM."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(STRICT_COLUMNS)

        sample_rows = [
            ["PROD-001", "By Product Agro Feed Solutions", "23/08/2026", "Industrial Hub 10", "National Highway 1", "Near Grain Market", "India", "Punjab", "Punjab", "Khanna", "Khanna", "141401", "Ludhiana", "North", "www.byproductagro.com", "REG-PB00", "Simranjit Singh", "simran@byproductagro.com", "+91 98880 11223", "Baljit Singh", "baljit@byproductagro.com", "+91 98880 11224", "Head Office", "info@byproductagro.com", "01628-223344"],
            ["HUSK-1001", "Agro Rice Mills Husk Division", "24/08/2026", "Plot 12, Focal Point Phase 2", "G.T. Road", "Near Toll Plaza", "India", "Punjab", "Punjab", "Ludhiana", "Ludhiana", "141010", "Ludhiana", "North", "www.agroricemills.com", "REG-PB01", "Gurpreet Singh", "gurpreet@agrorice.com", "+91 98765 43210", "Harjot Singh", "harjot@agrorice.com", "+91 98765 43211", "Office Helpdesk", "info@agrorice.com", "0161-2554400"],
            ["SAS-2002", "SAS Automation & Power Corp", "25/08/2026", "Building 4, Cyber Valley", "Sector 62", "Tech Hub", "India", "Uttar Pradesh", "Uttar Pradesh", "Noida", "Noida", "201309", "Gautam Buddha Nagar", "North", "www.sasautomation.in", "REG-UP02", "Vikram Malhotra", "vikram@sasautomation.in", "+91 98112 33445", "Amit Saxena", "amit@sasautomation.in", "+91 98112 33446", "Desk Reception", "desk@sasautomation.in", "0120-4455667"],
            ["MRO-3003", "Apex MRO Industrial Supplies", "26/08/2026", "Shed 88, Peenya Industrial Area", "Phase 3, 2nd Cross", "Opposite Substation", "India", "Karnataka", "Karnataka", "Bengaluru", "Bengaluru", "560058", "Bengaluru Urban", "South", "www.apexmro.com", "REG-KA01", "Suresh Nair", "suresh@apexmro.com", "+91 97420 11223", "Deepak Rao", "deepak@apexmro.com", "+91 97420 11224", "Branch Line", "support@apexmro.com", "080-28394455"],
            ["MCK-4004", "MCK Precision Machinery Ltd", "27/08/2026", "Survey 45/2, Bhosari MIDC", "Telco Road", "Behind Tata Motors", "India", "Maharashtra", "Maharashtra", "Pune", "Pune", "411026", "Pune", "West", "www.mckmachinery.com", "REG-MH03", "Rahul Deshmukh", "rahul@mckmachinery.com", "+91 98230 55667", "Nitin Kulkarni", "nitin@mckmachinery.com", "+91 98230 55668", "Sales Office", "sales@mckmachinery.com", "020-27123344"],
            ["DOC-5005", "DocuMatrix Global Logistics", "28/08/2026", "Container Terminal Road", "Willingdon Island", "Near Port Gate 2", "India", "Kerala", "Kerala", "Kochi", "Kochi", "682003", "Ernakulam", "South", "www.documatrix.com", "REG-KL01", "George Varghese", "george@documatrix.com", "+91 94470 99887", "Manoj Kumar", "manoj@documatrix.com", "+91 94470 99888", "Customer Care", "care@documatrix.com", "0484-2667788"],
            ["MSD-6006", "MSD Steels & Fasteners", "29/08/2026", "Plot 104, Transport Nagar", "Industrial Estate", "Ring Road Bypass", "India", "Rajasthan", "Rajasthan", "Jaipur", "Jaipur", "302013", "Jaipur", "North-West", "www.msdsteels.com", "REG-RJ01", "Mahesh Sharma", "mahesh@msdsteels.com", "+91 94140 77665", "Pooja Sharma", "pooja@msdsteels.com", "+91 94140 77666", "Accounts Desk", "accounts@msdsteels.com", "0141-2334455"],
            ["MOL-7007", "Mashal Oil & Agro Extracts", "30/08/2026", "Plot No. 12, Industrial Area", "Phase 2, Focal Point", "Near Metro Depot", "India", "Punjab", "Punjab", "Ludhiana", "Ludhiana", "141001", "Ludhiana", "North", "www.mashaloil.com", "REG-PB02", "Shivam", "shivam@mashaloil.com", "+91 78147 49816", "Raman Singla", "raman@mashaloil.com", "+91 78147 49817", "Main Plant Line", "contact@mashaloil.com", "0161-4556677"],
            ["MOMT-8008", "MOMT Heavy Tools & Dies", "31/08/2026", "Sector 25, HSIIDC Industrial Estate", "Ballabgarh", "Mathura Road", "India", "Haryana", "Haryana", "Faridabad", "Faridabad", "121004", "Faridabad", "North", "www.momttools.com", "REG-HR01", "Anil Chauhan", "anil@momttools.com", "+91 98100 22334", "Rajesh Verma", "rajesh@momttools.com", "+91 98100 22335", "Board Line", "info@momttools.com", "0129-2233445"],
            ["GEN-9009", "General Allied Trading Enterprises", "01/09/2026", "Commercial Complex 8", "Connaught Place", "Barakhamba Road", "India", "Delhi", "Delhi", "New Delhi", "New Delhi", "110001", "Central Delhi", "North", "www.generalallied.com", "REG-DL01", "Karan Kapoor", "karan@generalallied.com", "+91 98101 55667", "Rohan Mehra", "rohan@generalallied.com", "+91 98101 55668", "Customer Help", "help@generalallied.com", "011-23344556"]
        ]

        for r in sample_rows:
            writer.writerow(r)

        return b'\xef\xbb\xbf' + output.getvalue().encode("utf-8")

    @classmethod
    def generate_call_logs_excel_bytes(cls, calls: list) -> bytes:
        """Generate styled Excel (.xlsx) report for Call Logs & Telephony History."""
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from datetime import timezone, timedelta

        ist_tz = timezone(timedelta(hours=5, minutes=30))
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Call Telephony Logs"

        headers = [
            "S.No", "Call ID", "UUID", "Date & Time (IST)", "Direction",
            "Customer Phone", "Smartflo Virtual DID", "Address Code", "Customer Name",
            "Contact Person", "City / State", "Handled Agent", "Status",
            "Duration (MM:SS)", "Duration (s)", "Billsec (s)", "Hangup Reason", "Recording URL"
        ]
        ws.append(headers)

        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        center_align = Alignment(horizontal="center", vertical="center")
        thin_border = Border(
            left=Side(style='thin', color='CBD5E1'),
            right=Side(style='thin', color='CBD5E1'),
            top=Side(style='thin', color='CBD5E1'),
            bottom=Side(style='thin', color='CBD5E1')
        )

        ws.row_dimensions[1].height = 28
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align
            cell.border = thin_border

        for idx, c in enumerate(calls, start=1):
            time_str = "—"
            if c.start_time:
                st = c.start_time
                if st.tzinfo is None:
                    st = st.replace(tzinfo=timezone.utc)
                ist_dt = st.astimezone(ist_tz)
                time_str = ist_dt.strftime("%d %b %Y, %I:%M %p")

            dur_secs = c.duration_seconds or 0
            dur_mins = f"{dur_secs // 60:02d}:{dur_secs % 60:02d}"
            bill_secs = c.billsec or dur_secs
            dir_str = "Inbound" if c.direction == "incoming" else "Outbound"
            cust_code = c.customer.party_code if c.customer and c.customer.party_code else "—"
            cust_name = c.customer.party_name if c.customer else (c.customer.name if c.customer else "Unregistered Caller")
            contact_p = c.customer.contact_person_1 if c.customer and c.customer.contact_person_1 else "—"
            city_state = f"{c.customer.city or ''}, {c.customer.state or ''}".strip(', ') if c.customer else "—"
            agent_name = c.agent_name or (c.user.full_name if c.user else "System")

            vid_val = c.call_to_number
            if c.direction == "outgoing":
                vid_val = c.agent_number or (c.user.vid if c.user else "918065908540")

            row_data = [
                idx,
                c.call_id or "—",
                c.uuid or c.call_id or "—",
                time_str,
                dir_str,
                c.phone_number or "—",
                vid_val or "—",
                cust_code,
                cust_name,
                contact_p,
                city_state,
                agent_name,
                (c.status or "completed").title(),
                dur_mins,
                dur_secs,
                bill_secs,
                c.hangup_cause or c.notes or "—",
                c.recording_url or "—"
            ]
            ws.append(row_data)

            row_num = idx + 1
            ws.row_dimensions[row_num].height = 20
            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=row_num, column=col_idx)
                cell.border = thin_border
                cell.font = Font(name="Calibri", size=10)
                if col_idx in [1, 4, 5, 13, 14, 15, 16]:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                else:
                    cell.alignment = Alignment(vertical="center")

        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 11), 50)

        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()

    @classmethod
    def generate_call_logs_csv_bytes(cls, calls: list) -> bytes:
        """Generate UTF-8 CSV report for Call Logs & Telephony History."""
        from datetime import timezone, timedelta
        ist_tz = timezone(timedelta(hours=5, minutes=30))

        output = io.StringIO()
        writer = csv.writer(output)

        headers = [
            "S.No", "Call ID", "UUID", "Date & Time (IST)", "Direction",
            "Customer Phone", "Smartflo Virtual DID", "Address Code", "Customer Name",
            "Contact Person", "City / State", "Handled Agent", "Status",
            "Duration (MM:SS)", "Duration (s)", "Billsec (s)", "Hangup Reason", "Recording URL"
        ]
        writer.writerow(headers)

        for idx, c in enumerate(calls, start=1):
            time_str = "—"
            if c.start_time:
                st = c.start_time
                if st.tzinfo is None:
                    st = st.replace(tzinfo=timezone.utc)
                ist_dt = st.astimezone(ist_tz)
                time_str = ist_dt.strftime("%d %b %Y, %I:%M %p")

            dur_secs = c.duration_seconds or 0
            dur_mins = f"{dur_secs // 60:02d}:{dur_secs % 60:02d}"
            bill_secs = c.billsec or dur_secs
            dir_str = "Inbound" if c.direction == "incoming" else "Outbound"
            cust_code = c.customer.party_code if c.customer and c.customer.party_code else "—"
            cust_name = c.customer.party_name if c.customer else (c.customer.name if c.customer else "Unregistered Caller")
            contact_p = c.customer.contact_person_1 if c.customer and c.customer.contact_person_1 else "—"
            city_state = f"{c.customer.city or ''}, {c.customer.state or ''}".strip(', ') if c.customer else "—"
            agent_name = c.agent_name or (c.user.full_name if c.user else "System")

            vid_val = c.call_to_number
            if c.direction == "outgoing":
                vid_val = c.agent_number or (c.user.vid if c.user else "918065908540")

            writer.writerow([
                idx,
                c.call_id or "—",
                c.uuid or c.call_id or "—",
                time_str,
                dir_str,
                c.phone_number or "—",
                vid_val or "—",
                cust_code,
                cust_name,
                contact_p,
                city_state,
                agent_name,
                (c.status or "completed").title(),
                dur_mins,
                dur_secs,
                bill_secs,
                c.hangup_cause or c.notes or "—",
                c.recording_url or "—"
            ])

        return b'\xef\xbb\xbf' + output.getvalue().encode("utf-8")

    @staticmethod
    def generate_customers_excel_bytes(customers: List[Customer]) -> bytes:
        """Generate professionally styled master Excel (.xlsx) containing all customers with 25 standard columns & metadata."""
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Master Customers Directory"

        HEADER_FILL = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
        HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        REGULAR_FONT = Font(name="Calibri", size=10, color="1E293B")
        BOLD_FONT = Font(name="Calibri", size=10, bold=True, color="0F172A")
        BORDER_THIN = Border(
            left=Side(style="thin", color="E2E8F0"),
            right=Side(style="thin", color="E2E8F0"),
            top=Side(style="thin", color="E2E8F0"),
            bottom=Side(style="thin", color="E2E8F0")
        )

        headers = [
            "Address Code*", "Address Description*", "Address Date(DD/MM/YYYY)*", "Address Line 1*",
            "Address Line 2*", "Address Line 3", "Country*", "State*", "State", "City*", "City",
            "Pincode*", "District", "Zone", "Company Website", "Sales Region Code",
            "Contact Person 1", "Email-Id 1", "Phone Number 1", "Contact Person 2", "Email-Id 2",
            "Phone Number 2", "Contact Person 3", "Email-Id 3", "Phone Number 3",
            "Category", "Rating", "Assigned Employee", "Created Date"
        ]

        ws.append(headers)
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = BORDER_THIN
        ws.row_dimensions[1].height = 28

        for row_idx, c in enumerate(customers, start=2):
            assigned_name = c.assigned_employee.full_name if c.assigned_employee else "Unassigned / Shared"
            rating_str = f"{c.rating} Star{'s' if c.rating != 1 else ''}" if c.rating else "Unrated"
            created_str = c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else ""

            # Fetch secondary phones
            phone_2_val = ""
            phone_3_val = ""
            if c.phone_numbers:
                for p in c.phone_numbers:
                    if p.label == "Phone 2" or p.phone_type == "Secondary Mobile":
                        phone_2_val = p.phone_number
                    elif p.label == "Phone 3" or p.phone_type == "Office / Alternate":
                        phone_3_val = p.phone_number

            row_data = [
                c.party_code or "",
                c.party_name or "",
                c.address_date or "",
                c.address_line_1 or "",
                c.address_line_2 or "",
                c.address_line_3 or "",
                c.country or "India",
                c.state or "",
                c.state or "",
                c.city or "",
                c.city or "",
                c.pincode or "",
                c.district or "",
                c.zone or "",
                c.company_website or "",
                c.sales_region_code or "",
                c.contact_person_1 or "",
                c.email_id_1 or "",
                c.phone_1 or "",
                c.contact_person_2 or "",
                c.email_id_2 or "",
                phone_2_val,
                c.contact_person_3 or "",
                c.email_id_3 or "",
                phone_3_val,
                c.category or "General",
                rating_str,
                assigned_name,
                created_str
            ]
            ws.append(row_data)

            for col_idx in range(1, len(row_data) + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.font = REGULAR_FONT
                cell.border = BORDER_THIN
                if col_idx in (1, 19, 22, 25):  # Code & Phone columns
                    cell.font = BOLD_FONT
                if col_idx in (26, 27, 28):
                    cell.alignment = Alignment(horizontal="center")

            ws.row_dimensions[row_idx].height = 20

        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()

    @staticmethod
    def generate_customers_csv_bytes(customers: List[Customer]) -> bytes:
        """Generate UTF-8 BOM CSV containing all master customers with standard 25 columns + Category/Rating/Assigned."""
        output = io.StringIO()
        writer = csv.writer(output)

        headers = [
            "Address Code*", "Address Description*", "Address Date(DD/MM/YYYY)*", "Address Line 1*",
            "Address Line 2*", "Address Line 3", "Country*", "State*", "State", "City*", "City",
            "Pincode*", "District", "Zone", "Company Website", "Sales Region Code",
            "Contact Person 1", "Email-Id 1", "Phone Number 1", "Contact Person 2", "Email-Id 2",
            "Phone Number 2", "Contact Person 3", "Email-Id 3", "Phone Number 3",
            "Category", "Rating", "Assigned Employee"
        ]
        writer.writerow(headers)

        for c in customers:
            assigned_name = c.assigned_employee.full_name if c.assigned_employee else "Unassigned / Shared"
            rating_str = f"{c.rating} Star" if c.rating else "Unrated"
            phone_2_val = ""
            phone_3_val = ""
            if c.phone_numbers:
                for p in c.phone_numbers:
                    if p.label == "Phone 2" or p.phone_type == "Secondary Mobile":
                        phone_2_val = p.phone_number
                    elif p.label == "Phone 3" or p.phone_type == "Office / Alternate":
                        phone_3_val = p.phone_number

            writer.writerow([
                c.party_code or "",
                c.party_name or "",
                c.address_date or "",
                c.address_line_1 or "",
                c.address_line_2 or "",
                c.address_line_3 or "",
                c.country or "India",
                c.state or "",
                c.state or "",
                c.city or "",
                c.city or "",
                c.pincode or "",
                c.district or "",
                c.zone or "",
                c.company_website or "",
                c.sales_region_code or "",
                c.contact_person_1 or "",
                c.email_id_1 or "",
                c.phone_1 or "",
                c.contact_person_2 or "",
                c.email_id_2 or "",
                phone_2_val,
                c.contact_person_3 or "",
                c.email_id_3 or "",
                phone_3_val,
                c.category or "General",
                rating_str,
                assigned_name
            ])

        return b'\xef\xbb\xbf' + output.getvalue().encode("utf-8")

