import io
import csv
import json
from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.import_job import ImportJob, ImportError, ImportUpdate
from backend.app.schemas.stats import ImportSummaryResponse
from backend.app.services.excel_service import ExcelService, STRICT_COLUMNS
from backend.app.services.audit_service import AuditService
from backend.app.utils.security import get_current_user, get_current_admin_user

router = APIRouter(prefix="/imports", tags=["Excel Import"])

@router.get("/template-columns")
def get_template_columns():
    """Return the exact 15 required columns in exact sequence."""
    return {
        "total_columns": len(STRICT_COLUMNS),
        "columns": STRICT_COLUMNS
    }

@router.get("/sample-excel")
def download_sample_excel():
    """Download official 15-column sample Excel template."""
    file_bytes = ExcelService.generate_sample_excel_bytes()
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=sample_customer_import_15_columns.xlsx"}
    )

@router.get("/sample-csv")
def download_sample_csv():
    """Download official 15-column sample CSV template."""
    file_bytes = ExcelService.generate_sample_csv_bytes()
    return Response(
        content=file_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sample_customer_import_15_columns.csv"}
    )

@router.post("/preview")
async def preview_excel_import(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Inspect uploaded Excel/CSV file, validate exact 15 columns sequence, and return sample rows."""
    if not (file.filename.endswith(".xlsx") or file.filename.endswith(".xls") or file.filename.endswith(".csv")):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload an Excel (.xlsx) or CSV (.csv) file.")

    contents = await file.read()
    if len(contents) > 15 * 1024 * 1024:  # 15 MB limit
        raise HTTPException(status_code=400, detail="File exceeds maximum allowed size of 15MB")

    try:
        preview = ExcelService.preview_import(contents, file.filename)
        return preview
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")

@router.post("/process", response_model=ImportSummaryResponse)
async def process_excel_import(
    file: UploadFile = File(...),
    import_mode: str = Form("update"),  # "update", "skip"
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Execute customer import with strict 15-column validation, duplicate detection, and error tracking."""
    contents = await file.read()

    try:
        result = ExcelService.process_import(
            db=db,
            file_bytes=contents,
            filename=file.filename,
            import_mode=import_mode,
            user_id=current_user.id
        )

        AuditService.log(
            db,
            action="EXCEL_IMPORT_COMPLETED",
            entity_type="import",
            entity_id=str(result["job_id"]),
            changes={
                "filename": file.filename,
                "imported": result["imported_count"],
                "updated": result["updated_count"],
                "duplicates": result["duplicate_count"],
                "errors": result["error_count"]
            },
            user=current_user
        )

        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")

@router.get("/history")
def get_import_history(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve previous Excel import jobs."""
    jobs = (
        db.query(ImportJob)
        .options(joinedload(ImportJob.uploaded_by))
        .order_by(desc(ImportJob.created_at))
        .limit(limit)
        .all()
    )
    return [
        {
            "id": j.id,
            "filename": j.filename,
            "total_rows": j.total_rows,
            "imported_count": j.imported_count,
            "updated_count": j.updated_count,
            "duplicate_count": j.duplicate_count,
            "error_count": j.error_count,
            "status": j.status,
            "uploaded_by": j.uploaded_by.full_name if j.uploaded_by else "System",
            "created_at": j.created_at.isoformat() if j.created_at else None
        }
        for j in jobs
    ]

@router.get("/{job_id}/errors")
def get_job_errors(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve row-by-row error logs for a specific import job."""
    errors = db.query(ImportError).filter(ImportError.import_job_id == job_id).order_by(ImportError.row_number).all()
    
    formatted_errors = []
    for e in errors:
        raw = e.raw_data or {}
        # Case-insensitive field search helper
        def get_field(names: list) -> str:
            for k, v in raw.items():
                if k.lower().replace(" ", "").replace("_", "") in [n.lower().replace(" ", "").replace("_", "") for n in names]:
                    return str(v).strip()
            return "N/A"

        party_code = get_field(["Party Code", "PartyCode", "Code"])
        party_name = get_field(["Party Name", "PartyName", "Name", "Customer"])
        phone_1 = get_field(["Phone 1", "Phone1", "Mobile", "Phone"])
        contact_person = get_field(["Contact Person 1", "ContactPerson1", "Contact"])
        pincode = get_field(["Pincode", "Pin Code", "PostalCode"])

        # Determine actionable suggestion
        reason = e.error_reason or ""
        suggestion = "Please review this row in your Excel file, correct the data, and re-import."
        if "Phone 1" in reason:
            suggestion = f"The 'Phone 1' column contains '{phone_1}'. Please replace it with a valid 10-digit mobile number in Excel Row {e.row_number}."
        elif "Party Name" in reason:
            suggestion = f"The 'Party Name' column is empty in Excel Row {e.row_number}. Please provide a valid customer/business name."
        elif "Email" in reason:
            suggestion = f"The email address format in Excel Row {e.row_number} is invalid. Please correct it to format 'name@domain.com' or leave blank."

        formatted_errors.append({
            "id": e.id,
            "row_number": e.row_number,
            "party_code": party_code,
            "party_name": party_name,
            "phone_1": phone_1,
            "contact_person": contact_person,
            "pincode": pincode,
            "error_reason": reason,
            "suggestion": suggestion,
            "raw_data": raw
        })

    return formatted_errors

@router.get("/{job_id}/download-errors")
def download_job_errors_csv(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Download failed rows and error reasons as a downloadable CSV."""
    errors = db.query(ImportError).filter(ImportError.import_job_id == job_id).order_by(ImportError.row_number).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Excel Row #", "Party Code", "Party Name", "Phone 1", "Error Reason", "Action Needed"])

    for e in errors:
        raw = e.raw_data or {}
        p_code = raw.get("Party Code") or raw.get("Party code") or ""
        p_name = raw.get("Party Name") or raw.get("Party name") or ""
        p_phone = raw.get("Phone 1") or raw.get("Phone1") or ""
        
        action = "Correct the field in Excel and re-import."
        if "Phone 1" in e.error_reason:
            action = f"Provide a valid 10-digit mobile number instead of '{p_phone}'."

        writer.writerow([e.row_number, p_code, p_name, p_phone, e.error_reason, action])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=import_job_{job_id}_errors.csv"}
    )

@router.get("/{job_id}/updates")
def get_job_updates(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve row-by-row synchronized/updated records log for a specific import job."""
    updates = db.query(ImportUpdate).filter(ImportUpdate.import_job_id == job_id).order_by(ImportUpdate.row_number).all()
    
    return [
        {
            "id": u.id,
            "row_number": u.row_number,
            "party_code": u.party_code or "N/A",
            "party_name": u.party_name or "N/A",
            "previous_data": u.previous_data or {},
            "new_data": u.new_data or {},
            "changed_fields": u.changed_fields or [],
            "created_at": u.created_at.isoformat() if u.created_at else None
        }
        for u in updates
    ]

@router.get("/{job_id}/download-updates")
def download_job_updates_csv(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Download updated records log as a downloadable CSV."""
    updates = db.query(ImportUpdate).filter(ImportUpdate.import_job_id == job_id).order_by(ImportUpdate.row_number).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Excel Row #", "Party Code", "Party Name", "Updated Fields", "Previous Data (Before)", "New Data (Updated)", "Update Timestamp"])

    for u in updates:
        prev_str = json.dumps(u.previous_data or {})
        new_str = json.dumps(u.new_data or {})
        changed_str = ", ".join(u.changed_fields or []) if isinstance(u.changed_fields, list) else str(u.changed_fields)
        created_str = u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else ""

        writer.writerow([u.row_number, u.party_code, u.party_name, changed_str, prev_str, new_str, created_str])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=import_job_{job_id}_updated_records.csv"}
    )
