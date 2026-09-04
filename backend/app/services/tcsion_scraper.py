import os
import io
import sys
import csv
import json
import subprocess
import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from backend.app.config import settings

logger = logging.getLogger("tcsion_scraper")

# Global mutex lock to prevent concurrent sessions on the same TCS iON account
_tcsion_lock = asyncio.Lock()
_last_scrape_status = {
    "is_running": False,
    "last_run": None,
    "last_error": None,
    "current_party": None,
    "progress_step": None
}

class TcsIonScraperService:
    def __init__(self):
        self.login_url = settings.TCSION_LOGIN_URL
        self.username = settings.TCSION_USERNAME
        self.password = settings.TCSION_PASSWORD
        self.is_headless = settings.TCSION_HEADLESS
        self.worker_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "tcsion_worker.py"))

    def get_status(self) -> Dict[str, Any]:
        return {
            **_last_scrape_status,
            "has_credentials": bool(self.username and self.password),
            "is_locked": _tcsion_lock.locked()
        }

    async def launch_visual_party_ledger(self, party_name: str, months_back: int = 3) -> Dict[str, Any]:
        """
        Visual Auto-Launcher:
        Spawns a real, visible Chrome browser on desktop in an isolated process.
        Automatically logs into TCS iON, clicks Finance & Accounting -> Accounts Receivable -> Drill Down Reports -> Party Ledger Detail,
        and leaves the live Party Ledger screen OPEN on the desktop!
        """
        if not self.username or not self.password:
            raise ValueError("TCS iON credentials not configured in environment.")

        party_name_clean = party_name.strip()
        if not party_name_clean:
            raise ValueError("Party Name must be provided.")

        cmd = [
            sys.executable,
            self.worker_script,
            "--party", party_name_clean,
            "--months", str(months_back),
            "--mode", "visual",
            "--url", self.login_url
        ]
        env = {
            **os.environ,
            "TCSION_USERNAME": self.username,
            "TCSION_PASSWORD": self.password,
            "TCSION_LOGIN_URL": self.login_url
        }

        logger.info(f"Visual Launcher: Spawning visible worker process for '{party_name_clean}'...")
        # Spawn detached / independent background process on desktop
        subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        )

        return {
            "success": True,
            "party_name": party_name_clean,
            "message": f"🚀 Live Chrome window is opening on your desktop and navigating to Party Ledger for '{party_name_clean}'!"
        }

    def parse_tcsion_file_content(self, file_bytes: bytes, filename: str, party_name: str = "") -> Dict[str, Any]:
        """
        Parses CSV, JSON, or Excel (.xlsx/.xls) export directly downloaded from
        TCS iON Party Ledger Detail Report (ARSC0010) as shown in User Image 1.
        """
        records = []
        total_debit = 0.0
        total_credit = 0.0
        detected_party = party_name or "TCS Customer"

        fn_lower = filename.lower()

        # 1. JSON Format
        if fn_lower.endswith(".json"):
            try:
                data = json.loads(file_bytes.decode("utf-8", errors="ignore"))
                raw_items = data if isinstance(data, list) else data.get("records", data.get("data", []))
                for item in raw_items:
                    dr = self._clean_number(item.get("Debit Amount") or item.get("debit_amount") or 0)
                    cr = self._clean_number(item.get("Credit Amount") or item.get("credit_amount") or 0)
                    bal = self._clean_number(item.get("Closing Amount in Domestic Currency") or item.get("balance_amount") or 0)
                    total_debit += dr
                    total_credit += cr
                    records.append({
                        "party_code": item.get("Party Code") or item.get("party_code") or "CUST-TCS",
                        "voucher_number": item.get("Voucher Number") or item.get("voucher_number") or "—",
                        "voucher_date": item.get("Voucher Date") or item.get("voucher_date") or "—",
                        "voucher_sub_type": item.get("Accounting Voucher Type") or item.get("voucher_sub_type") or "General",
                        "debit_amount": dr,
                        "credit_amount": cr,
                        "balance_amount": bal,
                        "particulars": item.get("Header Narration / Details") or item.get("particulars") or f"{item.get('voucher_sub_type', '')}"
                    })
            except Exception as e:
                logger.error(f"Failed to parse TCS JSON export: {e}")

        # 2. Excel Format (.xlsx / .xls)
        elif fn_lower.endswith((".xlsx", ".xls")):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
                ws = wb.active
                rows = list(ws.iter_rows(values_only=True))
                if len(rows) > 1:
                    headers = [str(h).strip().lower() if h else "" for h in rows[0]]
                    
                    def find_col(candidates):
                        for c in candidates:
                            for idx, h in enumerate(headers):
                                if c in h:
                                    return idx
                        return -1

                    col_party_code = find_col(["party code"])
                    col_party_desc = find_col(["party description", "party name"])
                    col_v_num = find_col(["voucher number", "voucher no"])
                    col_v_date = find_col(["voucher date", "date"])
                    col_v_type = find_col(["accounting voucher type", "voucher sub type", "voucher type"])
                    col_debit = find_col(["debit amount", "debit"])
                    col_credit = find_col(["credit amount", "credit"])
                    col_closing = find_col(["closing amount", "balance", "closing balance"])
                    col_narration = find_col(["header narration", "narration", "particulars", "details"])

                    for row in rows[1:]:
                        if not any(row):
                            continue
                        v_num = str(row[col_v_num]).strip() if col_v_num >= 0 and row[col_v_num] is not None else ""
                        if not v_num or "total" in v_num.lower() or "summary" in v_num.lower():
                            continue

                        p_code = str(row[col_party_code]).strip() if col_party_code >= 0 and row[col_party_code] is not None else "CUST-TCS"
                        p_desc = str(row[col_party_desc]).strip() if col_party_desc >= 0 and row[col_party_desc] is not None else ""
                        if p_desc:
                            detected_party = p_desc

                        v_date = str(row[col_v_date]).strip() if col_v_date >= 0 and row[col_v_date] is not None else ""
                        if isinstance(row[col_v_date], datetime):
                            v_date = row[col_v_date].strftime("%d/%m/%Y")

                        v_type = str(row[col_v_type]).strip() if col_v_type >= 0 and row[col_v_type] is not None else "General"
                        dr_val = self._clean_number(row[col_debit]) if col_debit >= 0 else 0.0
                        cr_val = self._clean_number(row[col_credit]) if col_credit >= 0 else 0.0
                        bal_val = self._clean_number(row[col_closing]) if col_closing >= 0 else 0.0
                        narr = str(row[col_narration]).strip() if col_narration >= 0 and row[col_narration] is not None else f"{v_type} {v_num}"

                        total_debit += dr_val
                        total_credit += cr_val

                        records.append({
                            "party_code": p_code,
                            "voucher_number": v_num,
                            "voucher_date": v_date,
                            "voucher_sub_type": v_type,
                            "debit_amount": dr_val,
                            "credit_amount": cr_val,
                            "balance_amount": bal_val,
                            "particulars": narr
                        })
            except Exception as e:
                logger.error(f"Failed to parse TCS Excel export: {e}")

        # 3. CSV Format (Default fallback)
        else:
            try:
                decoded_str = file_bytes.decode("utf-8-sig", errors="ignore")
                reader = csv.reader(io.StringIO(decoded_str))
                rows = list(reader)
                if len(rows) > 1:
                    headers = [str(h).strip().lower() for h in rows[0]]
                    
                    def find_csv_col(candidates):
                        for c in candidates:
                            for idx, h in enumerate(headers):
                                if c in h:
                                    return idx
                        return -1

                    col_party_code = find_csv_col(["party code"])
                    col_party_desc = find_csv_col(["party description", "party name"])
                    col_v_num = find_csv_col(["voucher number", "voucher no"])
                    col_v_date = find_csv_col(["voucher date", "date"])
                    col_v_type = find_csv_col(["accounting voucher type", "voucher sub type", "voucher type"])
                    col_debit = find_csv_col(["debit amount", "debit"])
                    col_credit = find_csv_col(["credit amount", "credit"])
                    col_closing = find_csv_col(["closing amount", "balance", "closing balance"])
                    col_narration = find_csv_col(["header narration", "narration", "particulars", "details"])

                    for row in rows[1:]:
                        if not any(row):
                            continue
                        v_num = row[col_v_num].strip() if col_v_num >= 0 and len(row) > col_v_num else ""
                        if not v_num or "total" in v_num.lower() or "summary" in v_num.lower():
                            continue

                        p_code = row[col_party_code].strip() if col_party_code >= 0 and len(row) > col_party_code else "CUST-TCS"
                        p_desc = row[col_party_desc].strip() if col_party_desc >= 0 and len(row) > col_party_desc else ""
                        if p_desc:
                            detected_party = p_desc

                        v_date = row[col_v_date].strip() if col_v_date >= 0 and len(row) > col_v_date else ""
                        v_type = row[col_v_type].strip() if col_v_type >= 0 and len(row) > col_v_type else "General"
                        dr_val = self._clean_number(row[col_debit]) if col_debit >= 0 and len(row) > col_debit else 0.0
                        cr_val = self._clean_number(row[col_credit]) if col_credit >= 0 and len(row) > col_credit else 0.0
                        bal_val = self._clean_number(row[col_closing]) if col_closing >= 0 and len(row) > col_closing else 0.0
                        narr = row[col_narration].strip() if col_narration >= 0 and len(row) > col_narration else f"{v_type} {v_num}"

                        total_debit += dr_val
                        total_credit += cr_val

                        records.append({
                            "party_code": p_code,
                            "voucher_number": v_num,
                            "voucher_date": v_date,
                            "voucher_sub_type": v_type,
                            "debit_amount": dr_val,
                            "credit_amount": cr_val,
                            "balance_amount": bal_val,
                            "particulars": narr
                        })
            except Exception as e:
                logger.error(f"Failed to parse TCS CSV export: {e}")

        return {
            "success": True,
            "party_name": detected_party,
            "from_date": "04/06/2026",
            "to_date": datetime.now().strftime("%d/%m/%Y"),
            "total_records": len(records),
            "summary": {
                "opening_balance": 0.0,
                "total_debit": round(total_debit, 2),
                "total_credit": round(total_credit, 2),
                "closing_balance": round(total_debit - total_credit, 2)
            },
            "records": records,
            "synced_at": datetime.utcnow().isoformat(),
            "source": f"TCS iON File Import ({filename})"
        }

    def _clean_number(self, val_str: Any) -> float:
        if val_str is None:
            return 0.0
        if isinstance(val_str, (int, float)):
            return float(val_str)
        try:
            cleaned = str(val_str).replace(",", "").replace("₹", "").replace("Dr", "").replace("Cr", "").strip()
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

tcsion_scraper = TcsIonScraperService()
