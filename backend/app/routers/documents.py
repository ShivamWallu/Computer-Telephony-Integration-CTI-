import io
import urllib.parse
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Header, UploadFile, File, Form, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from backend.app.database import get_db
from backend.app.models.customer import Customer
from backend.app.models.customer_document import CustomerDocument
from backend.app.models.user import User
from backend.app.schemas.customer_document import CustomerDocumentOut
from backend.app.services.document_storage_service import DocumentStorageService
from backend.app.utils.security import get_current_user, decode_access_token
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/customers/{customer_id}/documents", tags=["Customer Documents"])

def get_document_user(
    token_param: Optional[str] = Query(None, alias="token"),
    auth_header: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
) -> User:
    """Flexible auth extractor supporting Bearer header or ?token= query parameter."""
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    elif token_param:
        token = token_param.strip()
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired authentication token")
    
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account inactive or not found")
    return user

def verify_customer_access(customer_id: int, user: User, db: Session) -> Customer:
    """Verify customer exists and check role-based access for assigned employee."""
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.is_archived == False).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer record not found")
    
    if user.role == "employee" and customer.assigned_employee_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied: Customer is not assigned to you")
    
    return customer

@router.get("", response_model=List[CustomerDocumentOut])
def list_customer_documents(
    customer_id: int,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all documents uploaded for a specific customer.
    Fast JSON response without heavy file payloads.
    """
    verify_customer_access(customer_id, current_user, db)

    query = (
        db.query(CustomerDocument)
        .options(joinedload(CustomerDocument.uploaded_by))
        .filter(CustomerDocument.customer_id == customer_id)
    )
    if category:
        query = query.filter(CustomerDocument.category == category)
    
    docs = query.order_by(CustomerDocument.created_at.desc()).all()
    return [CustomerDocumentOut.model_validate(d) for d in docs]

@router.post("", response_model=CustomerDocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_customer_document(
    customer_id: int,
    file: UploadFile = File(...),
    category: str = Form("General"),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Upload a new document (PDF, PNG, JPG, Excel, Word, etc.) for a specific customer.
    Stores metadata and persistent file payload.
    """
    verify_customer_access(customer_id, current_user, db)

    doc = await DocumentStorageService.store_document(
        db=db,
        customer_id=customer_id,
        file=file,
        category=category,
        description=description,
        user=current_user
    )

    return CustomerDocumentOut.model_validate(doc)

@router.get("/{document_id}/download")
def download_customer_document(
    customer_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_document_user)
):
    """
    Download a customer document as an attachment.
    Supports both Authorization header and ?token= query parameter.
    """
    verify_customer_access(customer_id, current_user, db)

    doc = db.query(CustomerDocument).filter(
        CustomerDocument.id == document_id,
        CustomerDocument.customer_id == customer_id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_bytes, content_type, filename = DocumentStorageService.get_document_payload(doc)

    # Encode filename for Content-Disposition header
    encoded_filename = urllib.parse.quote(filename)
    headers = {
        "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{encoded_filename}",
        "Content-Length": str(len(file_bytes))
    }

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type=content_type,
        headers=headers
    )

@router.get("/{document_id}/preview")
def preview_customer_document(
    customer_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_document_user)
):
    """
    Inline preview for images and PDF documents directly in the browser.
    Supports both Authorization header and ?token= query parameter.
    """
    verify_customer_access(customer_id, current_user, db)

    doc = db.query(CustomerDocument).filter(
        CustomerDocument.id == document_id,
        CustomerDocument.customer_id == customer_id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_bytes, content_type, filename = DocumentStorageService.get_document_payload(doc)

    headers = {
        "Content-Disposition": f"inline; filename=\"{filename}\"",
        "Content-Length": str(len(file_bytes))
    }

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type=content_type,
        headers=headers
    )

@router.delete("/{document_id}")
def delete_customer_document(
    customer_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Safely delete an individual customer document.
    Customer profile and other documents remain 100% untouched.
    """
    verify_customer_access(customer_id, current_user, db)

    doc = db.query(CustomerDocument).filter(
        CustomerDocument.id == document_id,
        CustomerDocument.customer_id == customer_id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    filename = doc.filename
    DocumentStorageService.delete_document(db, doc, user=current_user)

    return {
        "status": "success",
        "deleted_document_id": document_id,
        "message": f"Document '{filename}' deleted successfully"
    }
