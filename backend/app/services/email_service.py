import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from backend.app.config import settings
from backend.app.models.customer import Customer
from backend.app.models.interaction import CustomerInteraction
from backend.app.models.user import User
from backend.app.schemas.email import SendEmailRequest
import logging

logger = logging.getLogger(__name__)

EMAIL_TEMPLATES = {
    "payment_reminder": {
        "subject": "Important: Payment Reminder / Confirmation - {company_or_name}",
        "body": "Dear {name},\n\nThis is a friendly reminder regarding your pending invoice with us. Please let us know if payment has already been initiated, or feel free to reach out if you have any questions.\n\nThank you for your business.\n\nBest regards,\nCustomer Support Team"
    },
    "call_followup": {
        "subject": "Follow-up regarding our recent phone conversation - {company_or_name}",
        "body": "Hi {name},\n\nThank you for taking the time to speak with us today. As discussed, we are actively processing your request.\n\nPlease reply directly to this email if you need any additional assistance.\n\nWarm regards,\n{agent_name}"
    },
    "welcome": {
        "subject": "Welcome to our Services - {company_or_name}",
        "body": "Hello {name},\n\nWe are delighted to welcome you as a valued client! Your dedicated account representative is available to assist with any questions or support needs.\n\nSincerely,\nClient Success Team"
    },
    "order_status": {
        "subject": "Status Update on Your Order/Service Request",
        "body": "Dear {name},\n\nWe are pleased to inform you that your request is currently in progress and moving on schedule. We will notify you immediately once completed.\n\nBest regards,\nOperations Team"
    }
}

class EmailService:
    @staticmethod
    def get_templates() -> Dict[str, Any]:
        return EMAIL_TEMPLATES

    @classmethod
    def test_smtp_connection(
        cls,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_tls: Optional[bool] = None,
        to_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify SMTP credentials and optionally send a test verification email.
        """
        user = smtp_user or settings.SMTP_USER
        password = smtp_password or settings.SMTP_PASSWORD
        host = smtp_host or settings.SMTP_HOST
        port = smtp_port or settings.SMTP_PORT
        tls = smtp_tls if smtp_tls is not None else settings.SMTP_TLS
        recipient = to_email or user

        if not user or not password:
            return {
                "status": "error",
                "auth_failed": True,
                "message": "SMTP User and Password/App Password cannot be empty."
            }

        try:
            logger.info(f"Connecting to SMTP server {host}:{port} for {user}...")
            server = smtplib.SMTP(host, port, timeout=12)
            if tls:
                server.starttls()
            
            server.login(user, password)

            # Send test probe email
            msg = MIMEMultipart()
            msg["From"] = user
            msg["To"] = recipient
            msg["Subject"] = "✅ CRM Email Test Notification - SMTP Connected"
            msg.attach(MIMEText(f"Hello,\n\nThis is a test notification from your CRM system.\n\nSMTP Configuration is active and verified for {user}.\n\nTimestamp: {datetime.now(timezone.utc).isoformat()}", "plain"))
            
            server.sendmail(user, [recipient], msg.as_string())
            server.quit()

            return {
                "status": "success",
                "message": f"SMTP authentication succeeded and test email was delivered to {recipient}!",
                "smtp_user": user,
                "smtp_host": host
            }
        except smtplib.SMTPAuthenticationError as auth_err:
            logger.error(f"SMTP Auth Error: {auth_err}")
            return {
                "status": "error",
                "auth_failed": True,
                "code": 535,
                "message": "Gmail SMTP Authentication Failed: Google requires a 16-character App Password (not your standard Gmail password).",
                "details": str(auth_err),
                "help": "Please enable 2-Step Verification on itchd.kogm@gmail.com, generate a 16-character App Password at https://myaccount.google.com/apppasswords, and paste it here."
            }
        except Exception as e:
            logger.error(f"SMTP General Error: {e}")
            return {
                "status": "error",
                "message": f"SMTP connection error: {str(e)}"
            }

    @classmethod
    def send_email(
        cls,
        db: Session,
        customer_id: int,
        email_req: SendEmailRequest,
        sender_user: Optional[User] = None
    ) -> Dict[str, Any]:
        """
        Dispatch transactional email via configured provider (SMTP, Mock, Resend, Sendgrid)
        and record in customer interaction timeline.
        """
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            raise ValueError("Customer not found")

        provider = settings.EMAIL_PROVIDER.lower()
        success = True
        error_detail = None
        message_id = f"MSG-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        if provider == "smtp":
            try:
                msg = MIMEMultipart()
                msg["From"] = settings.EMAIL_FROM or settings.SMTP_USER
                msg["To"] = email_req.to_email
                msg["Subject"] = email_req.subject
                if email_req.cc:
                    msg["Cc"] = ", ".join(email_req.cc)
                msg.attach(MIMEText(email_req.body, "plain"))

                recipients = [email_req.to_email] + (email_req.cc or []) + (email_req.bcc or [])
                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
                if settings.SMTP_TLS:
                    server.starttls()
                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.EMAIL_FROM or settings.SMTP_USER, recipients, msg.as_string())
                server.quit()
            except smtplib.SMTPAuthenticationError as auth_err:
                success = False
                error_detail = "Gmail requires a 16-character App Password (generate at https://myaccount.google.com/apppasswords)"
                logger.error(f"SMTP Auth Failed: {auth_err}")
            except Exception as e:
                success = False
                error_detail = str(e)
                logger.error(f"SMTP email dispatch failed: {e}")
        elif provider == "resend" and settings.EMAIL_API_KEY:
            try:
                res = requests.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {settings.EMAIL_API_KEY}"},
                    json={
                        "from": settings.EMAIL_FROM,
                        "to": [email_req.to_email],
                        "subject": email_req.subject,
                        "text": email_req.body,
                        "cc": email_req.cc or [],
                        "bcc": email_req.bcc or []
                    },
                    timeout=10
                )
                if res.status_code >= 400:
                    success = False
                    error_detail = res.text
            except Exception as e:
                success = False
                error_detail = str(e)
        else:
            # Mock provider: logs simulation in development/demo mode
            logger.info(f"[MOCK EMAIL DISPATCH] To: {email_req.to_email} | Subject: {email_req.subject}")

        # Automatically log into Customer Interaction Timeline
        interaction = CustomerInteraction(
            customer_id=customer.id,
            user_id=sender_user.id if sender_user else None,
            interaction_type="email",
            direction="outgoing",
            subject=f"Email Sent: {email_req.subject}",
            content=email_req.body,
            meta_info={
                "to": email_req.to_email,
                "cc": email_req.cc or [],
                "bcc": email_req.bcc or [],
                "provider": provider,
                "status": "sent" if success else "failed",
                "error": error_detail,
                "sender_email": sender_user.email if sender_user else (settings.EMAIL_FROM or settings.SMTP_USER)
            },
            interaction_time=datetime.now(timezone.utc)
        )
        db.add(interaction)
        db.commit()

        if not success:
            raise RuntimeError(f"Failed to dispatch email: {error_detail}")

        return {
            "status": "sent",
            "message_id": message_id,
            "recipient": email_req.to_email,
            "subject": email_req.subject,
            "interaction_id": interaction.id,
            "sent_at": interaction.interaction_time
        }

    @classmethod
    def send_assignment_notification(
        cls,
        employee_email: str,
        employee_name: str,
        assigned_customers: List[Any],
        admin_name: str = "System Administrator",
        employee_password: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send automatic email notification to employee when customers are assigned/reassigned.
        Includes employee credentials info (name, email, password), assigned customers table, and CRM login guidance.
        """
        # User Safety Directive: Do NOT send assignment emails to employee email addresses
        logger.info(f"[EMAIL POLICY] Assignment email dispatch to employee {employee_email} bypassed per user directive.")
        return {
            "status": "bypassed",
            "recipient": employee_email,
            "count": len(assigned_customers),
            "message": "Email dispatch to employee email bypassed per user directive."
        }

        count = len(assigned_customers)
        subject = f"🔔 CRM Assignment Update: {count} Customer(s) Assigned to You ({employee_name})"
        pwd_display = employee_password or (employee_email.split('@')[0] if employee_email else "admin")

        # Build customer details table
        cust_rows_text = ""
        cust_rows_html = ""
        for idx, c in enumerate(assigned_customers, 1):
            c_name = getattr(c, 'name', 'N/A')
            c_company = getattr(c, 'company', 'Individual') or 'Individual'
            c_mobile = getattr(c, 'mobile', 'N/A')
            c_type = getattr(c, 'customer_type', 'Standard')
            c_status = getattr(c, 'status', 'Active')
            c_loc = f"{getattr(c, 'city', '')}, {getattr(c, 'state', '')}".strip(', ') or 'India'

            cust_rows_text += f"{idx}. {c_name} ({c_company}) | Phone: {c_mobile} | Tier: {c_type} | Status: {c_status} | Location: {c_loc}\n"
            cust_rows_html += f"""
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px 12px; font-weight: 600; color: #1e293b;">{c_name}</td>
                    <td style="padding: 10px 12px; color: #475569;">{c_company}</td>
                    <td style="padding: 10px 12px; color: #4f46e5; font-weight: 700;">{c_mobile}</td>
                    <td style="padding: 10px 12px;"><span style="background: #eef2ff; color: #4f46e5; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">{c_type}</span></td>
                    <td style="padding: 10px 12px; color: #10b981; font-weight: 600;">{c_status}</td>
                    <td style="padding: 10px 12px; color: #64748b;">{c_loc}</td>
                </tr>
            """

        body_text = f"""Hello {employee_name},

Administrator ({admin_name}) has assigned {count} customer(s) to your CRM account.

LOGIN & ACCESS INFORMATION:
- Employee Name: {employee_name}
- Registered Email / Login ID: {employee_email}
- Login Password: {pwd_display}
- CRM Portal URL: http://localhost:8000

ASSIGNED CUSTOMERS PORTFOLIO ({count} Total):
{cust_rows_text}

HOW TO ACCESS:
1. Open http://localhost:8000 in your browser.
2. Sign in with your email ({employee_email}) and password ({pwd_display}).
3. Open the 'Customers' tab to manage profiles, initiate calls, and schedule follow-ups.

Best regards,
KOGM CTI & Customer Management System
"""

        body_html = f"""
        <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 700px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.06);">
            <div style="background: #1e1b4b; padding: 24px; text-align: center; color: #ffffff;">
                <h2 style="margin: 0; font-size: 22px; font-weight: 700; letter-spacing: 0.5px;">KOGM Customer Management CRM</h2>
                <p style="margin: 6px 0 0 0; color: #a5b4fc; font-size: 14px;">Customer Portfolio Assignment Notification</p>
            </div>
            
            <div style="padding: 24px;">
                <p style="font-size: 15px; color: #1e293b; margin-top: 0;">Hello <strong>{employee_name}</strong>,</p>
                <p style="font-size: 14px; color: #475569; line-height: 1.6;">
                    Administrator <strong>{admin_name}</strong> has assigned <strong>{count} customer profile(s)</strong> to your CRM account. You now have full access to view, call, email, and manage follow-ups for these customers.
                </p>

                <!-- Employee Credentials & Setup Card -->
                <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid #4f46e5; border-radius: 6px; padding: 16px; margin: 20px 0;">
                    <div style="font-weight: 700; color: #1e293b; font-size: 14px; margin-bottom: 10px;">🔐 Your CRM Login Credentials & Portal Info:</div>
                    <table style="font-size: 13px; color: #334155; width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 6px 0; font-weight: 600; width: 160px;">Employee Name:</td>
                            <td style="padding: 6px 0; font-weight: 600; color: #1e293b;">{employee_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: 600;">Registered Email / ID:</td>
                            <td style="padding: 6px 0; color: #4f46e5; font-weight: 700;">{employee_email}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: 600;">Login Password:</td>
                            <td style="padding: 6px 0; color: #0f172a; font-weight: 700; font-family: monospace; background: #e2e8f0; padding: 2px 6px; border-radius: 4px; display: inline-block;">{pwd_display}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: 600;">CRM Portal Link:</td>
                            <td style="padding: 6px 0;"><a href="http://localhost:8000" style="color: #4f46e5; font-weight: 600; text-decoration: underline;">http://localhost:8000</a></td>
                        </tr>
                    </table>
                </div>

                <h4 style="margin: 22px 0 10px 0; color: #0f172a; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px;">📋 Assigned Customers List ({count} Total):</h4>
                <div style="overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 20px; border: 1px solid #e2e8f0; border-radius: 6px;">
                        <thead>
                            <tr style="background: #f1f5f9; text-align: left; color: #475569; border-bottom: 2px solid #cbd5e1;">
                                <th style="padding: 10px 12px;">Customer</th>
                                <th style="padding: 10px 12px;">Company</th>
                                <th style="padding: 10px 12px;">Mobile</th>
                                <th style="padding: 10px 12px;">Tier</th>
                                <th style="padding: 10px 12px;">Status</th>
                                <th style="padding: 10px 12px;">Location</th>
                            </tr>
                        </thead>
                        <tbody>
                            {cust_rows_html}
                        </tbody>
                    </table>
                </div>

                <div style="text-align: center; margin: 25px 0 15px 0;">
                    <a href="http://localhost:8000" style="background: #4f46e5; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px; display: inline-block;">
                        🚀 Open CRM Dashboard
                    </a>
                </div>
            </div>

            <div style="background: #f8fafc; padding: 14px 24px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0;">
                KOGM Enterprise CTI & Customer Management System • Automated Dispatch
            </div>
        </div>
        """

        provider = settings.EMAIL_PROVIDER.lower()
        try:
            if provider == "smtp" and settings.SMTP_USER and settings.SMTP_PASSWORD and cls.is_safe_deliverable_address(employee_email):
                msg = MIMEMultipart("alternative")
                msg["From"] = settings.EMAIL_FROM or settings.SMTP_USER
                msg["To"] = employee_email
                msg["Subject"] = subject
                msg.attach(MIMEText(body_text, "plain"))
                msg.attach(MIMEText(body_html, "html"))

                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=12)
                if settings.SMTP_TLS:
                    server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.EMAIL_FROM or settings.SMTP_USER, [employee_email], msg.as_string())
                server.quit()
                logger.info(f"Assignment notification email sent successfully to {employee_email}")
            else:
                logger.info(f"[SIMULATED ASSIGNMENT EMAIL (Bypass Real SMTP)] To: {employee_email} | Customers: {count}")
            return {"status": "sent", "recipient": employee_email, "count": count}
        except Exception as e:
            logger.warning(f"Could not deliver assignment email to {employee_email}: {e}")
            return {"status": "failed", "error": str(e)}

    @classmethod
    def send_employee_welcome_email(
        cls,
        employee_name: str,
        employee_email: str,
        password: str,
        admin_name: str = "Director / Administrator",
        portal_url: str = "http://localhost:8000"
    ) -> Dict[str, Any]:
        """
        Send professional welcome & onboarding email to newly created employee.
        Communicates that Director/Admin added them, login credentials, portal URL, and advice to change password.
        """
        subject = f"🎉 Welcome to the Team, {employee_name}! Your CRM Account is Ready"
        
        body_text = f"""Hello {employee_name},

Welcome to the team! {admin_name} has registered you as a Team Member on our Customer Management & CTI Portal.

YOUR LOGIN & ACCESS CREDENTIALS:
- Name: {employee_name}
- Registered Email / Login ID: {employee_email}
- Temporary Password: {password}
- CRM Portal Access Link: {portal_url}

IMPORTANT NEXT STEPS:
1. Open {portal_url} in your browser.
2. Log in using your registered email ({employee_email}) and temporary password.
3. For account security, we recommend changing your password from your profile settings after your first login.
4. Access your assigned customer portfolios, manage calls, and schedule follow-ups.

If you have any questions or need assistance getting started, please reach out to {admin_name}.

Best regards,
Customer Relations & Management System
"""

        body_html = f"""
        <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 650px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 14px rgba(0,0,0,0.06);">
            <div style="background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%); padding: 28px; text-align: center; color: #ffffff;">
                <div style="font-size: 32px; margin-bottom: 8px;">🎉</div>
                <h2 style="margin: 0; font-size: 22px; font-weight: 800; letter-spacing: 0.5px;">Welcome to the Team, {employee_name}!</h2>
                <p style="margin: 6px 0 0 0; color: #a5b4fc; font-size: 14px;">Your CRM & Telephony Portal Account Has Been Created</p>
            </div>
            
            <div style="padding: 28px;">
                <p style="font-size: 15px; color: #1e293b; margin-top: 0;">Hello <strong>{employee_name}</strong>,</p>
                <p style="font-size: 14px; color: #475569; line-height: 1.6;">
                    <strong>{admin_name}</strong> has added you to the <strong>Customer Management & Telephony CRM</strong>. You can now log in to view assigned customer accounts, handle incoming/outgoing customer calls, record interaction notes, and manage your daily tasks.
                </p>

                <!-- Credentials Card -->
                <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid #4f46e5; border-radius: 8px; padding: 18px; margin: 22px 0;">
                    <div style="font-weight: 700; color: #1e293b; font-size: 14px; margin-bottom: 12px;">🔐 Your Login Credentials & Access Details:</div>
                    <table style="font-size: 13.5px; color: #334155; width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 6px 0; font-weight: 600; width: 160px; color: #64748b;">Full Name:</td>
                            <td style="padding: 6px 0; font-weight: 700; color: #1e293b;">{employee_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: 600; color: #64748b;">Registered Email / ID:</td>
                            <td style="padding: 6px 0; color: #4f46e5; font-weight: 700;">{employee_email}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: 600; color: #64748b;">Password:</td>
                            <td style="padding: 6px 0; color: #0f172a; font-weight: 700; font-family: monospace; background: #e2e8f0; padding: 3px 8px; border-radius: 4px; display: inline-block;">{password}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: 600; color: #64748b;">Portal Access Link:</td>
                            <td style="padding: 6px 0;"><a href="{portal_url}" style="color: #4f46e5; font-weight: 600; text-decoration: underline;">{portal_url}</a></td>
                        </tr>
                    </table>
                </div>

                <!-- Security Tip -->
                <div style="background: #fffbeb; border: 1px solid #fef3c7; border-left: 4px solid #f59e0b; border-radius: 6px; padding: 12px 14px; font-size: 13px; color: #92400e; margin-bottom: 24px;">
                    🛡️ <strong>Security Tip:</strong> For account safety, please change your password after logging in for the first time by visiting your profile settings.
                </div>

                <div style="text-align: center; margin: 24px 0 10px 0;">
                    <a href="{portal_url}" style="background: #4f46e5; color: #ffffff; padding: 12px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 14px; display: inline-block; box-shadow: 0 2px 6px rgba(79, 70, 229, 0.3);">
                        🚀 Access CRM Portal
                    </a>
                </div>
            </div>

            <div style="background: #f8fafc; padding: 14px 24px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0;">
                Enterprise CTI & Customer Management System • Automated Staff Onboarding
            </div>
        </div>
        """
    @classmethod
    def is_safe_deliverable_address(cls, email: Optional[str]) -> bool:
        """
        Prevents sending real SMTP network packets to fake/test/dummy domains
        which cause 'Delivery incomplete' bounce errors in Gmail.
        """
        if not email or "@" not in email:
            return False
        clean_email = email.lower().strip()
        domain = clean_email.split("@")[-1]

        # Blacklist non-existent / dummy test domains
        dummy_domains = {
            "company.com", "example.com", "test.com", "test.org", 
            "invalid", "sample.com", "dummy.com", "crm.com", "testcrm.com"
        }
        if domain in dummy_domains or domain.endswith(".test") or domain.endswith(".example"):
            return False

        dummy_exact = {
            "sunil.varma@company.com", "deepak.c@company.com", "karan.m@company.com"
        }
        if clean_email in dummy_exact:
            return False

        return True

    @classmethod
    def send_employee_welcome_email(
        cls,
        employee_name: str,
        employee_email: str,
        password: str,
        admin_name: str = "Director / Administrator",
        portal_url: str = "http://localhost:8000"
    ) -> Dict[str, Any]:
        """
        Send professional welcome & onboarding email to newly created employee.
        Communicates that Director/Admin added them, login credentials, portal URL, and advice to change password.
        """
        subject = f"🎉 Welcome to the Team, {employee_name}! Your CRM Account is Ready"
        
        body_text = f"""Hello {employee_name},

Welcome to the team! {admin_name} has registered you as a Team Member on our Customer Management & CTI Portal.

YOUR LOGIN & ACCESS CREDENTIALS:
- Name: {employee_name}
- Registered Email / Login ID: {employee_email}
- Temporary Password: {password}
- CRM Portal Access Link: {portal_url}

IMPORTANT NEXT STEPS:
1. Open {portal_url} in your browser.
2. Log in using your registered email ({employee_email}) and temporary password.
3. For account security, we recommend changing your password from your profile settings after your first login.
4. Access your assigned customer portfolios, manage calls, and schedule follow-ups.

If you have any questions or need assistance getting started, please reach out to {admin_name}.

Best regards,
Customer Relations & Management System
"""

        body_html = f"""
        <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 650px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 14px rgba(0,0,0,0.06);">
            <div style="background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%); padding: 28px; text-align: center; color: #ffffff;">
                <div style="font-size: 32px; margin-bottom: 8px;">🎉</div>
                <h2 style="margin: 0; font-size: 22px; font-weight: 800; letter-spacing: 0.5px;">Welcome to the Team, {employee_name}!</h2>
                <p style="margin: 6px 0 0 0; color: #a5b4fc; font-size: 14px;">Your CRM & Telephony Portal Account Has Been Created</p>
            </div>
            
            <div style="padding: 28px;">
                <p style="font-size: 15px; color: #1e293b; margin-top: 0;">Hello <strong>{employee_name}</strong>,</p>
                <p style="font-size: 14px; color: #475569; line-height: 1.6;">
                    <strong>{admin_name}</strong> has added you to the <strong>Customer Management & Telephony CRM</strong>. You can now log in to view assigned customer accounts, handle incoming/outgoing customer calls, record interaction notes, and manage your daily tasks.
                </p>

                <!-- Credentials Card -->
                <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid #4f46e5; border-radius: 8px; padding: 18px; margin: 22px 0;">
                    <div style="font-weight: 700; color: #1e293b; font-size: 14px; margin-bottom: 12px;">🔐 Your Login Credentials & Access Details:</div>
                    <table style="font-size: 13.5px; color: #334155; width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 6px 0; font-weight: 600; width: 160px; color: #64748b;">Full Name:</td>
                            <td style="padding: 6px 0; font-weight: 700; color: #1e293b;">{employee_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: 600; color: #64748b;">Registered Email / ID:</td>
                            <td style="padding: 6px 0; color: #4f46e5; font-weight: 700;">{employee_email}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: 600; color: #64748b;">Password:</td>
                            <td style="padding: 6px 0; color: #0f172a; font-weight: 700; font-family: monospace; background: #e2e8f0; padding: 3px 8px; border-radius: 4px; display: inline-block;">{password}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: 600; color: #64748b;">Portal Access Link:</td>
                            <td style="padding: 6px 0;"><a href="{portal_url}" style="color: #4f46e5; font-weight: 600; text-decoration: underline;">{portal_url}</a></td>
                        </tr>
                    </table>
                </div>

                <!-- Security Tip -->
                <div style="background: #fffbeb; border: 1px solid #fef3c7; border-left: 4px solid #f59e0b; border-radius: 6px; padding: 12px 14px; font-size: 13px; color: #92400e; margin-bottom: 24px;">
                    🛡️ <strong>Security Tip:</strong> For account safety, please change your password after logging in for the first time by visiting your profile settings.
                </div>

                <div style="text-align: center; margin: 24px 0 10px 0;">
                    <a href="{portal_url}" style="background: #4f46e5; color: #ffffff; padding: 12px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 14px; display: inline-block; box-shadow: 0 2px 6px rgba(79, 70, 229, 0.3);">
                        🚀 Access CRM Portal
                    </a>
                </div>
            </div>

            <div style="background: #f8fafc; padding: 14px 24px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0;">
                Enterprise CTI & Customer Management System • Automated Staff Onboarding
            </div>
        </div>
        """

        provider = settings.EMAIL_PROVIDER.lower()
        try:
            if provider == "smtp" and settings.SMTP_USER and settings.SMTP_PASSWORD and cls.is_safe_deliverable_address(employee_email):
                msg = MIMEMultipart("alternative")
                msg["From"] = settings.EMAIL_FROM or settings.SMTP_USER
                msg["To"] = employee_email
                msg["Subject"] = subject
                msg.attach(MIMEText(body_text, "plain"))
                msg.attach(MIMEText(body_html, "html"))

                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=12)
                if settings.SMTP_TLS:
                    server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.EMAIL_FROM or settings.SMTP_USER, [employee_email], msg.as_string())
                server.quit()
                logger.info(f"Welcome onboarding email sent successfully to {employee_email}")
            else:
                logger.info(f"[SIMULATED WELCOME EMAIL (Bypass Real SMTP)] To: {employee_email} | Password Provided")
            return {"status": "sent", "recipient": employee_email}
        except Exception as e:
            logger.warning(f"Could not deliver welcome email to {employee_email}: {e}")
            return {"status": "failed", "error": str(e)}

    @classmethod
    def send_registration_confirmation_email(
        cls,
        employee_name: str,
        employee_email: str,
        portal_url: str = "http://localhost:8000"
    ) -> Dict[str, Any]:
        """
        Send registration confirmation email to self-registered employee.
        """
        subject = f"✅ Registration Successful - Welcome to CRM Portal, {employee_name}"
        
        body_text = f"""Hello {employee_name},

Thank you for registering on our Customer Management & CTI Portal. Your employee account has been successfully created.

ACCOUNT INFORMATION:
- Name: {employee_name}
- Registered Email / Login ID: {employee_email}
- Role: Employee
- Portal URL: {portal_url}

You can now log in at {portal_url} using your registered email and the password you chose during registration.

Best regards,
Customer Relations & Management System
"""

        body_html = f"""
        <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 650px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 14px rgba(0,0,0,0.06);">
            <div style="background: linear-gradient(135deg, #065f46 0%, #047857 100%); padding: 28px; text-align: center; color: #ffffff;">
                <div style="font-size: 32px; margin-bottom: 8px;">✅</div>
                <h2 style="margin: 0; font-size: 22px; font-weight: 800; letter-spacing: 0.5px;">Account Registration Successful!</h2>
                <p style="margin: 6px 0 0 0; color: #a7f3d0; font-size: 14px;">Welcome to the CRM Team, {employee_name}</p>
            </div>
            
            <div style="padding: 28px;">
                <p style="font-size: 15px; color: #1e293b; margin-top: 0;">Hello <strong>{employee_name}</strong>,</p>
                <p style="font-size: 14px; color: #475569; line-height: 1.6;">
                    Your employee account has been successfully registered. You can now log into the portal to access your dashboard, handle assigned customer interactions, and track follow-ups.
                </p>

                <!-- Details Card -->
                <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid #10b981; border-radius: 8px; padding: 18px; margin: 22px 0;">
                    <div style="font-weight: 700; color: #1e293b; font-size: 14px; margin-bottom: 12px;">📋 Account Summary:</div>
                    <table style="font-size: 13.5px; color: #334155; width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 6px 0; font-weight: 600; width: 160px; color: #64748b;">Full Name:</td>
                            <td style="padding: 6px 0; font-weight: 700; color: #1e293b;">{employee_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: 600; color: #64748b;">Registered Email:</td>
                            <td style="padding: 6px 0; color: #10b981; font-weight: 700;">{employee_email}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: 600; color: #64748b;">Assigned Role:</td>
                            <td style="padding: 6px 0; font-weight: 600; color: #1e293b;">Employee</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: 600; color: #64748b;">Portal Access Link:</td>
                            <td style="padding: 6px 0;"><a href="{portal_url}" style="color: #10b981; font-weight: 600; text-decoration: underline;">{portal_url}</a></td>
                        </tr>
                    </table>
                </div>

                <div style="text-align: center; margin: 24px 0 10px 0;">
                    <a href="{portal_url}" style="background: #10b981; color: #ffffff; padding: 12px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 14px; display: inline-block;">
                        🚀 Open Dashboard
                    </a>
                </div>
            </div>

            <div style="background: #f8fafc; padding: 14px 24px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0;">
                Enterprise CTI & Customer Management System • Automated Confirmation
            </div>
        </div>
        """

        provider = settings.EMAIL_PROVIDER.lower()
        try:
            if provider == "smtp" and settings.SMTP_USER and settings.SMTP_PASSWORD and cls.is_safe_deliverable_address(employee_email):
                msg = MIMEMultipart("alternative")
                msg["From"] = settings.EMAIL_FROM or settings.SMTP_USER
                msg["To"] = employee_email
                msg["Subject"] = subject
                msg.attach(MIMEText(body_text, "plain"))
                msg.attach(MIMEText(body_html, "html"))

                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=12)
                if settings.SMTP_TLS:
                    server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.EMAIL_FROM or settings.SMTP_USER, [employee_email], msg.as_string())
                server.quit()
                logger.info(f"Registration confirmation email sent to {employee_email}")
            else:
                logger.info(f"[SIMULATED REGISTRATION EMAIL (Bypass Real SMTP)] To: {employee_email}")
            return {"status": "sent", "recipient": employee_email}
        except Exception as e:
            logger.warning(f"Could not deliver registration confirmation email to {employee_email}: {e}")
            return {"status": "failed", "error": str(e)}


