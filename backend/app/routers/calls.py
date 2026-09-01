import json
import asyncio
import os
import hashlib
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, or_, func
from datetime import datetime, timezone
from backend.app.database import get_db
from backend.app.models.call import Call
from backend.app.models.customer import Customer
from backend.app.models.user import User
from backend.app.models.interaction import CustomerInteraction
from backend.app.schemas.call import (
    IncomingCallWebhook, OutgoingCallRequest, CallStatusUpdate, CallOut, IncomingCallResponse
)
from backend.app.services.cti_service import CTIService, broadcast_manager, parse_smartflo_timestamp
from backend.app.services.phone_normalizer import PhoneNormalizer
from backend.app.services.audit_service import AuditService
from backend.app.utils.security import get_current_user, get_optional_current_user, get_current_admin_user
import logging

logger = logging.getLogger(__name__)

CACHE_DIR = Path("backend/cache/recordings")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/calls", tags=["CTI & Calls"])

async def _extract_request_data(request: Request) -> Dict[str, Any]:
    """Helper to extract query params, form-data, or JSON from any incoming HTTP request."""
    data = {}
    # 1. Query parameters
    if request.query_params:
        data.update(dict(request.query_params))

    # 2. Form data or JSON body
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        try:
            body_json = await request.json()
            if isinstance(body_json, dict):
                data.update(body_json)
        except Exception:
            pass
    elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        try:
            form = await request.form()
            data.update(dict(form))
        except Exception:
            pass

    return data

@router.api_route("/exotel/incoming", methods=["GET", "POST"])
async def exotel_incoming_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Exotel Passthru / Inbound Call Webhook Endpoint.
    Configure this URL in your Exotel App Builder 'Passthru' applet:
    https://<ngrok-or-domain>/api/calls/exotel/incoming
    
    Exotel sends: CallSid, CallFrom (Caller), CallTo (Virtual Number), Direction, Created
    Identifies customer in < 10ms, creates Call record, and broadcasts live screen-pop to CRM!
    """
    raw_data = await _extract_request_data(request)
    logger.info(f"[EXOTEL PASSTHRU WEBHOOK RECEIVED] Method: {request.method} | Data: {raw_data}")

    provider = CTIService.get_provider("exotel")
    incoming_payload = provider.parse_incoming_payload(raw_data)

    if not incoming_payload.phone_number:
        logger.warning("Exotel webhook received without a valid caller phone number.")
        return {"status": "ok", "message": "No caller number found in payload", "data": raw_data}

    response = CTIService.handle_incoming_call(
        db=db,
        incoming=incoming_payload
    )

    # Return clean 200 OK response with metadata for Exotel
    return {
        "status": "ok",
        "call_id": response.call_id,
        "caller_phone": response.phone_number,
        "customer_found": response.customer_found,
        "customer_name": response.customer.name if response.customer else None,
        "message": response.message
    }

@router.api_route("/exotel/passthru", methods=["GET", "POST"])
async def exotel_passthru_alias(request: Request, db: Session = Depends(get_db)):
    """Alias for exotel_incoming_webhook for flexibility in Exotel configuration."""
    return await exotel_incoming_webhook(request, db)

@router.api_route("/exotel/status", methods=["GET", "POST"])
async def exotel_status_callback(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Exotel Call Status & End-of-Call Callback Webhook.
    Configure this URL in Exotel Connect Applet or Status Callback URL:
    https://<ngrok-or-domain>/api/calls/exotel/status
    
    Exotel sends: CallSid, Status (completed, busy, no-answer, failed), DialCallDuration, RecordingUrl
    """
    raw_data = await _extract_request_data(request)
    logger.info(f"[EXOTEL STATUS CALLBACK RECEIVED] Data: {raw_data}")

    call_sid = raw_data.get("CallSid") or raw_data.get("CallUUID") or raw_data.get("call_id")
    if not call_sid:
        return {"status": "ok", "message": "No CallSid provided"}

    call = db.query(Call).filter(Call.call_id == str(call_sid).strip()).first()
    raw_status = (raw_data.get("Status") or raw_data.get("CallStatus") or "completed").lower()

    duration = raw_data.get("DialCallDuration") or raw_data.get("Duration") or raw_data.get("Legs")
    duration_secs = int(duration) if duration and str(duration).isdigit() else 0
    recording_url = raw_data.get("RecordingUrl") or raw_data.get("RecordingURL")

    if call:
        call.status = raw_status
        call.duration_seconds = duration_secs
        if recording_url:
            call.recording_url = str(recording_url)
        call.end_time = datetime.now(timezone.utc)

        # If call was completed and linked to a customer, create interaction log if not already created
        if call.customer_id:
            duration_mins = f"{duration_secs // 60:02d}:{duration_secs % 60:02d}"
            interaction = CustomerInteraction(
                customer_id=call.customer_id,
                user_id=call.user_id,
                interaction_type="call",
                direction=call.direction,
                subject=f"Exotel Inbound Call ({raw_status.title()})",
                content=f"Call completed via Exotel. Duration: {duration_mins}. Recording: {recording_url or 'N/A'}",
                meta_info={
                    "call_id": call.call_id,
                    "duration": duration_mins,
                    "duration_seconds": duration_secs,
                    "recording_url": recording_url,
                    "phone": call.phone_number,
                    "provider": "exotel"
                },
                interaction_time=call.start_time
            )
            db.add(interaction)

        db.commit()

    return {"status": "ok", "call_id": call_sid, "updated_status": raw_status}

@router.api_route("/smartflo/incoming", methods=["GET", "POST"])
async def smartflo_incoming_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Tata Smartflo Inbound Screen-Pop Webhook Endpoint.
    Configure this URL in your Tata Smartflo Portal:
    https://<ngrok-or-domain>/api/calls/smartflo/incoming
    
    Supports all 5 Smartflo Virtual Numbers.
    Extracts: caller_id_number, call_to_number (DID/VID), uuid, call_id, start_stamp, operator, circle.
    Instantly locates customer profile (< 10ms), resolves employee, and pushes real-time screen-pop to CRM!
    """
    raw_data = await _extract_request_data(request)
    logger.info(f"[SMARTFLO INCOMING WEBHOOK RECEIVED] Method: {request.method} | Data: {raw_data}")

    provider = CTIService.get_provider("smartflo")
    incoming_payload = provider.parse_incoming_payload(raw_data)

    if not incoming_payload.phone_number:
        logger.warning("Smartflo webhook received without a valid caller phone number.")
        return {"status": "ok", "message": "No caller number found in payload", "data": raw_data}

    response = CTIService.handle_incoming_call(
        db=db,
        incoming=incoming_payload
    )

    # Return clean 200 OK response with metadata for Tata Smartflo
    return {
        "status": "ok",
        "call_id": response.call_id,
        "uuid": response.uuid,
        "caller_phone": response.phone_number,
        "call_to_number": response.call_to_number,
        "assigned_employee": response.assigned_employee_name,
        "customer_found": response.customer_found,
        "customer_name": response.customer.party_name if response.customer else None,
        "customer": response.customer.model_dump() if response.customer else None,
        "operator": response.operator,
        "circle": response.circle,
        "message": response.message
    }

@router.api_route("/smartflo", methods=["GET", "POST"])
@router.api_route("/smartflo/webhook", methods=["GET", "POST"])
async def smartflo_universal_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Universal Smartflo Webhook Router.
    Automatically detects whether incoming payload is:
    - CDR Disconnect (Call Ended / Disconnected)
    - Outbound Screen-Pop (Agent Dialed / ClickToCall init)
    - Inbound Screen-Pop (Customer calling DID)
    """
    raw_data = await _extract_request_data(request)
    logger.info(f"[SMARTFLO UNIVERSAL ROUTER] Received payload keys: {list(raw_data.keys())}")
    
    is_cdr = bool(
        raw_data.get("end_stamp") or
        raw_data.get("hangup_cause") or
        raw_data.get("hangup_cause_code") or
        raw_data.get("recording_url") or
        raw_data.get("billsec") or
        raw_data.get("call_flow")
    )
    direction_hint = str(raw_data.get("direction", "")).lower()
    clean_vid = PhoneNormalizer.clean_digits(raw_data.get("caller_id_number") or raw_data.get("caller_id") or "")
    from backend.app.services.cti_service import VID_EMPLOYEE_MAP
    is_outbound = direction_hint in ["clicktocall", "outbound", "outgoing"] or clean_vid in VID_EMPLOYEE_MAP

    if is_cdr:
        return await smartflo_cdr_callback(request, db)
    elif is_outbound:
        return await smartflo_outbound_screenpop(request, db)
    else:
        return await smartflo_incoming_webhook(request, db)

@router.api_route("/smartflo/cdr", methods=["GET", "POST"])
@router.api_route("/smartflo/status", methods=["GET", "POST"])
async def smartflo_cdr_callback(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Tata Smartflo Call Disconnect & CDR Logging Webhook.
    Configure this URL in Tata Smartflo Portal for Call Hangup / Disconnect events:
    https://<ngrok-or-domain>/api/calls/smartflo/cdr
    
    Captures: uuid, call_id, start_stamp, end_stamp, duration/billsec, recording_url,
              hangup_cause, reason_key, hangup_code, hangup_key, agent, agent_number.
    Automatically updates call record, stops live timer, and saves recording to customer timeline.
    """
    raw_data = await _extract_request_data(request)
    logger.info(f"[SMARTFLO CDR CALLBACK RECEIVED] Data: {raw_data}")

    call_uuid = raw_data.get("uuid") or raw_data.get("call_uuid") or raw_data.get("session_id")
    call_id = raw_data.get("call_id") or raw_data.get("callid") or raw_data.get("CallSid") or call_uuid
    lookup_key = str(call_uuid or call_id or "").strip()

    # Search for existing call record by uuid, call_id, or caller number within recent timeframe
    call = None
    if lookup_key:
        call = db.query(Call).filter(
            (Call.call_id == lookup_key) | 
            (Call.uuid == lookup_key) |
            (Call.call_id == str(call_id).strip()) |
            (Call.uuid == str(call_uuid).strip())
        ).first()

    clean_vid = PhoneNormalizer.clean_digits(raw_data.get("caller_id_number") or raw_data.get("caller_id") or "")
    from backend.app.services.cti_service import VID_EMPLOYEE_MAP
    direction_hint = str(raw_data.get("direction", "")).lower()
    is_outbound_dir = (
        direction_hint in ["clicktocall", "outbound", "outgoing"] or
        clean_vid in VID_EMPLOYEE_MAP
    )

    if is_outbound_dir:
        raw_phone = (
            raw_data.get("call_to_number")
            or raw_data.get("customer_no_with_prefix ")
            or raw_data.get("customer_no_with_prefix")
            or raw_data.get("customer_number_with_prefix")
            or raw_data.get("phone_number")
            or raw_data.get("caller_number")
            or ""
        )
    else:
        raw_phone = (
            raw_data.get("caller_number")
            or raw_data.get("caller_id_number")
            or raw_data.get("customer_no_with_prefix ")
            or raw_data.get("customer_no_with_prefix")
            or raw_data.get("customer_number_with_prefix")
            or raw_data.get("phone_number")
            or ""
        )
    clean_phone = str(raw_phone).strip()
    norm_phone = PhoneNormalizer.normalize(clean_phone) if clean_phone else ""

    # Guard: If webhook has NO phone number and NO call UUID (e.g. blank test probe, crawler, or healthcheck ping), ignore it without creating dummy 0s call records
    if not lookup_key and not clean_phone:
        logger.warning("[SMARTFLO CDR] Ignored empty probe webhook without call identifier or phone number.")
        return {"status": "ok", "message": "Ignored empty probe webhook without call data"}

    if not call and norm_phone:
        # Fallback search by normalized phone within recent timeframe
        call = (
            db.query(Call)
            .filter(
                (Call.phone_number_normalized == norm_phone) |
                (Call.call_to_number == clean_phone)
            )
            .order_by(desc(Call.start_time))
            .first()
        )

    raw_status = str(
        raw_data.get("call_status")
        or raw_data.get("status")
        or raw_data.get("hangup_cause")
        or "completed"
    ).lower()

    # Parse Duration & Billsec
    duration_str = (
        raw_data.get("duration")
        or raw_data.get("talk_time")
        or raw_data.get("billsec")
        or raw_data.get("duration_seconds")
        or "0"
    )
    # Extract digits if string contains "24 sec" or "24s"
    import re
    digits = re.findall(r'\d+', str(duration_str))
    duration_secs = int(digits[0]) if digits else 0

    billsec_str = raw_data.get("billsec") or str(duration_secs)
    b_digits = re.findall(r'\d+', str(billsec_str))
    billsec_secs = int(b_digits[0]) if b_digits else duration_secs

    # Parse Recording URL
    recording_url = (
        raw_data.get("recording_url")
        or raw_data.get("audio_url")
        or raw_data.get("record_path")
        or raw_data.get("recording")
        or raw_data.get("RecordingUrl")
    )

    # Parse Smartflo specific hangup reasons
    hangup_cause = raw_data.get("hangup_cause") or raw_data.get("Hangup-Cause")
    reason_key = raw_data.get("reason_key") or raw_data.get("Reason-Key")
    hangup_code = raw_data.get("hangup_code") or raw_data.get("Hangup-Code")
    hangup_key = raw_data.get("hangup_key") or raw_data.get("Hangup-Key")
    agent_name = raw_data.get("agent") or raw_data.get("agent_name")
    agent_number = raw_data.get("agent_number") or raw_data.get("agent_phone")
    operator_val = raw_data.get("operator") or raw_data.get("billing_circle")
    circle_val = raw_data.get("circle") or raw_data.get("billing_circle")

    # Determine final CRM status
    if any(k in raw_status for k in ["no_answer", "no answer", "miss", "drop", "no user", "cancel", "busy", "reject", "fail", "no_user_response", "originate_failed", "unallocated"]):
        final_status = "missed"
    elif billsec_secs > 0 or duration_secs > 0 or raw_status in ["answered", "completed", "success", "answer"]:
        final_status = "completed"
    else:
        final_status = raw_status

    # Parse End Stamp (Smartflo sends in Indian Standard Time IST UTC+05:30)
    end_stamp_str = raw_data.get("end_stamp") or raw_data.get("end_time")
    end_dt = parse_smartflo_timestamp(end_stamp_str)

    if not call:
        # Create completed Call record directly from CDR metadata
        from backend.app.services.search_service import SearchService
        cust_match = None
        if norm_phone:
            cust_match = SearchService.lookup_by_phone(db, clean_phone)

        clean_vid = PhoneNormalizer.clean_digits(raw_data.get("caller_id_number") or raw_data.get("caller_id") or "")
        from backend.app.services.cti_service import VID_EMPLOYEE_MAP
        vid_info = VID_EMPLOYEE_MAP.get(clean_vid) or {}
        resolved_agent = agent_name or vid_info.get("name")
        resolved_email = vid_info.get("email")
        db_user = None
        if resolved_email:
            db_user = db.query(User).filter(User.email == resolved_email).first()

        dir_val = "outgoing" if (
            str(raw_data.get("direction", "")).lower() in ["clicktocall", "outbound", "outgoing"] or
            clean_vid in VID_EMPLOYEE_MAP
        ) else "incoming"

        start_stamp_str = raw_data.get("start_stamp")
        start_dt = parse_smartflo_timestamp(start_stamp_str) if start_stamp_str else end_dt

        call_id_final = call_id or f"SF-CDR-{__import__('uuid').uuid4().hex[:10].upper()}"
        call = Call(
            call_id=call_id_final,
            uuid=call_uuid or call_id_final,
            customer_id=cust_match.id if cust_match else None,
            user_id=db_user.id if db_user else None,
            phone_number=clean_phone or "Unknown",
            phone_number_normalized=norm_phone or "",
            call_to_number=clean_phone or "",
            agent_name=resolved_agent,
            agent_number=agent_number or clean_vid,
            direction=dir_val,
            status=final_status,
            provider="smartflo",
            start_time=start_dt,
            duration_seconds=duration_secs,
            billsec=billsec_secs,
            recording_url=str(recording_url) if recording_url else None,
            end_time=end_dt
        )
        db.add(call)
        db.commit()
        db.refresh(call)

    if call:
        if call_uuid and not call.uuid:
            call.uuid = str(call_uuid)
        call.status = final_status
        call.duration_seconds = duration_secs
        call.billsec = billsec_secs
        if is_outbound_dir:
            call.direction = "outgoing"
        if recording_url:
            call.recording_url = str(recording_url)
        if hangup_cause:
            call.hangup_cause = str(hangup_cause)
        if reason_key:
            call.reason_key = str(reason_key)
        if hangup_code:
            call.hangup_code = str(hangup_code)
        if hangup_key:
            call.hangup_key = str(hangup_key)
        if agent_name:
            call.agent_name = str(agent_name)
        if agent_number:
            call.agent_number = str(agent_number)
        if operator_val and not call.operator:
            call.operator = str(operator_val)
        if circle_val and not call.circle:
            call.circle = str(circle_val)

        # Build informative hangup notes
        note_parts = []
        if hangup_cause:
            note_parts.append(f"Hangup: {hangup_cause}")
        if reason_key:
            note_parts.append(f"Reason: {reason_key}")
        if hangup_code:
            note_parts.append(f"Code: {hangup_code}")
        if hangup_key:
            note_parts.append(f"Key: {hangup_key}")
        if agent_name:
            note_parts.append(f"Agent: {agent_name}")
        call.notes = " | ".join(note_parts) if note_parts else call.notes

        # If linked to customer, write or update interaction timeline (strictly deduplicated)
        if call.customer_id:
            call_dir_label = "Outgoing" if call.direction == "outgoing" else "Inbound"
            duration_mins = f"{duration_secs // 60:02d}:{duration_secs % 60:02d}"
            
            existing_inters = (
                db.query(CustomerInteraction)
                .filter(
                    CustomerInteraction.customer_id == call.customer_id,
                    CustomerInteraction.interaction_type == "call"
                )
                .all()
            )
            matched_inter = None
            for ci in existing_inters:
                meta = ci.meta_info or {}
                if meta.get("call_id") == call.call_id or (call.uuid and meta.get("uuid") == call.uuid):
                    matched_inter = ci
                    break

            new_meta = {
                "call_id": call.call_id,
                "uuid": call.uuid,
                "direction": call.direction,
                "duration": duration_mins,
                "duration_seconds": duration_secs,
                "billsec": billsec_secs,
                "recording_url": str(recording_url or call.recording_url or "") or None,
                "phone": call.phone_number,
                "hangup_cause": hangup_cause,
                "reason_key": reason_key,
                "hangup_code": hangup_code,
                "hangup_key": hangup_key,
                "agent_name": agent_name or call.agent_name,
                "provider": "smartflo"
            }

            if matched_inter:
                matched_inter.subject = f"Tata Smartflo {call_dir_label} Call ({final_status.title()})"
                matched_inter.content = f"Call completed via Tata Smartflo. Duration: {duration_mins} ({duration_secs}s). {call.notes or ''}"
                matched_inter.meta_info = new_meta
                matched_inter.direction = call.direction
            else:
                interaction = CustomerInteraction(
                    customer_id=call.customer_id,
                    user_id=call.user_id,
                    interaction_type="call",
                    direction=call.direction,
                    subject=f"Tata Smartflo {call_dir_label} Call ({final_status.title()})",
                    content=f"Call completed via Tata Smartflo. Duration: {duration_mins} ({duration_secs}s). {call.notes or ''}",
                    meta_info=new_meta,
                    interaction_time=call.start_time
                )
                db.add(interaction)

        db.commit()

        # Remove from active calls and broadcast call_ended event to frontend
        broadcast_manager.remove_active_call(call.call_id)
        if call.uuid:
            broadcast_manager.remove_active_call(call.uuid)

        end_event = {
            "event": "call_ended",
            "call_id": call.call_id,
            "uuid": call.uuid,
            "phone_number": call.phone_number,
            "status": final_status,
            "direction": call.direction or "outgoing",
            "duration_seconds": duration_secs,
            "billsec": billsec_secs,
            "recording_url": recording_url,
            "hangup_cause": hangup_cause,
            "reason_key": reason_key,
            "hangup_code": hangup_code,
            "hangup_key": hangup_key,
            "agent_name": agent_name or call.agent_name,
            "virtual_did": clean_vid or call.agent_number,
            "user_id": call.user_id,
            "customer_found": bool(call.customer_id),
            "customer_id": call.customer_id,
            "operator": call.operator,
            "circle": call.circle,
            "timestamp": end_dt.isoformat()
        }
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(broadcast_manager.broadcast_call(end_event))
        except RuntimeError:
            pass

    return {
        "status": "ok",
        "call_id": call.call_id if call else lookup_key,
        "uuid": call_uuid,
        "call_status": final_status,
        "updated_status": final_status,
        "duration_seconds": duration_secs,
        "billsec": billsec_secs,
        "hangup_cause": hangup_cause,
        "reason_key": reason_key
    }

# ---------------------------------------------------------------------------
# OUTBOUND WEBHOOKS — Triggered when agent calls from Smartflo Connect App
# ---------------------------------------------------------------------------

@router.api_route("/smartflo/outbound", methods=["GET", "POST"])
async def smartflo_outbound_screenpop(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Tata Smartflo Outbound Call Screen-Pop Webhook.
    Fires when an agent makes a call FROM Smartflo Connect App (VID outbound).
    Trigger: "Call answered by Agent" / "Call Start"
    URL: https://<ngrok>/api/calls/smartflo/outbound

    Payload fields:
      uuid, call_to_number, caller_id_number, start_stamp,
      answer_agent_number, call_id, billing_circle, call_status, direction,
      customer_no_with_prefix, ref_id
    """
    raw_data = await _extract_request_data(request)
    logger.info(f"[SMARTFLO OUTBOUND SCREENPOP] Data: {raw_data}")

    # --- Extract fields from Smartflo outbound payload ---
    call_uuid    = str(raw_data.get("uuid") or raw_data.get("ref_id") or "").strip()
    call_id_raw  = str(raw_data.get("call_id") or call_uuid).strip()
    vid          = str(
        raw_data.get("caller_id_number") or
        raw_data.get("caller_id") or ""
    ).strip()
    # Destination = customer's number
    customer_phone = str(
        raw_data.get("call_to_number") or
        raw_data.get("customer_no_with_prefix ") or     # note trailing space in Smartflo payload key
        raw_data.get("customer_no_with_prefix") or
        raw_data.get("customer_number_with_prefix") or ""
    ).strip()

    agent_phone  = str(raw_data.get("answered_agent_number") or raw_data.get("answer_agent_number") or vid).strip()
    ref_id       = str(raw_data.get("ref_id") or "").strip()
    billing_circle = str(raw_data.get("billing_circle") or "").strip()

    if not customer_phone:
        logger.warning("[SMARTFLO OUTBOUND SCREENPOP] No customer phone in payload")
        return {"status": "ok", "message": "No customer number in outbound payload", "data": raw_data}

    clean_customer = PhoneNormalizer.clean_digits(customer_phone)
    norm_customer  = PhoneNormalizer.normalize(customer_phone)
    clean_vid      = PhoneNormalizer.clean_digits(vid)

    # --- Resolve employee from VID ---
    from backend.app.services.cti_service import VID_EMPLOYEE_MAP
    vid_info    = VID_EMPLOYEE_MAP.get(clean_vid) or VID_EMPLOYEE_MAP.get(vid) or {}
    agent_name  = vid_info.get("name", "Agent")
    agent_email = vid_info.get("email", "")

    # Resolve DB user from VID/email
    db_user = None
    if agent_email:
        db_user = db.query(User).filter(User.email == agent_email).first()
    if not db_user and clean_vid:
        db_user = db.query(User).filter(
            (User.allowed_caller_id == clean_vid) |
            (User.allowed_caller_id == vid)
        ).first()

    # --- Customer lookup ---
    customer = None
    from backend.app.services.search_service import SearchService
    if clean_customer:
        customer = SearchService.lookup_by_phone(db, clean_customer)

    # --- Create or update Call record ---
    call = db.query(Call).filter(
        (Call.call_id == call_id_raw) | (Call.uuid == call_uuid) | (Call.uuid == ref_id)
    ).first()

    now_dt = datetime.now(timezone.utc)

    if not call:
        call_id_final = call_id_raw or f"SF-OUT-{call_uuid[:12]}" if call_uuid else f"SF-OUT-{__import__('uuid').uuid4().hex[:10].upper()}"
        call = Call(
            call_id=call_id_final,
            uuid=call_uuid or call_id_final,
            customer_id=customer.id if customer else None,
            user_id=db_user.id if db_user else None,
            phone_number=clean_customer,
            phone_number_normalized=norm_customer,
            call_to_number=clean_customer,
            agent_name=agent_name,
            agent_number=clean_vid or agent_phone,
            direction="outgoing",
            status="ringing",
            provider="smartflo",
            start_time=now_dt,
            duration_seconds=0,
            operator=billing_circle or None
        )
        db.add(call)
        db.commit()
        db.refresh(call)
        logger.info(f"[SMARTFLO OUTBOUND] New outbound call record created: {call.call_id} → {clean_customer}")
    else:
        call.direction = "outgoing"
        call.status = "ringing"
        if not call.customer_id and customer:
            call.customer_id = customer.id
        db.commit()

    # --- Build customer summary for 360° Screen-Pop ---
    from backend.app.schemas.customer import CustomerSearchOut
    cust_out = None
    if customer:
        cust_out = CustomerSearchOut(
            id=customer.id,
            party_code=customer.party_code,
            party_name=customer.party_name,
            contact_person_1=customer.contact_person_1,
            email_id_1=customer.email_id_1,
            city=customer.city,
            state=customer.state,
            phone_1=customer.phone_1,
            phone_1_normalized=customer.phone_1_normalized,
            status=customer.status,
            assigned_employee_name=customer.assigned_employee.full_name if customer.assigned_employee else None,
            match_type="outgoing_call"
        ).model_dump()

    # --- Broadcast real-time SSE screen-pop ---
    broadcast_payload = {
        "event": "outgoing_call",
        "call_id": call.call_id,
        "uuid": call.uuid,
        "call_to_number": clean_customer,
        "phone_number": clean_customer,
        "phone_number_normalized": norm_customer,
        "caller_phone": clean_vid,
        "caller_id": clean_vid,
        "vid": clean_vid,
        "direction": "outgoing",
        "customer_found": customer is not None,
        "customer": cust_out,
        "agent_user_id": db_user.id if db_user else None,
        "agent_name": agent_name,
        "assigned_employee_name": agent_name,
        "start_time": now_dt.isoformat(),
        "timestamp": now_dt.isoformat(),
        "created_timestamp": now_dt.timestamp(),
        "status": "ringing",
        "provider": "smartflo",
        "ref_id": ref_id,
        "source": "smartflo_connect_app"
    }

    broadcast_manager.add_active_call(call.uuid, broadcast_payload)
    broadcast_manager.add_active_call(call.call_id, broadcast_payload)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast_manager.broadcast_call(broadcast_payload))
    except RuntimeError:
        pass

    logger.info(f"[SMARTFLO OUTBOUND SCREENPOP] Broadcast sent → Customer: {customer.party_name if customer else clean_customer} | VID: {clean_vid} | Agent: {agent_name}")

    return {
        "status": "ok",
        "call_id": call.call_id,
        "uuid": call.uuid,
        "customer_phone": clean_customer,
        "vid": clean_vid,
        "agent": agent_name,
        "customer_found": customer is not None,
        "customer_name": customer.party_name if customer else None
    }


@router.api_route("/smartflo/outbound-cdr", methods=["GET", "POST"])
async def smartflo_outbound_cdr(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Tata Smartflo Outbound CDR Webhook — fires on call hangup for outbound calls.
    Trigger: "Call hangup (Missed or Answered)" — Outbound
    URL: https://<ngrok>/api/calls/smartflo/outbound-cdr

    Records call duration, status, recording URL, agent info into the DB
    and broadcasts call_ended event to frontend to auto-dismiss call card.
    """
    raw_data = await _extract_request_data(request)
    logger.info(f"[SMARTFLO OUTBOUND CDR] Data: {raw_data}")

    # Delegate to the same CDR handler — logic is identical for inbound and outbound CDR
    return await smartflo_cdr_callback(request, db)


@router.get("/events")
async def call_events_sse(request: Request):
    """
    Server-Sent Events (SSE) stream for live CTI Screen Pop & Multi-Call updates.
    Clients connect here to receive real-time incoming call events instantaneously.
    """
    async def event_generator():
        q = broadcast_manager.subscribe()
        try:
            # Send initial connected heartbeat
            yield f"data: {json.dumps({'event': 'connected', 'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"
            while True:
                # Check for client disconnect
                if await request.is_disconnected():
                    break
                try:
                    # Wait for next call event with 15s heartbeat timeout
                    call_event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(call_event)}\n\n"
                except asyncio.TimeoutError:
                    # Send keep-alive heartbeat
                    yield f": heartbeat {datetime.now(timezone.utc).isoformat()}\n\n"
        finally:
            broadcast_manager.unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.get("/active")
def get_active_ringing_calls(
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """
    Returns currently ringing / active calls filtered by user role & Allowed Caller ID:
    - Admin sees all active calls across all Smartflo Allowed Caller IDs.
    - Employee sees only active calls routed to their Allowed Caller ID / assigned user ID.
    """
    is_admin = current_user.role == "admin" if current_user else True
    user_id = current_user.id if current_user else None
    user_cid = (current_user.allowed_caller_id or current_user.vid) if current_user else None

    active_calls = broadcast_manager.get_all_active_calls(
        user_id=user_id,
        allowed_caller_id=user_cid,
        is_admin=is_admin,
        max_age_seconds=120
    )
    return {
        "has_active_call": len(active_calls) > 0,
        "active_calls": active_calls,
        "active_call": active_calls[0] if active_calls else None
    }

class DismissCallRequest(BaseModel):
    call_id: Optional[str] = None
    uuid: Optional[str] = None

@router.post("/dismiss")
@router.post("/active/dismiss")
def dismiss_active_call_endpoint(req: DismissCallRequest):
    """Dismiss a call card from the active in-memory cache so it stops popping up."""
    key = req.uuid or req.call_id
    if key:
        broadcast_manager.remove_active_call(key)
    if req.call_id:
        broadcast_manager.remove_active_call(req.call_id)
    if req.uuid:
        broadcast_manager.remove_active_call(req.uuid)
    return {"status": "dismissed", "key": key}

@router.post("/incoming", response_model=IncomingCallResponse)
def incoming_call_webhook(
    payload: IncomingCallWebhook,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """
    Standard Telephony Webhook Endpoint.
    Triggered by PBX/SIP/Twilio/Exotel or frontend simulator when a call arrives.
    """
    response = CTIService.handle_incoming_call(
        db=db,
        incoming=payload,
        agent_user_id=current_user.id if current_user else None
    )
    return response

@router.post("/simulate", response_model=IncomingCallResponse)
def simulate_incoming_call(
    payload: IncomingCallWebhook,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Interactive live incoming call simulator for testing the employee call screen.
    """
    response = CTIService.handle_incoming_call(
        db=db,
        incoming=payload,
        agent_user_id=current_user.id
    )
    return response

@router.post("/outgoing")
def initiate_outgoing_call(
    req: OutgoingCallRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Initiate an outbound call to a customer using Tata Smartflo / configured VID.
    Strictly enforces Allowed Caller ID / VID mapping:
    - Normal staff are strictly restricted to their mapped VID.
    - Admin can call using their VID or specified VID.
    """
    if not req.phone_number or len(req.phone_number.strip()) < 3:
        raise HTTPException(status_code=400, detail="A valid phone number is required")

    return CTIService.handle_outgoing_call(
        db=db,
        to_number=req.phone_number,
        current_user=current_user,
        requested_vid=req.vid,
        customer_id=req.customer_id,
        notes=req.notes,
        provider_name=req.provider or "smartflo"
    )

@router.post("/status")
def update_call_status(
    status_update: CallStatusUpdate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """Update call status (completed, missed, duration, recording URL, notes)."""
    call = db.query(Call).filter(Call.call_id == status_update.call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call record not found")

    call.status = status_update.status
    if status_update.duration_seconds is not None:
        call.duration_seconds = status_update.duration_seconds
    if status_update.recording_url:
        call.recording_url = status_update.recording_url
    elif not call.recording_url:
        # Default sample recording playback link for testing and verification
        call.recording_url = "https://actions.google.com/sounds/v1/telephones/telephone_ring.ogg"
    if status_update.notes:
        call.notes = status_update.notes
    call.end_time = datetime.now(timezone.utc)

    # If call was completed with notes and linked to a customer, create interaction
    if call.customer_id and (status_update.status == "completed" or status_update.notes):
        duration_mins = f"{call.duration_seconds // 60:02d}:{call.duration_seconds % 60:02d}"
        interaction = CustomerInteraction(
            customer_id=call.customer_id,
            user_id=call.user_id or (current_user.id if current_user else None),
            interaction_type="call",
            direction=call.direction,
            subject=f"{call.direction.title()} Call ({call.status.title()})",
            content=call.notes or f"Call duration: {duration_mins}",
            meta_info={
                "call_id": call.call_id,
                "duration": duration_mins,
                "duration_seconds": call.duration_seconds,
                "recording_url": call.recording_url,
                "phone": call.phone_number
            },
            interaction_time=call.start_time
        )
        db.add(interaction)

    if status_update.notes:
        AuditService.log(
            db,
            action="CALL_NOTE_SAVED",
            entity_type="call",
            entity_id=str(call.call_id or call.id),
            changes={"notes": status_update.notes, "status": call.status},
            user=current_user or (call.user if hasattr(call, 'user') and call.user else None)
        )

    db.commit()

    # Remove from active calls cache so active pollers immediately drop the ringing state
    broadcast_manager.remove_active_call(call.call_id)
    if call.uuid:
        broadcast_manager.remove_active_call(call.uuid)

    return {"status": "updated", "call_id": call.call_id, "call_status": call.status}

@router.get("/export")
def export_calls_report(
    format: str = Query("xlsx", description="xlsx or csv"),
    date_filter: str = Query("all", description="all, today, week, month, custom"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD for custom filter"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD for custom filter"),
    employee_id: Optional[int] = Query(None, description="Specific employee ID to filter (admin only)"),
    direction: Optional[str] = Query(None, description="all, incoming, outgoing, missed"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Export complete Call Logs & Telephony History to Excel (.xlsx) or CSV (.csv).
    Includes role-based filtering, date presets, custom date range, accurate IST times,
    and clickable audio recording links.
    """
    from backend.app.services.excel_service import ExcelService
    from datetime import timezone, timedelta
    
    query = db.query(Call).options(joinedload(Call.customer), joinedload(Call.user))

    # RBAC: Employee only exports calls routed to their Allowed Caller ID or assigned user ID
    if current_user.role == "employee":
        user_cid = current_user.allowed_caller_id or current_user.vid
        if user_cid:
            norm_cid = user_cid.replace("+", "").lstrip("0")
            query = query.filter(
                or_(
                    Call.user_id == current_user.id,
                    Call.call_to_number == user_cid,
                    Call.call_to_number.like(f"%{norm_cid[-10:]}"),
                    Call.agent_number == user_cid,
                    Call.agent_number.like(f"%{norm_cid[-10:]}")
                )
            )
        else:
            query = query.filter(Call.user_id == current_user.id)
    elif employee_id:
        target_user = db.query(User).filter(User.id == employee_id).first()
        if target_user:
            t_cid = target_user.allowed_caller_id or target_user.vid
            if t_cid:
                norm_t = t_cid.replace("+", "").lstrip("0")
                query = query.filter(
                    or_(
                        Call.user_id == target_user.id,
                        Call.call_to_number == t_cid,
                        Call.call_to_number.like(f"%{norm_t[-10:]}"),
                        Call.agent_number == t_cid,
                        Call.agent_number.like(f"%{norm_t[-10:]}")
                    )
                )
            else:
                query = query.filter(Call.user_id == target_user.id)

    # Direction filter
    if direction and direction != "all":
        if direction == "missed":
            query = query.filter(Call.status == "missed")
        else:
            query = query.filter(Call.direction == direction)

    # Date filter
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if date_filter == "today":
        query = query.filter(Call.start_time >= today_start)
    elif date_filter == "week":
        week_start = today_start - timedelta(days=now.weekday())
        query = query.filter(Call.start_time >= week_start)
    elif date_filter == "month":
        month_start = today_start.replace(day=1)
        query = query.filter(Call.start_time >= month_start)
    elif date_filter == "custom":
        if start_date:
            try:
                s_dt = datetime.strptime(start_date.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                query = query.filter(Call.start_time >= s_dt)
            except Exception:
                pass
        if end_date:
            try:
                e_dt = datetime.strptime(end_date.strip(), "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
                query = query.filter(Call.start_time <= e_dt)
            except Exception:
                pass

    calls = query.order_by(desc(Call.start_time)).all()

    timestamp_slug = datetime.now().strftime("%Y%m%d_%H%M%S")
    emp_slug = "all_team"
    if current_user.role == "employee":
        emp_slug = current_user.full_name.replace(" ", "_").lower()
    elif employee_id:
        target_user = db.query(User).filter(User.id == employee_id).first()
        if target_user:
            emp_slug = target_user.full_name.replace(" ", "_").lower()

    if format.lower() == "csv":
        csv_bytes = ExcelService.generate_call_logs_csv_bytes(calls)
        filename = f"Call_Logs_{emp_slug}_{timestamp_slug}.csv"
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "text/csv; charset=utf-8"
            }
        )
    else:
        excel_bytes = ExcelService.generate_call_logs_excel_bytes(calls)
        filename = f"Call_Logs_{emp_slug}_{timestamp_slug}.xlsx"
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            }
        )

@router.get("", response_model=List[CallOut])
def list_calls(
    customer_id: Optional[int] = None,
    user_id: Optional[int] = None,
    direction: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch call history logs with role-based access isolation."""
    query = db.query(Call).options(joinedload(Call.customer), joinedload(Call.user))

    # RBAC: Employee only sees calls routed to their Allowed Caller ID, initiated by them, or assigned to them
    if current_user.role == "employee":
        user_cid = current_user.allowed_caller_id or current_user.vid
        conditions = [Call.user_id == current_user.id]
        if user_cid:
            norm_cid = user_cid.replace("+", "").lstrip("0")
            conditions.extend([
                Call.call_to_number == user_cid,
                Call.call_to_number.like(f"%{norm_cid[-10:]}"),
                Call.agent_number == user_cid,
                Call.agent_number.like(f"%{norm_cid[-10:]}")
            ])
        if current_user.full_name:
            conditions.append(Call.agent_name.ilike(f"%{current_user.full_name}%"))
        query = query.filter(or_(*conditions))
    elif user_id:
        query = query.filter(Call.user_id == user_id)

    if customer_id:
        query = query.filter(Call.customer_id == customer_id)
    if direction:
        query = query.filter(Call.direction == direction)

    calls = query.order_by(desc(Call.start_time)).limit(limit).all()
    return [CallOut.model_validate(c) for c in calls]

@router.post("/clear-test-logs")
@router.delete("/clear-test-logs")
def clear_test_call_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Safely clear test/simulated call logs from the database.
    IMPORTANT: Real customer call history, customers, and agent profiles are 100% PRESERVED.
    """
    from sqlalchemy import or_

    # Identify test call logs (is_test is True, starts with TEST-/SIM-, or synthetic probe logs starting with SF-CDR-)
    test_calls_query = db.query(Call).filter(
        or_(
            Call.is_test == True,
            Call.call_id.like("TEST-%"),
            Call.call_id.like("SIM-%"),
            Call.call_id.like("SF-CDR-%")
        )
    )
    deleted_calls_count = test_calls_query.delete(synchronize_session=False)

    # Real calls count remaining intact
    preserved_count = db.query(Call).count()

    # Also clean in-memory active call state if simulated
    broadcast_manager.clear_active_call()

    db.commit()

    AuditService.log(
        db,
        action="TEST_CALL_LOGS_CLEARED",
        entity_type="call",
        changes={"deleted_test_calls": deleted_calls_count, "preserved_real_calls": preserved_count},
        user=current_user
    )

    logger.info(f"Cleared {deleted_calls_count} test call records. {preserved_count} real customer calls preserved.")
    return {
        "status": "success",
        "cleared_count": deleted_calls_count,
        "preserved_count": preserved_count,
        "message": f"Successfully cleared {deleted_calls_count} test call log(s). {preserved_count} real customer call(s) preserved intact."
    }

class UpdateTokenRequest(BaseModel):
    token: str
    token_name: Optional[str] = "CRM Outbound ClickToCall"

@router.get("/token-status")
def get_smartflo_token_status(
    current_user: User = Depends(get_current_user)
):
    """Fetch current Smartflo Call API token metadata, masked token, expiry status, and 10-day warning."""
    from backend.app.services.token_service import SmartfloTokenService
    meta = SmartfloTokenService.get_token_metadata()
    if current_user.role != "admin":
        meta["raw_token"] = meta["masked_token"]
    return meta

@router.post("/update-token")
def update_smartflo_token(
    req: UpdateTokenRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Admin-only: Update the Smartflo Call API Bearer Token and re-calculate expiry metadata."""
    from backend.app.services.token_service import SmartfloTokenService
    try:
        updated_meta = SmartfloTokenService.update_token(req.token, req.token_name)
        AuditService.log(
            db,
            action="SMARTFLO_TOKEN_UPDATED",
            entity_type="system_config",
            entity_id=None,
            changes={
                "token_name": updated_meta["token_name"],
                "masked_token": updated_meta["masked_token"],
                "expiry": updated_meta["expiry_formatted"],
                "days_left": updated_meta["days_left_int"]
            },
            user=admin_user
        )
        return {
            "status": "success",
            "message": f"Tata Smartflo Call API Token updated successfully! Valid until {updated_meta['expiry_formatted']}.",
            "token": updated_meta
        }
    except Exception as e:
        logger.error(f"Failed to update Smartflo API Token: {e}")
        raise HTTPException(status_code=400, detail=str(e))

def _range_file_response(request: Request, file_path: str) -> Response:
    """Helper to serve audio files with HTTP 206 Partial Content (Range) for fast seeking."""
    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("range")
    content_type = "audio/mpeg"

    if not range_header:
        def iter_full():
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk

        return StreamingResponse(
            iter_full(),
            status_code=200,
            headers={
                "Content-Type": content_type,
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=604800, immutable",
                "Access-Control-Allow-Origin": "*"
            }
        )

    # Parse Range: bytes=start-end
    try:
        range_str = range_header.replace("bytes=", "").strip()
        parts = range_str.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
        start = max(0, min(start, file_size - 1))
        end = max(start, min(end, file_size - 1))
        chunk_len = end - start + 1

        def iter_range():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = chunk_len
                while remaining > 0:
                    read_bytes = min(remaining, 64 * 1024)
                    data = f.read(read_bytes)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            iter_range(),
            status_code=206,
            headers={
                "Content-Type": content_type,
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(chunk_len),
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=604800, immutable",
                "Access-Control-Allow-Origin": "*"
            }
        )
    except Exception:
        return FileResponse(file_path, media_type=content_type)

@router.get("/recording-stream")
@router.get("/recording-proxy")
async def stream_call_recording(
    request: Request,
    url: Optional[str] = Query(None),
    call_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    High-Performance Audio Streaming & Caching Proxy for Inbound and Outbound Call Recordings.
    - Caches recordings locally on first play for 0-second instant replay.
    - Supports HTTP 206 Partial Content (Range requests) for lightning-fast seeking and scrubbing.
    - Eliminates remote Smartflo SSL / CORS / handshake buffering delays.
    """
    target_url = (url or "").strip()
    if not target_url and call_id:
        call_obj = db.query(Call).filter(or_(Call.call_id == call_id, Call.uuid == call_id)).first()
        if call_obj and call_obj.recording_url:
            target_url = call_obj.recording_url.strip()

    if not target_url:
        raise HTTPException(status_code=400, detail="Recording URL or valid call_id is required.")

    # 1. Check local cache
    url_hash = hashlib.md5(target_url.encode("utf-8")).hexdigest()
    cache_file = CACHE_DIR / f"{url_hash}.mp3"

    if cache_file.exists() and cache_file.stat().st_size > 512:
        return _range_file_response(request, str(cache_file))

    # 2. If not cached yet, fetch from remote with fast buffer & cache locally
    try:
        req = urllib.request.Request(
            target_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*"
            }
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            content = resp.read()
            if content and len(content) > 100:
                with open(cache_file, "wb") as f:
                    f.write(content)
                return _range_file_response(request, str(cache_file))
    except Exception as e:
        logger.warning(f"Failed to fetch remote audio from {target_url}: {e}")

    # Fallback if cache exists
    if cache_file.exists() and cache_file.stat().st_size > 0:
        return _range_file_response(request, str(cache_file))

    # If unreachable and target_url is valid, redirect directly
    return Response(status_code=307, headers={"Location": target_url})

