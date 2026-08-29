import os
import json
import base64
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from backend.app.config import settings

logger = logging.getLogger(__name__)

class SmartfloTokenService:
    """
    Enterprise Call API Token Management & Expiry Tracking Service.
    Automatically parses Smartflo JWT token payload to track creation, expiry, and 10-day alerts.
    """
    DEFAULT_NAME = "CRM Outbound ClickToCall"

    @classmethod
    def get_raw_token(cls) -> str:
        return os.getenv("SMARTFLO_API_TOKEN") or getattr(settings, "SMARTFLO_API_TOKEN", "") or ""

    @classmethod
    def parse_jwt_payload(cls, token: str) -> Dict[str, Any]:
        """Decode JWT payload without verifying signature to extract exp and iat."""
        if not token or not isinstance(token, str):
            return {}
        parts = token.strip().split(".")
        if len(parts) < 2:
            return {}
        try:
            payload_b64 = parts[1]
            # Add padding if needed
            rem = len(payload_b64) % 4
            if rem > 0:
                payload_b64 += "=" * (4 - rem)
            payload_json = base64.urlsafe_b64decode(payload_b64.encode('utf-8')).decode('utf-8')
            return json.loads(payload_json)
        except Exception as e:
            logger.warning(f"Could not decode JWT payload: {e}")
            return {}

    METADATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smartflo_token_meta.json")

    @classmethod
    def get_token_metadata(cls) -> Dict[str, Any]:
        """
        Returns full token status, masked token, creation time, expiry time,
        days left, and whether a 10-day expiry alert is active.
        Enforces standard 90-day maximum lifecycle for Tata Smartflo tokens.
        """
        token = cls.get_raw_token()
        payload = cls.parse_jwt_payload(token)
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        now_utc = datetime.now(timezone.utc)

        # Load persisted token meta if exists
        saved_meta = {}
        if os.path.exists(cls.METADATA_FILE):
            try:
                with open(cls.METADATA_FILE, "r", encoding="utf-8") as f:
                    saved_meta = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load smartflo_token_meta.json: {e}")

        created_at_dt = None
        expires_at_dt = None

        if "iat" in payload and payload["iat"]:
            try:
                created_at_dt = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
            except Exception:
                pass
        if "exp" in payload and payload["exp"]:
            try:
                expires_at_dt = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
            except Exception:
                pass

        # If saved meta belongs to the current token
        if saved_meta.get("token_hash") == hash(token):
            if not created_at_dt and saved_meta.get("created_at_iso"):
                created_at_dt = datetime.fromisoformat(saved_meta["created_at_iso"])
            if not expires_at_dt and saved_meta.get("expiry_iso"):
                expires_at_dt = datetime.fromisoformat(saved_meta["expiry_iso"])

        # Default 90-day lifecycle fallback if not in JWT
        if not created_at_dt:
            created_at_dt = now_utc
        if not expires_at_dt:
            # Fixed 90 days validity from creation date
            expires_at_dt = created_at_dt + timedelta(days=90)

        created_at_ist = created_at_dt.astimezone(ist_tz)
        expires_at_ist = expires_at_dt.astimezone(ist_tz)

        # Calculate exact difference
        time_left = expires_at_dt - now_utc
        days_left = time_left.total_seconds() / 86400.0

        is_expired = days_left <= 0
        is_expiring_soon = 0 < days_left <= 10.0

        # Masked token representation: eyJhbG****yB5k
        masked_token = "—"
        if token and len(token) > 12:
            masked_token = f"{token[:6]}****{token[-4:]}"
        elif token:
            masked_token = f"{token[:3]}****"

        status_label = "active"
        status_text = f"Active ({int(days_left)} days remaining)"
        if not token:
            status_label = "invalid"
            status_text = "No Token Configured"
        elif is_expired:
            status_label = "expired"
            status_text = "Expired"
        elif is_expiring_soon:
            status_label = "expiring_soon"
            status_text = f"Expiring Soon ({int(days_left)} days left)"

        alert_message = None
        if is_expired:
            alert_message = f"🚨 Tata Smartflo Call API Token expired on {expires_at_ist.strftime('%d %b %Y, %I:%M %p')}. Outbound click-to-call is currently unavailable. Please generate a new token and update it below."
        elif is_expiring_soon:
            alert_message = f"⚠️ Tata Smartflo Call API Token is expiring in {int(days_left)} day(s) on {expires_at_ist.strftime('%d %b %Y, %I:%M %p')}. Please generate a new token from Tata Smartflo portal and update it in CTI Dashboard to prevent service disruption."

        return {
            "token_name": saved_meta.get("token_name") or cls.DEFAULT_NAME,
            "raw_token": token,
            "masked_token": masked_token,
            "created_at_iso": created_at_dt.isoformat(),
            "created_at_formatted": created_at_ist.strftime("%d %b %Y, %I:%M %p"),
            "expiry_iso": expires_at_dt.isoformat(),
            "expiry_formatted": expires_at_ist.strftime("%d %b %Y, %I:%M %p"),
            "days_left": round(days_left, 1),
            "days_left_int": max(0, int(days_left)),
            "is_expiring_soon": is_expiring_soon,
            "is_expired": is_expired,
            "is_valid": bool(token and not is_expired),
            "status": status_label,
            "status_text": status_text,
            "access_control": "NONE",
            "blacklisted": False,
            "alert_message": alert_message
        }

    @classmethod
    def update_token(cls, new_token: str, token_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Update the active Smartflo API Token in environment variables, settings, and .env file.
        Freshly restarts the 90-day lifecycle for the new token.
        """
        clean_token = new_token.strip()
        if not clean_token:
            raise ValueError("Token cannot be empty")

        now_utc = datetime.now(timezone.utc)
        payload = cls.parse_jwt_payload(clean_token)

        created_dt = now_utc
        if "iat" in payload and payload["iat"]:
            try:
                created_dt = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
            except Exception:
                pass

        # Expiry from JWT or 90 days from creation
        expiry_dt = created_dt + timedelta(days=90)
        if "exp" in payload and payload["exp"]:
            try:
                expiry_dt = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
            except Exception:
                pass

        # Save metadata JSON for fresh lifecycle tracking
        try:
            with open(cls.METADATA_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "token_hash": hash(clean_token),
                    "token_name": token_name or cls.DEFAULT_NAME,
                    "created_at_iso": created_dt.isoformat(),
                    "expiry_iso": expiry_dt.isoformat(),
                    "updated_at_iso": now_utc.isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write smartflo_token_meta.json: {e}")

        # Update runtime in-memory settings
        os.environ["SMARTFLO_API_TOKEN"] = clean_token
        settings.SMARTFLO_API_TOKEN = clean_token

        # Update .env file persistently
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                found = False
                new_lines = []
                for line in lines:
                    if line.strip().startswith("SMARTFLO_API_TOKEN="):
                        new_lines.append(f'SMARTFLO_API_TOKEN="{clean_token}"\n')
                        found = True
                    else:
                        new_lines.append(line)
                
                if not found:
                    new_lines.append(f'\nSMARTFLO_API_TOKEN="{clean_token}"\n')

                with open(env_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                logger.info("[SMARTFLO TOKEN] Persisted new API token to .env file.")
            except Exception as e:
                logger.error(f"Error persisting token to .env: {e}")

        return cls.get_token_metadata()
