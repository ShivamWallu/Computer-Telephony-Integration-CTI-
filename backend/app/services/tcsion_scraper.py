import os
import sys
import subprocess
import logging
import asyncio
from typing import Dict, Any, Optional

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

    async def launch_visual_party_ledger(
        self,
        party_name: str,
        months_back: int = 3,
        username: Optional[str] = None,
        password: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Visual Auto-Launcher:
        Spawns a real, visible Chrome browser on desktop in an isolated process.
        Automatically logs into TCS iON using the authenticated user's specific credentials,
        clicks Finance & Accounting -> Accounts Receivable -> Drill Down Reports -> Party Ledger Detail,
        and leaves the live Party Ledger screen OPEN on the desktop!
        """
        tcs_user = (username or "").strip() or self.username
        tcs_pass = (password or "").strip() or self.password

        if not tcs_user or not tcs_pass:
            raise ValueError("TCS iON credentials not configured for this user.")

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
            "TCSION_USERNAME": tcs_user,
            "TCSION_PASSWORD": tcs_pass,
            "TCSION_LOGIN_URL": self.login_url
        }

        logger.info(f"Visual Launcher: Spawning visible worker process for '{party_name_clean}' using account '{tcs_user}'...")
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
            "tcs_user": tcs_user,
            "message": f"🚀 Live Chrome window is opening on your desktop and navigating to Party Ledger for '{party_name_clean}' using account '{tcs_user}'!"
        }

tcsion_scraper = TcsIonScraperService()
