import os
import io
import sys
import csv
import json
import time
import random
import argparse
from datetime import datetime, timedelta
from typing import Dict, Any, List

try:
    import openpyxl
except ImportError:
    openpyxl = None

from playwright.sync_api import sync_playwright

def human_delay(min_sec: float = 1.0, max_sec: float = 2.5):
    time.sleep(random.uniform(min_sec, max_sec))

def clean_num(val_str: Any) -> float:
    if val_str is None:
        return 0.0
    if isinstance(val_str, (int, float)):
        return float(val_str)
    try:
        cleaned = str(val_str).replace(",", "").replace("₹", "").replace("Dr", "").replace("Cr", "").strip()
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0

def run_tcsion_worker(party_name: str, months_back: int, mode: str, username: str, password: str, login_url: str):
    from_date_dt = datetime.now() - timedelta(days=months_back * 30)
    to_date_dt = datetime.now()
    from_date_num = from_date_dt.strftime("%d/%m/%Y")
    to_date_num = to_date_dt.strftime("%d/%m/%Y")

    profile_dir = os.path.abspath("backend/cache/tcs_browser_profile")
    os.makedirs(profile_dir, exist_ok=True)

    is_visual = (mode == "visual")
    is_headless = not is_visual

    with sync_playwright() as p:
        args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled"
        ]
        if is_visual:
            args.append("--start-maximized")

        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=is_headless,
            args=args,
            no_viewport=is_visual,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            accept_downloads=True
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        try:
            # Step 1: Navigate directly to Login URL
            page.goto("https://training.tcsion.com/Login/Login.html", wait_until="networkidle", timeout=45000)
            human_delay(1.0, 2.0)

            # If session expired page is shown, redirect to login
            if "sessionExpired" in page.url:
                login_again_link = page.locator('a:has-text("log in"), a:has-text("Login"), text="log in"').first
                if login_again_link.is_visible(timeout=3000):
                    login_again_link.click()
                else:
                    page.goto("https://training.tcsion.com/Login/Login.html", wait_until="networkidle")
                human_delay(1.0, 2.0)

            # Check if login form inputs are present
            user_input = page.locator('#floatingInput, input#userName, input[name="accountname"], input[type="text"]').first
            if user_input.is_visible(timeout=6000):
                pass_input = page.locator('#floatingPassword, input#password, input[name="password"], input[type="password"]').first

                user_input.click()
                user_input.fill("")
                user_input.type(username, delay=random.randint(35, 65))
                human_delay(0.3, 0.6)

                pass_input.click()
                pass_input.fill("")
                pass_input.type(password, delay=random.randint(35, 65))
                human_delay(0.4, 0.8)

                login_btn = page.locator('button[type="submit"], input[type="submit"], button:has-text("Log In"), button:has-text("Login")').first
                login_btn.click()
                human_delay(4.0, 6.0)

                if "loginfailure" in page.url or "already logged" in page.content():
                    out = {
                        "success": False,
                        "cooldown": True,
                        "error": "You are already logged into TCS iON with this ID. Please wait 2 minutes."
                    }
                    print("JSON_RESULT:" + json.dumps(out))
                    return

            # Step 2: Click Finance and Accounting Tile
            finance_selectors = [
                'text="Finance and Accounting"',
                'text="Finance & Accounting"',
                'div:has-text("Finance and Accounting")',
                'div:has-text("Finance & Accounting")',
                'span:has-text("Finance and Accounting")',
                'span:has-text("Finance & Accounting")',
                'a:has-text("Finance and Accounting")',
                'a:has-text("Finance & Accounting")',
                '[title*="Finance" i]'
            ]

            for sel in finance_selectors:
                try:
                    elem = page.locator(sel).first
                    if elem.is_visible(timeout=2000):
                        elem.scroll_into_view_if_needed()
                        elem.click(force=True)
                        break
                except Exception:
                    pass

            human_delay(3.0, 5.0)

            if len(context.pages) > 1:
                page = context.pages[-1]
                page.bring_to_front()
                human_delay(1.5, 2.5)

            # Step 3: Top Nav -> Accounts Receivable -> Drill Down Reports
            ar_selectors = [
                'text="Accounts Receivable"',
                'span:has-text("Accounts Receivable")',
                'a:has-text("Accounts Receivable")',
                'li:has-text("Accounts Receivable")',
                'div:has-text("Accounts Receivable")',
                '[title*="Accounts Receivable" i]'
            ]

            ar_clicked = False
            for p_item in context.pages:
                if ar_clicked:
                    break
                for sel in ar_selectors:
                    try:
                        loc = p_item.locator(sel).first
                        if loc.is_visible(timeout=1500):
                            loc.scroll_into_view_if_needed()
                            loc.click(force=True)
                            page = p_item
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
                        if loc.is_visible(timeout=1500):
                            loc.scroll_into_view_if_needed()
                            loc.click(force=True)
                            page = p_item
                            break
                    except Exception:
                        pass

            human_delay(2.0, 3.5)

            # Step 4: Click PL - Party Ledger Detail Report (ARSC0010)
            report_selectors = [
                'text="Party Ledger Detail"',
                '[data-report-id="ARSC0010"]',
                'div:has-text("Party Ledger Detail")',
                'text="PL - Party Ledger Detail"',
                'text="ARSC0010"'
            ]

            for p_item in context.pages:
                for sel in report_selectors:
                    try:
                        loc = p_item.locator(sel).first
                        if loc.is_visible(timeout=2000):
                            loc.scroll_into_view_if_needed()
                            loc.click(force=True)
                            page = p_item
                            break
                    except Exception:
                        pass

            human_delay(2.5, 4.0)

            if len(context.pages) > 1:
                page = context.pages[-1]
                page.bring_to_front()

            # Step 5: Fill Party Name & Filters
            try:
                party_input = page.locator('input[placeholder*="Party" i], input[name*="party" i], #txtParty').first
                if party_input.is_visible(timeout=5000):
                    party_input.scroll_into_view_if_needed()
                    party_input.click()
                    party_input.fill("")
                    party_input.type(party_name, delay=random.randint(45, 85))
                    human_delay(1.0, 1.8)
                    suggestion = page.locator(f'.suggestion-item:has-text("{party_name}"), .dropdown-item, li:has-text("{party_name}")').first
                    if suggestion.is_visible(timeout=3000):
                        suggestion.click()
            except Exception:
                pass

            if is_visual:
                # Mode visual: Leave the screen open for the user!
                out = {
                    "success": True,
                    "party_name": party_name,
                    "message": f"TCS iON Party Ledger Detail Report screen is now open on your desktop for '{party_name}'!",
                    "url": page.url
                }
                print("JSON_RESULT:" + json.dumps(out))
                # Keep open for interactive viewing
                time.sleep(300)
                return

            # Mode Scrape: Click Apply and extract / download
            apply_btn = page.locator('button:has-text("Apply"), input[value="Apply"], #btnApply').first
            if apply_btn.is_visible(timeout=5000):
                apply_btn.click()
                human_delay(3.5, 6.0)

            # Direct Export Download Attempt
            try:
                export_trigger = page.locator('button[title*="Export" i], .export-btn, [title*="Download" i], i.fa-download, div.export-icon, a:has-text("Export"), [title="Export"]').first
                if export_trigger.is_visible(timeout=5000):
                    export_trigger.click()
                    human_delay(0.8, 1.5)
                    csv_or_xls = page.locator('text="CSV", a:has-text("CSV"), [data-format="csv"], text="JSON", a:has-text("JSON"), text="XLS", a:has-text("XLS")').first
                    if csv_or_xls.is_visible(timeout=4000):
                        with page.expect_download(timeout=15000) as download_info:
                            csv_or_xls.click()
                        download = download_info.value
                        download_path = download.path()
                        with open(download_path, "rb") as f:
                            file_bytes = f.read()

                        # Parse file content
                        # Simple CSV / JSON reader
                        fn = download.suggested_filename
                        if fn.endswith(".json"):
                            jdata = json.loads(file_bytes.decode("utf-8", errors="ignore"))
                            raw_recs = jdata if isinstance(jdata, list) else jdata.get("records", [])
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
                            out = {
                                "success": True,
                                "party_name": party_name,
                                "from_date": from_date_num,
                                "to_date": to_date_num,
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
                            return
            except Exception:
                pass

            # Table HTML Extraction
            table_rows = page.locator('table.report-table tbody tr, table tbody tr, .grid-row').all()
            records = []
            tdr = 0.0
            tcr = 0.0
            for row in table_rows:
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

            out = {
                "success": True,
                "party_name": party_name,
                "from_date": from_date_num,
                "to_date": to_date_num,
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

        except Exception as e:
            out = {
                "success": False,
                "error": str(e)
            }
            print("JSON_RESULT:" + json.dumps(out))
        finally:
            if not is_visual:
                context.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--party", default="SDMOBH0016")
    parser.add_argument("--months", type=int, default=3)
    parser.add_argument("--mode", default="scrape", choices=["scrape", "visual"])
    parser.add_argument("--user", default="trng_infotech@khandelia.com")
    parser.add_argument("--password", default="Pass!@#32132")
    parser.add_argument("--url", default="https://training.tcsion.com/Login/Login.html")
    args = parser.parse_args()

    run_tcsion_worker(
        party_name=args.party,
        months_back=args.months,
        mode=args.mode,
        username=args.user,
        password=args.password,
        login_url=args.url
    )
