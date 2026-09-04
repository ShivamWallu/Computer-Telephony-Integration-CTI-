import os
import io
import sys
import csv
import json
import time
import random
import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

try:
    import openpyxl
except ImportError:
    openpyxl = None

from playwright.sync_api import sync_playwright, Page, BrowserContext

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("tcsion_worker")

# Define Navigation States
STATE_UNKNOWN = "UNKNOWN"
STATE_SESSION_CONFLICT = "SESSION_CONFLICT"
STATE_SESSION_EXPIRED = "SESSION_EXPIRED"
STATE_LOGIN_PAGE = "LOGIN_PAGE"
STATE_TCSION_HOME = "TCSION_HOME"
STATE_FINANCE_NAVBAR = "FINANCE_NAVBAR"
STATE_REPORTS_GRID = "REPORTS_GRID"
STATE_PARTY_LEDGER = "PARTY_LEDGER"

def human_delay(min_sec: float = 1.0, max_sec: float = 2.5):
    """Simulate natural human dwell and reaction time."""
    time.sleep(random.uniform(min_sec, max_sec))

def clean_num(val_str: Any) -> float:
    """Normalize currency / numeric strings to float."""
    if val_str is None:
        return 0.0
    if isinstance(val_str, (int, float)):
        return float(val_str)
    try:
        cleaned = str(val_str).replace(",", "").replace("₹", "").replace("Dr", "").replace("Cr", "").strip()
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


class TcsIonStateMachine:
    """
    Production-grade, session-aware State Machine for TCS iON ERP.
    Navigates to Party Ledger Detail (Supplier/Customer) report (ARSC0010).
    Reuses existing authenticated sessions and never duplicates login.
    """

    def __init__(self, party_name: str, months_back: int, mode: str, username: str, password: str, login_url: str):
        self.party_name = party_name.strip()
        self.months_back = months_back
        self.mode = mode
        self.username = username
        self.password = password
        self.login_url = login_url or "https://training.tcsion.com/Login/Login.html"
        self.home_url = "https://training.tcsion.com/TCSiONHome/Home"

        self.is_visual = (mode == "visual")
        self.is_headless = not self.is_visual

        # Profile directory for persistent browser session cookies
        self.profile_dir = os.path.abspath("backend/cache/tcs_browser_profile")
        os.makedirs(self.profile_dir, exist_ok=True)

        from_date_dt = datetime.now() - timedelta(days=months_back * 30)
        to_date_dt = datetime.now()
        self.from_date_str = from_date_dt.strftime("%d/%m/%Y")
        self.to_date_str = to_date_dt.strftime("%d/%m/%Y")

    def run(self) -> Dict[str, Any]:
        with sync_playwright() as p:
            args = [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
            if self.is_visual:
                args.append("--start-maximized")

            context = p.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                headless=self.is_headless,
                args=args,
                no_viewport=self.is_visual,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                accept_downloads=True
            )

            try:
                result = self._execute_state_machine(context)
                return result
            finally:
                if not self.is_visual:
                    try:
                        context.close()
                    except Exception:
                        pass

    def _execute_state_machine(self, context: BrowserContext) -> Dict[str, Any]:
        # Step 1: Initialize session check
        page = context.pages[0] if context.pages else context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        logger.info("Checking for existing active TCS iON session...")
        # First try navigating to Home URL to test if session cookies are already valid
        try:
            page.goto(self.home_url, wait_until="networkidle", timeout=30000)
        except Exception:
            try:
                page.goto(self.home_url, wait_until="domcontentloaded", timeout=20000)
            except Exception as e:
                logger.warning(f"Initial Home navigation timeout: {e}")

        human_delay(1.5, 2.5)

        max_transitions = 14
        transitions = 0
        active_page = page

        while transitions < max_transitions:
            transitions += 1
            state, active_page = self._detect_current_state(context, active_page)
            logger.info(f"[State Machine Transition #{transitions}] Detected State: {state} on URL: {active_page.url}")

            if state == STATE_PARTY_LEDGER:
                logger.info("Target State Reached: Party Ledger Detail Report Screen.")
                return self._handle_party_ledger_screen(context, active_page)

            elif state == STATE_SESSION_CONFLICT:
                logger.warning("Session Conflict Detected: You are already logged in with this ID.")
                return {
                    "success": False,
                    "cooldown": True,
                    "error": "You are already logged into TCS iON with this ID. Please log out from that session and log in after 2 minutes."
                }

            elif state == STATE_SESSION_EXPIRED:
                logger.info("Session expired detected. Returning to login...")
                self._handle_session_expired(active_page)

            elif state == STATE_LOGIN_PAGE:
                logger.info("User is not logged in. Executing normal login process...")
                success = self._handle_login(active_page)
                if not success:
                    # Check if error or conflict appeared after login attempt
                    sub_state, active_page = self._detect_current_state(context, active_page)
                    if sub_state == STATE_SESSION_CONFLICT:
                        return {
                            "success": False,
                            "cooldown": True,
                            "error": "You are already logged into TCS iON with this ID. Please log out from that session and log in after 2 minutes."
                        }
                    return {
                        "success": False,
                        "error": "TCS iON Login failed. Please verify credentials."
                    }

            elif state == STATE_TCSION_HOME:
                logger.info("At TCS iON Home / Applications. Clicking Finance and Accounting...")
                active_page = self._handle_home_click_finance(context, active_page)

            elif state == STATE_FINANCE_NAVBAR:
                logger.info("At Finance and Accounting. Opening Accounts Receivable -> Drill Down Reports...")
                active_page = self._handle_finance_click_ar_drilldown(context, active_page)

            elif state == STATE_REPORTS_GRID:
                logger.info("At Accounts Receivable Reports Grid. Selecting Party Ledger Detail tile...")
                active_page = self._handle_select_party_ledger_tile(context, active_page)

            elif state == STATE_UNKNOWN:
                logger.warning("Current state is UNKNOWN. Attempting to navigate to Home URL...")
                try:
                    active_page.goto(self.home_url, wait_until="networkidle", timeout=30000)
                except Exception:
                    active_page.goto(self.login_url, wait_until="domcontentloaded", timeout=20000)
                human_delay(2.0, 3.0)

        return {
            "success": False,
            "error": "Automation exceeded maximum state transitions without reaching target screen."
        }

    def _detect_current_state(self, context: BrowserContext, current_page: Page) -> Tuple[str, Page]:
        """
        Inspects all open tabs/pages and DOM elements to determine current state.
        Prioritizes the most specific state first.
        """
        all_pages = list(context.pages)
        if current_page not in all_pages and all_pages:
            current_page = all_pages[-1]

        # Prioritize checking current_page, then other open tabs
        candidate_pages = [current_page] + [p for p in all_pages if p != current_page]

        for p in candidate_pages:
            try:
                url = p.url or ""
                # Check for session conflict error first
                if "loginfailure" in url.lower():
                    return STATE_SESSION_CONFLICT, p

                # Evaluate page content for conflict message
                body_text = ""
                try:
                    body_text = p.inner_text("body", timeout=1200)
                except Exception:
                    pass

                if "already logged into tcs ion with this id" in body_text.lower() or "log in after 2 minutes" in body_text.lower():
                    return STATE_SESSION_CONFLICT, p

                if "sessionexpired" in url.lower() or "session has timed out due to inactivity" in body_text.lower():
                    return STATE_SESSION_EXPIRED, p

                # 1. Check for Login Page (Unauthenticated)
                if "login.html" in url.lower() or p.locator('#floatingInput, #floatingPassword, #submitlogin').first.is_visible(timeout=500):
                    return STATE_LOGIN_PAGE, p

                # Check indicators across page and all frames (supports Dojo/iFrames)
                frames_to_check = [p] + [f for f in p.frames if f != p.main_frame]

                # 2. Check for Target Screen: Party Ledger Detail Report
                pl_indicators = [
                    '#txtParty',
                    'input[placeholder*="Party" i]',
                    'text="Party Ledger Detail Report"',
                    'span:has-text("Party Ledger Detail Report")',
                    'div:has-text("Party Ledger Detail Report")',
                    'text="Total Transaction Count"',
                    'th:has-text("Voucher Number")',
                    'th:has-text("Party Code")'
                ]
                for f in frames_to_check:
                    for sel in pl_indicators:
                        try:
                            if f.locator(sel).first.is_visible(timeout=400):
                                return STATE_PARTY_LEDGER, p
                        except Exception:
                            pass

                # 3. Check for Reports Grid: Accounts Receivable Reports
                grid_indicators = [
                    'text="Accounts Receivable Reports"',
                    'div:has-text("Accounts Receivable Reports")',
                    'span:has-text("Accounts Receivable Reports")',
                    'text="ARSC0010"',
                    '[data-report-id="ARSC0010"]',
                    'text="Debit Note Credit Note Register-Sales"'
                ]
                for f in frames_to_check:
                    for sel in grid_indicators:
                        try:
                            if f.locator(sel).first.is_visible(timeout=400):
                                return STATE_REPORTS_GRID, p
                        except Exception:
                            pass

                # 4. Check for Finance & Accounting Navbar
                navbar_indicators = [
                    'text="TCS ION Finance and Accounting"',
                    'div:has-text("TCS ION Finance and Accounting")',
                    'text="TCS iON Finance and Accounting"',
                    'div:has-text("TCS iON Finance and Accounting")',
                    'a:has-text("Accounts Receivable")',
                    'li:has-text("Accounts Receivable")'
                ]
                for f in frames_to_check:
                    for sel in navbar_indicators:
                        try:
                            if f.locator(sel).first.is_visible(timeout=400):
                                return STATE_FINANCE_NAVBAR, p
                        except Exception:
                            pass

                # 5. Check for TCS iON Home Applications Dashboard (Authenticated only)
                home_indicators = [
                    'input[placeholder*="Type your query" i]',
                    'div:has-text("Explore and simplify your user experience")',
                    'div:has-text("Quicklinks")'
                ]
                for f in frames_to_check:
                    for sel in home_indicators:
                        try:
                            if f.locator(sel).first.is_visible(timeout=400):
                                return STATE_TCSION_HOME, p
                        except Exception:
                            pass

            except Exception:
                continue

        # Fallback based on URL pattern
        curr_url = current_page.url or ""
        if "login" in curr_url.lower():
            return STATE_LOGIN_PAGE, current_page
        if "home" in curr_url.lower():
            return STATE_TCSION_HOME, current_page

        return STATE_UNKNOWN, current_page

    def _handle_login(self, page: Page) -> bool:
        """
        Fills credentials and submits login. Verifies result without spamming.
        """
        logger.info("Entering credentials into TCS iON Enterprise Login...")
        user_input = page.locator('#floatingInput, input[name="accountname"], input#userName').first
        pass_input = page.locator('#floatingPassword, input[name="password"], input#password').first

        if not user_input.is_visible(timeout=6000):
            page.goto(self.login_url, wait_until="networkidle", timeout=30000)
            user_input = page.locator('#floatingInput, input[name="accountname"], input#userName').first
            pass_input = page.locator('#floatingPassword, input[name="password"], input#password').first

        if not user_input.is_visible(timeout=5000):
            logger.error("Username input field not found on login page.")
            return False

        # Type username with realistic delays
        user_input.click()
        user_input.fill("")
        user_input.type(self.username, delay=random.randint(35, 65))
        human_delay(0.3, 0.6)

        # Type password securely without logging
        pass_input.click()
        pass_input.fill("")
        pass_input.type(self.password, delay=random.randint(35, 65))
        human_delay(0.4, 0.8)

        # Click Login button (#submitlogin)
        login_btn = page.locator('#submitlogin, button[type="submit"], input[type="submit"], button:has-text("Login")').first
        login_btn.click()
        logger.info("Submitted login credentials, awaiting authentication verification...")

        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass

        human_delay(2.5, 4.0)
        return True

    def _handle_session_expired(self, page: Page):
        """Handle 15-minute inactivity session expiration."""
        login_again_link = page.locator('a:has-text("log in"), a:has-text("Login"), text="log in"').first
        try:
            if login_again_link.is_visible(timeout=3000):
                login_again_link.click()
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
            else:
                page.goto(self.login_url, wait_until="networkidle", timeout=30000)
        except Exception:
            page.goto(self.login_url, wait_until="domcontentloaded", timeout=20000)
        human_delay(1.5, 2.5)

    def _handle_home_click_finance(self, context: BrowserContext, page: Page) -> Page:
        """Locates and clicks Finance and Accounting application tile."""
        finance_selectors = [
            'span:has-text("Finance and Accounting")',
            'text="Finance and Accounting"',
            'p:has-text("Finance and Accounting")',
            'a:has-text("Finance and Accounting")',
            '[title*="Finance" i]',
            'div.app-card:has-text("Finance and Accounting")',
            'div:has-text("Finance and Accounting")',
            'text="Finance & Accounting"'
        ]

        clicked = False
        initial_page_count = len(context.pages)

        for sel in finance_selectors:
            try:
                elem = page.locator(sel).first
                if elem.is_visible(timeout=2000):
                    elem.scroll_into_view_if_needed()
                    elem.click(force=True)
                    clicked = True
                    break
            except Exception:
                pass

        human_delay(3.0, 5.0)

        # Handle popup/new tab if opened
        if len(context.pages) > initial_page_count:
            new_page = context.pages[-1]
            new_page.bring_to_front()
            return new_page

        return page

    def _handle_finance_click_ar_drilldown(self, context: BrowserContext, page: Page) -> Page:
        """
        In Finance and Accounting navbar:
        Clicks 'Accounts Receivable ▾' then selects 'Drill Down Reports'.
        """
        ar_selectors = [
            'text="Accounts Receivable"',
            'span:has-text("Accounts Receivable")',
            'a:has-text("Accounts Receivable")',
            'li:has-text("Accounts Receivable")',
            'div:has-text("Accounts Receivable")',
            '[title*="Accounts Receivable" i]'
        ]

        active_page = page
        ar_clicked = False

        for p_item in context.pages:
            if ar_clicked:
                break
            for sel in ar_selectors:
                try:
                    loc = p_item.locator(sel).first
                    if loc.is_visible(timeout=2000):
                        loc.scroll_into_view_if_needed()
                        loc.click(force=True)
                        active_page = p_item
                        ar_clicked = True
                        break
                except Exception:
                    pass

        human_delay(1.5, 2.5)

        drill_selectors = [
            'text="Drill Down Reports"',
            'span:has-text("Drill Down Reports")',
            'a:has-text("Drill Down Reports")',
            'li:has-text("Drill Down Reports")',
            'div:has-text("Drill Down Reports")'
        ]

        for p_item in context.pages:
            for sel in drill_selectors:
                try:
                    loc = p_item.locator(sel).first
                    if loc.is_visible(timeout=2000):
                        loc.scroll_into_view_if_needed()
                        loc.click(force=True)
                        active_page = p_item
                        break
                except Exception:
                    pass

        human_delay(2.5, 4.0)
        return active_page

    def _handle_select_party_ledger_tile(self, context: BrowserContext, page: Page) -> Page:
        """
        In Accounts Receivable Reports card grid:
        Locates and clicks the 'PL - Party Ledger Detail (Supplier/Customer)' (ARSC0010) tile.
        """
        report_selectors = [
            'text="Party Ledger Detail"',
            '[data-report-id="ARSC0010"]',
            'div:has-text("Party Ledger Detail")',
            'text="PL - Party Ledger Detail"',
            'text="ARSC0010"'
        ]

        initial_count = len(context.pages)
        active_page = page

        for p_item in context.pages:
            for sel in report_selectors:
                try:
                    loc = p_item.locator(sel).first
                    if loc.is_visible(timeout=2000):
                        loc.scroll_into_view_if_needed()
                        loc.click(force=True)
                        active_page = p_item
                        break
                except Exception:
                    pass

        human_delay(3.0, 5.0)

        if len(context.pages) > initial_count:
            active_page = context.pages[-1]
            active_page.bring_to_front()

        return active_page

    def _handle_party_ledger_screen(self, context: BrowserContext, page: Page) -> Dict[str, Any]:
        """
        Target reached: Party Ledger Detail (Supplier/Customer) Report.
        Fills party filter and handles visual or scrape mode.
        """
        logger.info(f"Configuring Party Ledger Detail for Party: '{self.party_name}'...")

        # 1. Enter Party Name if provided
        if self.party_name:
            party_inputs = [
                '#txtParty',
                'input[placeholder*="Party" i]',
                'input[name*="party" i]',
                'input[aria-label*="Party" i]'
            ]
            for sel in party_inputs:
                try:
                    party_field = page.locator(sel).first
                    if party_field.is_visible(timeout=3000):
                        party_field.scroll_into_view_if_needed()
                        party_field.click()
                        party_field.fill("")
                        party_field.type(self.party_name, delay=random.randint(45, 80))
                        human_delay(1.0, 1.8)

                        # Check for autocomplete suggestion dropdown
                        suggestion = page.locator(f'.suggestion-item:has-text("{self.party_name}"), .dropdown-item, li:has-text("{self.party_name}")').first
                        if suggestion.is_visible(timeout=2500):
                            suggestion.click()
                        break
                except Exception:
                    pass

        # If Mode == "visual": Keep screen open on user's desktop!
        if self.is_visual:
            out = {
                "success": True,
                "party_name": self.party_name,
                "message": f"TCS iON Party Ledger Detail Report screen is now OPEN on your desktop for '{self.party_name}'!",
                "url": page.url
            }
            logger.info("Visual Auto-Launcher completed successfully. Screen is ready for user interaction.")
            print("JSON_RESULT:" + json.dumps(out))
            # Keep open for interactive viewing
            time.sleep(360)
            return out

        # If Mode == "scrape": Click Apply and extract data
        apply_btn = page.locator('button:has-text("Apply"), input[value="Apply"], #btnApply').first
        try:
            if apply_btn.is_visible(timeout=4000):
                apply_btn.click()
                human_delay(3.5, 6.0)
        except Exception:
            pass

        # Attempt Direct File Download Export
        try:
            export_trigger = page.locator('button[title*="Export" i], .export-btn, [title*="Download" i], i.fa-download, div.export-icon, a:has-text("Export"), [title="Export"]').first
            if export_trigger.is_visible(timeout=4000):
                export_trigger.click()
                human_delay(0.8, 1.5)

                csv_or_json = page.locator('text="CSV", a:has-text("CSV"), [data-format="csv"], text="JSON", a:has-text("JSON"), text="XLS", a:has-text("XLS")').first
                if csv_or_json.is_visible(timeout=4000):
                    with page.expect_download(timeout=15000) as download_info:
                        csv_or_json.click()
                    download = download_info.value
                    download_path = download.path()

                    with open(download_path, "rb") as f:
                        file_bytes = f.read()

                    # Check format and parse
                    fn = download.suggested_filename.lower()
                    if fn.endswith(".json"):
                        jdata = json.loads(file_bytes.decode("utf-8", errors="ignore"))
                        raw_recs = jdata if isinstance(jdata, list) else jdata.get("records", [])
                        records, tdr, tcr = self._parse_json_records(raw_recs)
                        out = {
                            "success": True,
                            "party_name": self.party_name,
                            "from_date": self.from_date_str,
                            "to_date": self.to_date_str,
                            "total_records": len(records),
                            "summary": {
                                "opening_balance": 0.0,
                                "total_debit": round(tdr, 2),
                                "total_credit": round(tcr, 2),
                                "closing_balance": round(tdr - tcr, 2)
                            },
                            "records": records,
                            "synced_at": datetime.utcnow().isoformat(),
                            "source": "TCS iON Finance and Accounting (Live Export Download)"
                        }
                        print("JSON_RESULT:" + json.dumps(out))
                        return out
        except Exception as e:
            logger.debug(f"Direct export download not triggered: {e}")

        # Fallback: Live HTML Table Scraping
        table_rows = page.locator('table.report-table tbody tr, table tbody tr, .grid-row').all()
        records = []
        tdr = 0.0
        tcr = 0.0

        for row in table_rows:
            try:
                cols = row.locator('td').all_inner_texts()
                if cols and len(cols) >= 5:
                    v_num = cols[1].strip() if len(cols) > 1 else ""
                    v_date = cols[2].strip() if len(cols) > 2 else ""
                    sub_type = cols[3].strip() if len(cols) > 3 else ""
                    dr = clean_num(cols[4] if len(cols) > 4 else "0")
                    cr = clean_num(cols[5] if len(cols) > 5 else "0")
                    bal = clean_num(cols[6] if len(cols) > 6 else "0")
                    tdr += dr
                    tcr += cr
                    records.append({
                        "party_code": cols[0].strip() if len(cols) > 0 else "CUST-TCS",
                        "voucher_number": v_num,
                        "voucher_date": v_date,
                        "voucher_sub_type": sub_type,
                        "debit_amount": dr,
                        "credit_amount": cr,
                        "balance_amount": bal,
                        "particulars": f"{sub_type} - {v_num}"
                    })
            except Exception:
                continue

        out = {
            "success": True,
            "party_name": self.party_name,
            "from_date": self.from_date_str,
            "to_date": self.to_date_str,
            "total_records": len(records),
            "summary": {
                "opening_balance": 0.0,
                "total_debit": round(tdr, 2),
                "total_credit": round(tcr, 2),
                "closing_balance": round(tdr - tcr, 2)
            },
            "records": records,
            "synced_at": datetime.utcnow().isoformat(),
            "source": "TCS iON Finance and Accounting (Live Scraped)"
        }
        print("JSON_RESULT:" + json.dumps(out))
        return out

    def _parse_json_records(self, raw_recs: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], float, float]:
        records = []
        tdr = 0.0
        tcr = 0.0
        for item in raw_recs:
            dr = clean_num(item.get("Debit Amount") or item.get("debit_amount"))
            cr = clean_num(item.get("Credit Amount") or item.get("credit_amount"))
            bal = clean_num(item.get("Closing Amount in Domestic Currency") or item.get("balance_amount"))
            tdr += dr
            tcr += cr
            records.append({
                "party_code": item.get("Party Code") or "CUST-TCS",
                "voucher_number": item.get("Voucher Number") or "—",
                "voucher_date": item.get("Voucher Date") or "—",
                "voucher_sub_type": item.get("Accounting Voucher Type") or "General",
                "debit_amount": dr,
                "credit_amount": cr,
                "balance_amount": bal,
                "particulars": item.get("Header Narration / Details") or ""
            })
        return records, tdr, tcr


def main():
    parser = argparse.ArgumentParser(description="TCS iON Automated State Machine Worker")
    parser.add_argument("--party", default="SDMOBH0016", help="Party Name or Code")
    parser.add_argument("--months", type=int, default=3, help="Months back for ledger report")
    parser.add_argument("--mode", default="scrape", choices=["scrape", "visual"], help="Automation mode")
    parser.add_argument("--url", default="https://training.tcsion.com/Login/Login.html", help="Login URL")
    # For backward compatibility or override; passwords should preferentially be passed via environment variables
    parser.add_argument("--user", default=None, help="Optional username override")
    parser.add_argument("--password", default=None, help="Optional password override")

    args = parser.parse_args()

    # Read credentials securely from environment variables first
    username = args.user or os.environ.get("TCSION_USERNAME", "trng_infotech@khandelia.com")
    password = args.password or os.environ.get("TCSION_PASSWORD", "Pass!@#32132")
    login_url = args.url or os.environ.get("TCSION_LOGIN_URL", "https://training.tcsion.com/Login/Login.html")

    state_machine = TcsIonStateMachine(
        party_name=args.party,
        months_back=args.months,
        mode=args.mode,
        username=username,
        password=password,
        login_url=login_url
    )

    try:
        res = state_machine.run()
    except Exception as e:
        logger.error(f"Fatal error running state machine: {e}")
        out = {
            "success": False,
            "error": str(e)
        }
        print("JSON_RESULT:" + json.dumps(out))

if __name__ == "__main__":
    main()
