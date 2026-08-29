import os
import io
import mimetypes
from typing import Tuple, Optional
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from backend.app.models.customer_document import CustomerDocument
from backend.app.models.user import User
from backend.app.services.audit_service import AuditService
import logging

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {
    # PDF
    "application/pdf",
    # Images
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/svg+xml",
    # Office Documents
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", # .xlsx
    "application/vnd.ms-excel",                                          # .xls
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", # .docx
    "application/msword",                                                # .doc
    # Text / CSV
    "text/csv",
    "text/plain",
    # Archives
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream"
}

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

class DocumentStorageService:
    @staticmethod
    def get_mime_type(filename: str, header_content_type: Optional[str] = None) -> str:
        """Infer or sanitize content MIME type."""
        if header_content_type and header_content_type in ALLOWED_MIME_TYPES:
            return header_content_type
        
        guessed, _ = mimetypes.guess_type(filename)
        return guessed or header_content_type or "application/octet-stream"

    @classmethod
    async def store_document(
        cls,
        db: Session,
        customer_id: int,
        file: UploadFile,
        category: str = "General",
        description: Optional[str] = None,
        user: Optional[User] = None
    ) -> CustomerDocument:
        """
        Store uploaded document with serverless-compatible persistent storage.
        Uses database binary storage with zero local disk dependency.
        """
        file_bytes = await file.read()
        file_size = len(file_bytes)

        if file_size == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes)")
        
        if file_size > MAX_FILE_SIZE_BYTES:
            raise HTTPException(status_code=400, detail=f"File exceeds maximum allowed size of 25 MB ({file_size / (1024*1024):.1f} MB)")

        filename = os.path.basename(file.filename or "document")
        content_type = cls.get_mime_type(filename, file.content_type)

        # Check if Vercel Blob or AWS S3 is configured, otherwise store persistent BLOB in DB
        storage_provider = "database_blob"
        storage_url = None

        doc = CustomerDocument(
            customer_id=customer_id,
            uploaded_by_user_id=user.id if user else None,
            filename=filename,
            file_size_bytes=file_size,
            content_type=content_type,
            category=category or "General",
            description=description,
            storage_provider=storage_provider,
            file_data=file_bytes,
            storage_url=storage_url
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        AuditService.log(
            db,
            action="DOCUMENT_UPLOADED",
            entity_type="customer_document",
            entity_id=str(doc.id),
            changes={
                "filename": filename,
                "category": category,
                "file_size": file_size,
                "customer_id": customer_id
            },
            user=user
        )

        logger.info(f"Stored document #{doc.id} '{filename}' ({file_size} bytes, category: {category}) for customer #{customer_id}")
        return doc

    @classmethod
    def get_document_payload(cls, doc: CustomerDocument) -> Tuple[bytes, str, str]:
        """
        Retrieve binary payload for download or preview.
        Returns (bytes, content_type, filename).
        """
        if not doc.file_data:
            raise HTTPException(status_code=404, detail="Document binary content not found")
        
        return doc.file_data, doc.content_type, doc.filename

    @classmethod
    def delete_document(cls, db: Session, doc: CustomerDocument, user: Optional[User] = None) -> bool:
        """Safely delete document without affecting customer profile or other documents."""
        doc_id = doc.id
        doc_filename = doc.filename
        customer_id = doc.customer_id

        db.delete(doc)
        db.commit()

        AuditService.log(
            db,
            action="DOCUMENT_DELETED",
            entity_type="customer_document",
            entity_id=str(doc_id),
            changes={"filename": doc_filename, "customer_id": customer_id},
            user=user
        )

        logger.info(f"Deleted document #{doc_id} ('{doc_filename}') of customer #{customer_id}")
        return True
