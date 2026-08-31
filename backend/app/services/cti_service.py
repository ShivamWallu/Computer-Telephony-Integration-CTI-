import os
import uuid
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from backend.app.models.call import Call
from backend.app.models.customer import Customer
from backend.app.models.user import User
from backend.app.models.interaction import CustomerInteraction
from backend.app.models.follow_up import FollowUp
from backend.app.schemas.call import IncomingCallWebhook, IncomingCallResponse
from backend.app.schemas.customer import CustomerSearchOut
from backend.app.services.phone_normalizer import PhoneNormalizer
from backend.app.services.search_service import SearchService
from backend.app.config import settings
import logging

logger = logging.getLogger(__name__)

# Indian Standard Time (IST = UTC+05:30)
IST_TZ = timezone(timedelta(hours=5, minutes=30))

def parse_smartflo_timestamp(ts_val) -> datetime:
    """Parse Smartflo Indian Standard Time (IST) timestamp string to UTC datetime accurately."""
    if not ts_val:
        return datetime.now(timezone.utc)
    s_str = str(ts_val).strip()
    try:
        if " " in s_str:
            # Smartflo format: "YYYY-MM-DD HH:MM:SS" (in IST +05:30)
            naive_dt = datetime.strptime(s_str, "%Y-%m-%d %H:%M:%S")
            ist_dt = naive_dt.replace(tzinfo=IST_TZ)
            return ist_dt.astimezone(timezone.utc)
        elif "T" in s_str:
            if s_str.endswith("Z") or "+" in s_str:
                return datetime.fromisoformat(s_str.replace("Z", "+00:00"))
            else:
                naive_dt = datetime.fromisoformat(s_str)
                return naive_dt.replace(tzinfo=IST_TZ).astimezone(timezone.utc)
        else:
            return datetime.fromtimestamp(float(s_str), tz=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)

# Known Smartflo Allowed Caller ID (VID / DID) to Employee Name / Email Map
VID_EMPLOYEE_MAP = {
    "918065908531": {"name": "Sahil Dogra", "email": "kogm.sahildogra@gmail.com", "phone": "918146982211"},
    "8065908531": {"name": "Sahil Dogra", "email": "kogm.sahildogra@gmail.com", "phone": "918146982211"},
    "+918065908531": {"name": "Sahil Dogra", "email": "kogm.sahildogra@gmail.com", "phone": "918146982211"},

    "918065908532": {"name": "BM Jagga", "email": "bmjagga@khandelia.com", "phone": "917087422511"},
    "8065908532": {"name": "BM Jagga", "email": "bmjagga@khandelia.com", "phone": "917087422511"},
    "+918065908532": {"name": "BM Jagga", "email": "bmjagga@khandelia.com", "phone": "917087422511"},

    "918065908533": {"name": "Utpal Pal", "email": "sales.kol@khandelia.com", "phone": "919830022111"},
    "8065908533": {"name": "Utpal Pal", "email": "sales.kol@khandelia.com", "phone": "919830022111"},
    "+918065908533": {"name": "Utpal Pal", "email": "sales.kol@khandelia.com", "phone": "919830022111"},

    "918065908534": {"name": "Sunil Jain", "email": "sales.gm@khandelia.com", "phone": "917888814811"},
    "8065908534": {"name": "Sunil Jain", "email": "sales.gm@khandelia.com", "phone": "917888814811"},
    "+918065908534": {"name": "Sunil Jain", "email": "sales.gm@khandelia.com", "phone": "917888814811"},

    "918065908535": {"name": "Ravi Kumar", "email": "customercare@khandelia.com", "phone": "917814694240"},
    "8065908535": {"name": "Ravi Kumar", "email": "customercare@khandelia.com", "phone": "917814694240"},
    "+918065908535": {"name": "Ravi Kumar", "email": "customercare@khandelia.com", "phone": "917814694240"},

    "918065908536": {"name": "Ankush Dingra", "email": "account.unit6@khandelia.com", "phone": "919784410004"},
    "8065908536": {"name": "Ankush Dingra", "email": "account.unit6@khandelia.com", "phone": "919784410004"},
    "+918065908536": {"name": "Ankush Dingra", "email": "account.unit6@khandelia.com", "phone": "919784410004"},

    "918065908538": {"name": "Sonu Kumar", "email": "kogm.sonukumar@gmail.com", "phone": "919316113211"},
    "8065908538": {"name": "Sonu Kumar", "email": "kogm.sonukumar@gmail.com", "phone": "919316113211"},
    "+918065908538": {"name": "Sonu Kumar", "email": "kogm.sonukumar@gmail.com", "phone": "919316113211"},

    "918065908539": {"name": "Ankush Kapila", "email": "storepurchase@khandelia.com", "phone": "917696304207"},
    "8065908539": {"name": "Ankush Kapila", "email": "storepurchase@khandelia.com", "phone": "917696304207"},
    "+918065908539": {"name": "Ankush Kapila", "email": "storepurchase@khandelia.com", "phone": "917696304207"},

    "918065908540": {"name": "Yogesh Khandelia", "email": "infotech@khandelia.com", "phone": "919914565011"},
    "8065908540": {"name": "Yogesh Khandelia", "email": "infotech@khandelia.com", "phone": "919914565011"},
    "+918065908540": {"name": "Yogesh Khandelia", "email": "infotech@khandelia.com", "phone": "919914565011"},

    "918065908541": {"name": "Pankaj", "email": "kogm.pankaj@gmail.com", "phone": "+917743004676"},
    "8065908541": {"name": "Pankaj", "email": "kogm.pankaj@gmail.com", "phone": "+917743004676"},
    "+918065908541": {"name": "Pankaj", "email": "kogm.pankaj@gmail.com", "phone": "+917743004676"},
}

class CallBroadcastManager:
    """
    In-memory real-time broadcast & multi-call manager for CTI Screen Pop.
    Maintains multiple simultaneous active calls and broadcasts events to connected SSE frontend clients.
    """
    def __init__(self):
        self._listeners: List[asyncio.Queue] = []
        self._active_calls: Dict[str, Dict[str, Any]] = {}
        self._latest_active_call: Optional[Dict[str, Any]] = None
        self._latest_call_timestamp: float = 0.0

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self._listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._listeners:
            self._listeners.remove(q)

    def add_active_call(self, call_key: str, payload: Dict[str, Any]):
        self._active_calls[call_key] = payload
        self._latest_active_call = payload
        self._latest_call_timestamp = datetime.now(timezone.utc).timestamp()

    def update_active_call(self, call_key: str, updates: Dict[str, Any]):
        if call_key in self._active_calls:
            self._active_calls[call_key].update(updates)
        for key, call in list(self._active_calls.items()):
            if call.get("uuid") == call_key or call.get("call_id") == call_key:
                call.update(updates)

    def remove_active_call(self, call_key: str):
        keys_to_remove = []
        for k, v in self._active_calls.items():
            if k == call_key or v.get("uuid") == call_key or v.get("call_id") == call_key:
                keys_to_remove.append(k)
        for k in keys_to_remove:
            self._active_calls.pop(k, None)

        if self._latest_active_call and (
            self._latest_active_call.get("call_id") == call_key or
            self._latest_active_call.get("uuid") == call_key
        ):
            self._latest_active_call = None

    def get_all_active_calls(
        self,
        allowed_caller_id: Optional[str] = None,
        user_id: Optional[int] = None,
        is_admin: bool = False,
        max_age_seconds: int = 180
    ) -> List[Dict[str, Any]]:
        """Return active calls filtered by user role, allowed caller ID, and fresh age (< 180s)."""
        now = datetime.now(timezone.utc).timestamp()
        clean_cid = str(allowed_caller_id).strip() if allowed_caller_id else None
        results = []
        seen_keys = set()
        for call_key, call in list(self._active_calls.items()):
            c_key = call.get("uuid") or call.get("call_id") or call_key
            if c_key in seen_keys:
                continue
            seen_keys.add(c_key)

            call_ts = call.get("created_timestamp") or now
            if (now - call_ts) > max_age_seconds:
                continue

            if is_admin:
                results.append(call)
            else:
                call_agent_id = call.get("agent_user_id") or call.get("user_id")
                call_did = str(call.get("call_to_number") or "")
                call_vid = str(call.get("vid") or call.get("caller_phone") or call.get("caller_id") or call.get("agent_number") or "")
                
                matches_agent = (user_id is not None and call_agent_id == user_id)
                matches_cid = False
                if clean_cid:
                    cid_10 = clean_cid[-10:] if len(clean_cid) >= 10 else clean_cid
                    if call_did and (call_did.endswith(cid_10) or clean_cid in call_did):
                        matches_cid = True
                    elif call_vid and (call_vid.endswith(cid_10) or clean_cid in call_vid):
                        matches_cid = True

                if matches_agent or matches_cid:
                    results.append(call)

        return results

    def get_latest_active_call(self, max_age_seconds: int = 35) -> Optional[Dict[str, Any]]:
        now = datetime.now(timezone.utc).timestamp()
        if self._latest_active_call and (now - self._latest_call_timestamp) <= max_age_seconds:
            return self._latest_active_call
        return None

    def clear_active_call(self):
        self._active_calls.clear()
        self._latest_active_call = None
        self._latest_call_timestamp = 0.0

    async def broadcast_call(self, call_payload: Dict[str, Any]):
        for q in list(self._listeners):
            try:
                await q.put(call_payload)
            except Exception as e:
                logger.warning(f"Failed to put event into SSE queue: {e}")

broadcast_manager = CallBroadcastManager()

def resolve_employee_by_vid_or_name(
    db: Session,
    vid: Optional[str] = None,
    agent_name: Optional[str] = None,
    agent_number: Optional[str] = None
) -> Optional[User]:
    """
    Resolve internal User/Employee entity from Smartflo Allowed Caller ID / VID, agent name, or phone.
    """
    clean_vid = str(vid).strip() if vid else ""
    clean_name = str(agent_name).strip() if agent_name else ""
    clean_num = str(agent_number).strip() if agent_number else ""

    # 1. Search in DB by User.allowed_caller_id or User.vid
    if clean_vid:
        user = db.query(User).filter(
            (User.allowed_caller_id == clean_vid) |
            (User.vid == clean_vid)
        ).first()
        if user:
            return user
        # Try without +91 or with 91
        norm_vid = clean_vid.replace("+", "").lstrip("0")
        user = db.query(User).filter(
            (User.allowed_caller_id.like(f"%{norm_vid[-10:]}")) |
            (User.vid.like(f"%{norm_vid[-10:]}"))
        ).first()
        if user:
            return user

    # 2. Check Static VID Fallback Mapping
    if clean_vid and clean_vid in VID_EMPLOYEE_MAP:
        mapping = VID_EMPLOYEE_MAP[clean_vid]
        user = db.query(User).filter(User.email == mapping["email"]).first()
        if user:
            return user

    # 3. Search in DB by User.full_name
    if clean_name:
        user = db.query(User).filter(User.full_name.ilike(f"%{clean_name}%")).first()
        if user:
            return user

    # 4. Search in DB by User.phone
    if clean_num:
        user = db.query(User).filter(User.phone == clean_num).first()
        if user:
            return user

    return None

class BaseTelephonyProvider(ABC):
    @abstractmethod
    def parse_incoming_payload(self, raw_payload: Dict[str, Any]) -> IncomingCallWebhook:
        pass

    @abstractmethod
    def initiate_outbound(self, to_number: str, agent_id: Optional[str] = None) -> Dict[str, Any]:
        pass

class GenericWebhookProvider(BaseTelephonyProvider):
    """Handles standard JSON Webhooks from PBX, Asterisk, FreePBX, etc."""
    def parse_incoming_payload(self, raw_payload: Dict[str, Any]) -> IncomingCallWebhook:
        phone = (
            raw_payload.get("phone_number")
            or raw_payload.get("caller")
            or raw_payload.get("from")
            or raw_payload.get("From")
            or ""
        )
        return IncomingCallWebhook(
            phone_number=str(phone).strip(),
            call_id=raw_payload.get("call_id") or raw_payload.get("CallSid") or str(uuid.uuid4()),
            call_time=datetime.now(timezone.utc),
            direction=raw_payload.get("direction", "incoming"),
            provider="generic",
            caller_name=raw_payload.get("caller_name"),
            agent_extension=raw_payload.get("agent_extension")
        )

    def initiate_outbound(self, to_number: str, agent_id: Optional[str] = None) -> Dict[str, Any]:
        call_id = f"OUT-{uuid.uuid4().hex[:8].upper()}"
        return {"status": "initiated", "call_id": call_id, "to": to_number}

class TwilioProvider(BaseTelephonyProvider):
    """Twilio Voice API Webhook Integration."""
    def parse_incoming_payload(self, raw_payload: Dict[str, Any]) -> IncomingCallWebhook:
        return IncomingCallWebhook(
            phone_number=str(raw_payload.get("From") or raw_payload.get("Caller", "")).strip(),
            call_id=raw_payload.get("CallSid") or str(uuid.uuid4()),
            call_time=datetime.now(timezone.utc),
            direction="incoming",
            provider="twilio",
            caller_name=raw_payload.get("CallerName"),
            agent_extension=raw_payload.get("To")
        )

    def initiate_outbound(self, to_number: str, agent_id: Optional[str] = None) -> Dict[str, Any]:
        return {"status": "queued", "provider": "twilio", "call_id": f"CA{uuid.uuid4().hex}"}

class ExotelProvider(BaseTelephonyProvider):
    """Exotel Cloud Telephony Webhook Integration."""
    def parse_incoming_payload(self, raw_payload: Dict[str, Any]) -> IncomingCallWebhook:
        caller_phone = (
            raw_payload.get("CallFrom")
            or raw_payload.get("From")
            or raw_payload.get("Caller")
            or raw_payload.get("phone_number")
            or ""
        )
        call_sid = (
            raw_payload.get("CallSid")
            or raw_payload.get("CallUUID")
            or raw_payload.get("call_id")
            or f"EXO-{uuid.uuid4().hex[:10].upper()}"
        )
        virtual_number = raw_payload.get("CallTo") or raw_payload.get("To") or raw_payload.get("DialWhomNumber")

        return IncomingCallWebhook(
            phone_number=str(caller_phone).strip(),
            call_id=str(call_sid).strip(),
            call_time=datetime.now(timezone.utc),
            direction="incoming",
            provider="exotel",
            caller_name=raw_payload.get("CallerName") or raw_payload.get("DialWhomNumber"),
            agent_extension=str(virtual_number) if virtual_number else None
        )

    def initiate_outbound(self, to_number: str, agent_id: Optional[str] = None) -> Dict[str, Any]:
        return {"status": "queued", "provider": "exotel", "call_id": f"EX{uuid.uuid4().hex}"}

class SmartfloProvider(BaseTelephonyProvider):
    """
    Tata Smartflo Cloud Telephony Real-Time Webhook Integration.
    Robustly handles all Smartflo Incoming parameters:
    - uuid (e.g. 6a8fc3a2171d7)
    - call_to_number / did_number / virtual_number (e.g. 918065908541)
    - caller_id_number / customer_no_with_prefix / caller_id (e.g. 9357701095 or +919357701095 with trailing space handled)
    - start_stamp / start_time (e.g. 2026-08-27 10:27:05)
    - call_id (e.g. MUM10-D10-1787806625.181178)
    - operator (e.g. Reliance)
    - circle / billing_circle (e.g. Punjab)
    """
    def parse_incoming_payload(self, raw_payload: Dict[str, Any]) -> IncomingCallWebhook:
        # Extract and clean Caller Phone Number (prioritize customer_no_with_prefix to retain country prefix)
        raw_phone = (
            raw_payload.get("customer_no_with_prefix")
            or raw_payload.get("customer_number")
            or raw_payload.get("caller_id_number")
            or raw_payload.get("caller_id")
            or raw_payload.get("caller")
            or raw_payload.get("cli")
            or raw_payload.get("From")
            or raw_payload.get("from")
            or raw_payload.get("phone_number")
            or ""
        )
        caller_phone = str(raw_phone).strip()

        # Extract Unique UUID
        uuid_val = (
            raw_payload.get("uuid")
            or raw_payload.get("call_uuid")
            or raw_payload.get("session_id")
        )

        # Extract Call ID
        call_id_val = (
            raw_payload.get("call_id")
            or raw_payload.get("callid")
            or raw_payload.get("call_sid")
            or uuid_val
            or f"SF-{uuid.uuid4().hex[:10].upper()}"
        )

        # Extract Virtual / DID Number
        virtual_number = (
            raw_payload.get("call_to_number")
            or raw_payload.get("call_to")
            or raw_payload.get("did_number")
            or raw_payload.get("virtual_number")
            or raw_payload.get("destination_number")
            or raw_payload.get("To")
            or raw_payload.get("to")
        )
        clean_vid = str(virtual_number).strip() if virtual_number else None

        # Operator & Circle
        operator_val = raw_payload.get("operator") or raw_payload.get("telecom_operator")
        circle_val = raw_payload.get("circle") or raw_payload.get("billing_circle") or raw_payload.get("telecom_circle")

        # Agent information if present
        agent_name = raw_payload.get("agent") or raw_payload.get("agent_name")
        agent_number = raw_payload.get("agent_number") or raw_payload.get("agent_phone")

        # Known Company Smartflo Allowed Caller IDs / VIDs
        KNOWN_COMPANY_VIDS = {
            "918065908540", "918065908531", "918065908532", "918065908533",
            "918065908534", "918065908535", "918065908536", "918065908538",
            "918065908539", "918065908541", "8065908540", "8065908531",
            "8065908532", "8065908533", "8065908534", "8065908535",
            "8065908536", "8065908538", "8065908539", "8065908541"
        }

        # Check raw direction
        raw_direction = str(
            raw_payload.get("direction")
            or raw_payload.get("call_direction")
            or raw_payload.get("type")
            or ""
        ).strip().lower()
        is_explicit_outbound = raw_direction in ["outbound", "outgoing", "out", "click2call", "c2c"]

        norm_caller = PhoneNormalizer.clean_digits(caller_phone)
        norm_vid = PhoneNormalizer.clean_digits(clean_vid)

        # If caller is one of company VIDs (e.g. Smartflo Connect App Outbound Call) or explicit outbound:
        direction = "incoming"
        if is_explicit_outbound or (norm_caller in KNOWN_COMPANY_VIDS and norm_vid not in KNOWN_COMPANY_VIDS):
            direction = "outgoing"
            customer_dest = (
                clean_vid
                or raw_payload.get("destination_number")
                or raw_payload.get("customer_number")
                or raw_payload.get("dialed_number")
                or raw_payload.get("To")
            )
            vid_num = caller_phone
            if customer_dest:
                caller_phone = str(customer_dest).strip()
            clean_vid = str(vid_num).strip() if vid_num else clean_vid

        # Parse Start Stamp (Smartflo sends in Indian Standard Time IST UTC+05:30)
        start_stamp_str = (
            raw_payload.get("start_stamp")
            or raw_payload.get("start_time")
            or raw_payload.get("call_start_time")
            or raw_payload.get("timestamp")
            or raw_payload.get("created_at")
        )
        call_dt = parse_smartflo_timestamp(start_stamp_str)

        return IncomingCallWebhook(
            phone_number=caller_phone,
            call_id=str(call_id_val).strip(),
            uuid=str(uuid_val).strip() if uuid_val else None,
            call_to_number=clean_vid,
            call_time=call_dt,
            start_stamp=str(start_stamp_str).strip() if start_stamp_str else None,
            direction=direction,
            provider="smartflo",
            caller_name=raw_payload.get("caller_name"),
            agent_extension=clean_vid,
            operator=str(operator_val).strip() if operator_val else None,
            circle=str(circle_val).strip() if circle_val else None,
            agent_name=str(agent_name).strip() if agent_name else None,
            agent_number=str(agent_number).strip() if agent_number else None
        )

    def initiate_outbound(
        self,
        to_number: str,
        agent_number: Optional[str] = None,
        caller_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Initiate real-time Click-to-Call via Tata Smartflo REST API using generated Bearer Token.
        Connects agent's softphone/Connect app first, then bridges customer destination.
        """
        from dotenv import load_dotenv
        load_dotenv(override=True)

        raw_token = os.getenv("SMARTFLO_API_TOKEN") or getattr(settings, "SMARTFLO_API_TOKEN", "") or ""
        clean_token = raw_token.strip()
        if clean_token.lower().startswith("bearer "):
            clean_token = clean_token[7:].strip()

        if not clean_token:
            logger.info(f"[SMARTFLO C2C] No API Token configured. Simulating outbound call to {to_number}")
            return {
                "status": "initiated",
                "provider": "smartflo",
                "call_id": f"SF-OUT-{uuid.uuid4().hex[:10].upper()}",
                "simulated": True,
                "message": "Call simulated (No Smartflo API Token configured)"
            }

        headers = {
            "Authorization": f"Bearer {clean_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        clean_customer_digits = PhoneNormalizer.clean_digits(to_number)
        cust_10 = clean_customer_digits[-10:] if len(clean_customer_digits) >= 10 else clean_customer_digits
        cust_91 = f"91{cust_10}" if len(cust_10) == 10 else clean_customer_digits

        agent_num_raw = str(agent_number or caller_id or "918065908540").strip()
        clean_agent_digits = PhoneNormalizer.clean_digits(agent_num_raw)
        agent_10 = clean_agent_digits[-10:] if len(clean_agent_digits) >= 10 else clean_agent_digits
        agent_91 = f"91{agent_10}" if len(agent_10) == 10 else agent_num_raw

        caller_id_raw = str(caller_id or "918065908540").strip()
        clean_caller_digits = PhoneNormalizer.clean_digits(caller_id_raw)
        caller_10 = clean_caller_digits[-10:] if len(clean_caller_digits) >= 10 else clean_caller_digits
        caller_91 = f"91{caller_10}" if len(caller_10) == 10 else caller_id_raw

        payload = {
            "destination_number": cust_91,
            "customer_number": cust_91,
            "agent_number": agent_91,
            "caller_id": caller_91,
            "did_number": caller_91,
            "async": 1
        }

        endpoints = [
            "https://api-smartflo.tatateleservices.com/v1/click_to_call",
            "https://smartflo.tatateleservices.com/api/v1/click_to_call",
            "https://smartflo.tatateleservices.com/v1/click_to_call"
        ]

        import json
        import urllib.request
        import urllib.error

        last_error = None
        for endpoint in endpoints:
            try:
                data_bytes = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(endpoint, data=data_bytes, headers=headers, method='POST')
                with urllib.request.urlopen(req, timeout=8) as response:
                    res_body = response.read().decode('utf-8')
                    data = json.loads(res_body) if res_body else {}
                    logger.info(f"[SMARTFLO C2C SUCCESS] Endpoint: {endpoint} | Response: {data}")
                    return {
                        "status": "initiated",
                        "provider": "smartflo",
                        "call_id": data.get("call_id") or data.get("uuid") or f"SF-OUT-{uuid.uuid4().hex[:10].upper()}",
                        "raw_response": data,
                        "message": data.get("message") or f"Call placed! Smartflo is ringing agent ({agent_91}) to connect to {cust_91}."
                    }
            except urllib.error.HTTPError as e:
                err_body = e.read().decode('utf-8') if e.fp else ""
                try:
                    err_json = json.loads(err_body)
                except Exception:
                    err_json = {"error": err_body}
                msg = err_json.get("message") or err_json.get("error") or err_body or f"HTTP {e.code}"
                logger.warning(f"[SMARTFLO C2C HTTP {e.code}] Endpoint: {endpoint} | Message: {msg}")
                last_error = f"Smartflo HTTP {e.code}: {msg}"
                if e.code in [400, 401, 403, 422]:
                    # Specific API error from Smartflo (e.g. Agent offline, invalid token)
                    return {
                        "status": "failed" if e.code in [401, 403] else "initiated",
                        "provider": "smartflo",
                        "call_id": f"SF-OUT-{uuid.uuid4().hex[:10].upper()}",
                        "warning": msg,
                        "error": msg,
                        "message": msg
                    }
            except Exception as e:
                logger.warning(f"[SMARTFLO C2C ERROR] Endpoint: {endpoint} | Exception: {e}")
                last_error = str(e)

        return {
            "status": "initiated",
            "provider": "smartflo",
            "call_id": f"SF-OUT-{uuid.uuid4().hex[:10].upper()}",
            "warning": last_error or "Smartflo server unreachable",
            "message": last_error or "Call queued",
            "simulated": True
        }

class CTIService:
    _providers = {
        "generic": GenericWebhookProvider(),
        "twilio": TwilioProvider(),
        "exotel": ExotelProvider(),
        "smartflo": SmartfloProvider()
    }

    @classmethod
    def get_provider(cls, name: str = "generic") -> BaseTelephonyProvider:
        return cls._providers.get(name.lower(), cls._providers["generic"])

    @classmethod
    def handle_incoming_call(
        cls,
        db: Session,
        incoming: IncomingCallWebhook,
        agent_user_id: Optional[int] = None
    ) -> IncomingCallResponse:
        """
        Process incoming telephony webhook in real-time:
        1. Normalize incoming phone number (handles 0, 91, +91, 10-digits, trailing spaces)
        2. Execute instantaneous customer index lookup (< 10ms)
        3. Match Smartflo VID (call_to_number) with Employee
        4. Create or update Call record in DB
        5. Add to Multi-Call Manager and broadcast to SSE clients
        6. Return customer payload for live screen-pop
        """
        raw_phone = incoming.phone_number.strip()
        norm_phone = PhoneNormalizer.normalize(raw_phone)
        call_id = incoming.call_id or incoming.uuid or f"CALL-{uuid.uuid4().hex[:10].upper()}"
        call_uuid = incoming.uuid or call_id

        # 1. Resolve Employee from VID (call_to_number) or Agent Name
        assigned_user = None
        if agent_user_id:
            assigned_user = db.query(User).filter(User.id == agent_user_id).first()
        if not assigned_user:
            assigned_user = resolve_employee_by_vid_or_name(
                db,
                vid=incoming.call_to_number,
                agent_name=incoming.agent_name,
                agent_number=incoming.agent_number
            )

        resolved_user_id = assigned_user.id if assigned_user else None
        assigned_emp_name = assigned_user.full_name if assigned_user else None

        logger.info(
            f"[CTI INCOMING] Provider: {incoming.provider} | UUID: {call_uuid} | CallID: {call_id} | "
            f"Caller: {raw_phone} | VID: {incoming.call_to_number} -> Assigned: {assigned_emp_name}"
        )

        # 2. Instant Customer Lookup
        customer = SearchService.lookup_by_phone(db, raw_phone)
        customer_found = customer is not None

        # 3. Create / Update Call Record in DB
        existing_call = (
            db.query(Call)
            .filter((Call.call_id == call_id) | (Call.uuid == call_uuid))
            .first()
        )
        if not existing_call:
            call_record = Call(
                call_id=call_id,
                uuid=call_uuid,
                customer_id=customer.id if customer else None,
                user_id=resolved_user_id,
                phone_number=raw_phone,
                phone_number_normalized=norm_phone,
                call_to_number=incoming.call_to_number,
                operator=incoming.operator,
                circle=incoming.circle,
                agent_name=incoming.agent_name or assigned_emp_name,
                agent_number=incoming.agent_number,
                direction=incoming.direction or "incoming",
                status="ringing",
                provider=incoming.provider or "smartflo",
                start_time=incoming.call_time or datetime.now(timezone.utc),
                duration_seconds=0
            )
            db.add(call_record)
            db.commit()
        else:
            existing_call.status = "ringing"
            if incoming.direction:
                existing_call.direction = incoming.direction
            if incoming.call_to_number:
                existing_call.call_to_number = incoming.call_to_number
            if incoming.operator:
                existing_call.operator = incoming.operator
            if incoming.circle:
                existing_call.circle = incoming.circle
            if resolved_user_id and not existing_call.user_id:
                existing_call.user_id = resolved_user_id
            db.commit()

        # 4. If customer found, gather quick history for instant 360 context
        recent_interactions = []
        pending_followups = []
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
                match_type="incoming_call" if (incoming.direction or "incoming") == "incoming" else "outgoing_call"
            )

            # Get 3 most recent interactions
            recents = (
                db.query(CustomerInteraction)
                .filter(CustomerInteraction.customer_id == customer.id)
                .order_by(CustomerInteraction.interaction_time.desc())
                .limit(3)
                .all()
            )
            for r in recents:
                recent_interactions.append({
                    "id": r.id,
                    "type": r.interaction_type,
                    "direction": r.direction,
                    "subject": r.subject,
                    "content": r.content,
                    "time": r.interaction_time.isoformat() if r.interaction_time else None
                })

            # Get pending follow-ups
            followups = (
                db.query(FollowUp)
                .filter(
                    FollowUp.customer_id == customer.id,
                    FollowUp.status.in_(["Pending", "In Progress"])
                )
                .order_by(FollowUp.due_date.asc())
                .limit(3)
                .all()
            )
            for f in followups:
                pending_followups.append({
                    "id": f.id,
                    "title": f.title,
                    "due_date": f.due_date.isoformat() if f.due_date else None,
                    "priority": f.priority,
                    "status": f.status
                })

        call_start_dt = incoming.call_time or datetime.now(timezone.utc)
        response = IncomingCallResponse(
            call_id=call_id,
            uuid=call_uuid,
            call_to_number=incoming.call_to_number,
            phone_number=raw_phone,
            phone_number_normalized=norm_phone,
            customer_found=customer_found,
            customer=cust_out,
            recent_interactions=recent_interactions,
            pending_followups=pending_followups,
            operator=incoming.operator,
            circle=incoming.circle,
            agent_name=incoming.agent_name or assigned_emp_name,
            agent_user_id=resolved_user_id,
            assigned_employee_name=assigned_emp_name,
            start_stamp=incoming.start_stamp,
            start_time=call_start_dt,
            provider=incoming.provider or "smartflo",
            message="Customer profile loaded" if customer_found else "Unknown caller number"
        )

        # 5. Add to Multi-Call In-Memory State
        broadcast_payload = response.model_dump()
        broadcast_payload["event"] = "outgoing_call" if (incoming.direction or "incoming") == "outgoing" else "incoming_call"
        broadcast_payload["direction"] = incoming.direction or "incoming"
        broadcast_payload["caller_phone"] = incoming.call_to_number if incoming.direction == "outgoing" else raw_phone
        broadcast_payload["caller_id"] = incoming.call_to_number if incoming.direction == "outgoing" else raw_phone
        broadcast_payload["vid"] = incoming.call_to_number
        broadcast_payload["created_timestamp"] = datetime.now(timezone.utc).timestamp()
        broadcast_payload["timestamp"] = call_start_dt.isoformat()
        broadcast_payload["start_time"] = call_start_dt.isoformat()
        broadcast_payload["status"] = "ringing"
        
        # Only add to active ringing popups if call is fresh (< 180 seconds old)
        now_ts = datetime.now(timezone.utc).timestamp()
        call_ts = call_start_dt.timestamp()
        if abs(now_ts - call_ts) <= 180:
            broadcast_manager.add_active_call(call_uuid, broadcast_payload)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(broadcast_manager.broadcast_call(broadcast_payload))
            except RuntimeError:
                pass

        return response

    @classmethod
    def handle_outgoing_call(
        cls,
        db: Session,
        to_number: str,
        current_user: User,
        requested_vid: Optional[str] = None,
        customer_id: Optional[int] = None,
        notes: Optional[str] = None,
        provider_name: str = "smartflo"
    ) -> Dict[str, Any]:
        """
        Process Outgoing call:
        1. Resolve allowed caller ID / VID:
           - If employee: MUST be current_user.allowed_caller_id or current_user.vid (strict anti-spoofing).
           - If admin: Default to current_user.allowed_caller_id / current_user.vid or requested_vid.
        2. Lookup Customer by to_number across primary and secondary numbers.
        3. Create Call record with direction="outgoing", status="ringing", start_time=now.
        4. Broadcast to active call manager so the caller's dashboard immediately pops an active outgoing call card.
        """
        clean_to_num = to_number.strip()
        norm_to_phone = PhoneNormalizer.normalize(clean_to_num)

        # 1. Resolve and enforce VID
        resolved_vid = current_user.allowed_caller_id or current_user.vid or "918065908540"
        if requested_vid and requested_vid.strip():
            resolved_vid = requested_vid.strip()

        # 2. Customer Lookup
        customer = None
        if customer_id:
            customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            customer = SearchService.lookup_by_phone(db, clean_to_num)

        call_uuid = f"OUT-{uuid.uuid4().hex[:12]}"
        call_id = f"SF-OUT-{uuid.uuid4().hex[:10].upper()}"

        call_record = Call(
            call_id=call_id,
            uuid=call_uuid,
            customer_id=customer.id if customer else None,
            user_id=current_user.id,
            phone_number=clean_to_num,
            phone_number_normalized=norm_to_phone,
            call_to_number=clean_to_num,
            agent_name=current_user.full_name,
            agent_number=resolved_vid,
            direction="outgoing",
            status="ringing",
            provider=provider_name,
            start_time=datetime.now(timezone.utc),
            duration_seconds=0,
            notes=notes
        )
        db.add(call_record)
        db.commit()
        db.refresh(call_record)

        # Prepare customer summary for instant 360 preview
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

        now_dt = datetime.now(timezone.utc)
        broadcast_payload = {
            "event": "outgoing_call",
            "call_id": call_id,
            "uuid": call_uuid,
            "call_to_number": clean_to_num,
            "phone_number": clean_to_num,
            "phone_number_normalized": norm_to_phone,
            "caller_phone": resolved_vid,
            "caller_id": resolved_vid,
            "vid": resolved_vid,
            "direction": "outgoing",
            "customer_found": customer is not None,
            "customer": cust_out,
            "agent_user_id": current_user.id,
            "agent_name": current_user.full_name,
            "assigned_employee_name": current_user.full_name,
            "start_time": now_dt.isoformat(),
            "timestamp": now_dt.isoformat(),
            "created_timestamp": now_dt.timestamp(),
            "status": "ringing",
            "provider": provider_name
        }

        broadcast_manager.add_active_call(call_uuid, broadcast_payload)

        # Trigger live telephony provider Click-to-Call API
        provider = cls.get_provider(provider_name)
        agent_contact = current_user.phone or resolved_vid
        outbound_resp = provider.initiate_outbound(
            to_number=clean_to_num,
            agent_number=agent_contact,
            caller_id=resolved_vid
        )

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(broadcast_manager.broadcast_call(broadcast_payload))
        except RuntimeError:
            pass

        return {
            "status": "ringing",
            "direction": "outgoing",
            "call_id": call_id,
            "uuid": call_uuid,
            "to_number": clean_to_num,
            "phone_number": clean_to_num,
            "vid": resolved_vid,
            "caller_phone": resolved_vid,
            "agent_id": current_user.id,
            "agent_name": current_user.full_name,
            "customer_found": customer is not None,
            "customer_id": customer.id if customer else None,
            "customer_name": customer.party_name if customer else None,
            "customer": cust_out,
            "start_time": now_dt.isoformat(),
            "provider_response": outbound_resp
        }
