import logging
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.customer import Customer
from backend.app.services.tcsion_scraper import tcsion_scraper
from backend.app.services.audit_service import AuditService
from backend.app.utils.security import get_current_user
from backend.app.models.user import User

logger = logging.getLogger("integrations_router")

router = APIRouter(prefix="/integrations", tags=["Enterprise Integrations & TCS iON"])

class TcsIonLedgerRequest(BaseModel):
    customer_id: Optional[int] = None
    party_name: str = Field(..., description="Party or Company Name to search in TCS iON")
    months_back: int = Field(default=3, ge=1, le=12, description="Number of historical months to query")

@router.get("/tcsion/status", response_model=Dict[str, Any])
def get_tcsion_sync_status():
    """
    Returns current active state of the TCS iON scraper and last sync status.
    """
    return tcsion_scraper.get_status()

@router.post("/tcsion/ledger", response_model=Dict[str, Any])
async def sync_tcsion_party_ledger(
    payload: TcsIonLedgerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Triggers automated live sync of Party Ledger Detail Report from TCS iON Finance & Accounting.
    Locked to single execution to prevent concurrent session collisions.
    """
    party_name = payload.party_name.strip()
    if not party_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Party Name cannot be empty."
        )

    # Optional customer validation
    customer = None
    if payload.customer_id:
        customer = db.query(Customer).filter(Customer.id == payload.customer_id).first()
        if customer and not party_name:
            party_name = customer.party_name or customer.name

    logger.info(f"User {current_user.email} triggered TCS iON Ledger sync for '{party_name}'")

    try:
        ledger_result = await tcsion_scraper.scrape_party_ledger(
            party_name=party_name,
            months_back=payload.months_back
        )

        # Audit log the integration event
        try:
            AuditService.log(
                db=db,
                action="TCSION_LEDGER_SYNC",
                entity_type="CUSTOMER",
                entity_id=str(payload.customer_id or 0),
                changes={
                    "party_name": party_name,
                    "records_count": ledger_result.get("total_records", 0),
                    "closing_balance": ledger_result.get("summary", {}).get("closing_balance", 0)
                },
                user=current_user
            )
        except Exception as audit_err:
            logger.warning(f"Audit log failed for TCS iON sync: {audit_err}")

        return ledger_result

    except RuntimeError as r_err:
        err_str = str(r_err)
        if "already logged" in err_str.lower() or "cooldown" in err_str.lower():
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=err_str
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=err_str
        )
    except Exception as e:
        logger.error(f"Error executing TCS iON sync: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TCS iON Automation encountered an unexpected error: {str(e)}"
        )
