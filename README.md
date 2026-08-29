# Professional CTI (Computer Telephony Integration) + Customer Management CRM

A high-performance, enterprise-grade **Computer Telephony Integration (CTI) and Customer Relationship Management (CRM)** web application engineered for instant caller identification, sub-millisecond phone-indexed search, unified multi-channel customer history, safe Excel data synchronization, and straightforward deployment on **Vercel**.

---

## 🌟 Key Features

1. **⚡ Ultra-Fast Customer Identification (< 10ms Search Latency)**
   - Normalized phone number indexing (`mobile_normalized`, `alternate_mobile_normalized`).
   - Prioritized multi-tier search ranking: Exact Phone $\rightarrow$ Customer ID $\rightarrow$ Email $\rightarrow$ Name / Company $\rightarrow$ Partial match.
   - Global keyboard search activated with `/` or `Ctrl+K`.

2. **📞 Live CTI Screen & Softphone Bar**
   - Telephony Webhook (`POST /api/calls/incoming`) compatible with Asterisk, FreePBX, Twilio, Exotel, and generic SIP servers.
   - Real-time caller screen-pop with matched customer name, VIP status, and previous conversation notes.
   - 1-Click Actions: Open 360° Profile, Quick Call Note, Send Email, End & Log Call.
   - Unknown caller identification with 1-click **Quick Create Customer** pre-filling the incoming number.
   - Built-in interactive incoming call simulator.

3. **📊 Safe Excel Data Onboarding & Sync Engine**
   - Drag & drop `.xlsx` and `.csv` upload wizard.
   - Automatic column header detection and mapping.
   - Pre-import inspection with sample preview.
   - Duplicate detection against existing database records.
   - Safe Update mode: Updates customer details without destroying call or interaction history.
   - Granular row-by-row error ledger with downloadable CSV error report.
   - Pre-generated sample `demo_customers.xlsx` with 25 realistic customer records.

4. **🗂️ Unified Customer 360° Profile & Chronological Timeline**
   - Slide-out profile drawer with full customer metadata.
   - Chronological multi-channel interaction stream combining Phone Calls, Emails, Conversation Notes, WhatsApp, and Follow-ups.
   - Channel filter chips (`All`, `Calls`, `Emails`, `Notes`, `Follow-ups`) and sort toggle.

5. **✉️ Transactional Email Composer**
   - Integrated email composer directly within the customer view.
   - Ready-made email templates: Payment Reminder, Call Follow-up, Welcome Packet, Order Status.
   - Modular email dispatcher supporting Mock, SMTP (Gmail / Outlook), Resend, and SendGrid.
   - Automatically writes sent emails to the customer interaction timeline.

6. **📅 Follow-up & Task Pipeline**
   - Categorized task queues: `Today's Due`, `Overdue`, `Upcoming`, `Completed`.
   - Priority indicators (`Urgent`, `High`, `Medium`, `Low`).
   - 1-click completion toggle and direct click-to-call action.

7. **🔒 Authentication & Role-Based Access Control (RBAC)**
   - Secure bcrypt password hashing and JWT token authorization.
   - Roles: `admin` (Full org analytics, team management, customer reassignment, audit logs) and `employee` (assigned customers, calls, notes, emails, tasks).
   - Instant 1-click demo user switcher in top navigation.

---

## 🏗️ Architecture & Tech Stack

- **Backend**: Python 3.11, FastAPI, Pydantic V2, SQLAlchemy 2.0 ORM, PyJWT, bcrypt, openpyxl.
- **Frontend**: Vanilla HTML5, Modern CSS3 Design System with Glassmorphism and CSS variables, Modular ES6 JavaScript.
- **Database**: PostgreSQL (with connection pooling and indexed search). Gracefully falls back to SQLite for zero-config local testing.
- **Deployment**: Vercel Serverless Function (`api/index.py`, `vercel.json`).

---

## 🚀 Quick Start (Local Setup)

### 1. Prerequisites
- Python 3.10+ installed.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Generate Sample Excel (Optional)
```bash
python scripts/generate_demo_excel.py
```

### 4. Run Development Server
```bash
python run_server.py
```
Open your browser at **`http://localhost:8000`**.

The database schema and **25 demo customer profiles** will automatically initialize on the first launch!

---

## 🔑 Demo Credentials

| Role | Name | Email | Password |
| :--- | :--- | :--- | :--- |
| **Admin** | Admin Shivam | `admin@crm.com` | `admin` |
| **Employee** | Rahul Sharma | `rahul@crm.com` | `rahul` |
| **Employee** | Amit Verma | `amit@crm.com` | `amit` |
| **Employee** | Priya Patel | `priya@crm.com` | `priya` |

> *Tip: Use the **Switch User** dropdown in the top right header to instantly switch roles without re-logging in.*

---

## 🌐 Deploy to Vercel

### Step 1: Push Code to GitHub / GitLab / Bitbucket
```bash
git init
git add .
git commit -m "Initial commit of CTI CRM System"
git remote add origin https://github.com/your-username/cti-customer-management.git
git push -u origin main
```

### Step 2: Import into Vercel
1. Go to [vercel.com](https://vercel.com) and click **"Add New Project"**.
2. Select your repository.
3. In **Environment Variables**, configure:
   - `DATABASE_URL`: Your hosted PostgreSQL connection string (e.g., from [Neon](https://neon.tech), [Supabase](https://supabase.com), or AWS RDS).
   - `JWT_SECRET`: Any random 32+ character secret string.
   - `EMAIL_PROVIDER`: `mock`, `smtp`, or `resend`.
4. Click **Deploy**. Vercel will automatically compile both the FastAPI serverless functions and static frontend.

---

## 📡 REST API Documentation

When the server is running, interactive Swagger API documentation is available at **`http://localhost:8000/docs`**.

### Key Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/auth/login` | Authenticate user and issue JWT |
| `GET` | `/api/customers/search?q=` | Ultra-fast phone, ID, email, or name search |
| `GET` | `/api/customers` | Paginated customer list with filters |
| `GET` | `/api/customers/{id}` | Complete customer profile |
| `POST` | `/api/customers` | Create new customer profile |
| `GET` | `/api/customers/{id}/timeline` | Customer interaction timeline |
| `POST` | `/api/calls/incoming` | Telephony PBX Webhook for incoming calls |
| `POST` | `/api/calls/simulate` | Interactive live incoming call test |
| `POST` | `/api/interactions` | Log conversation note or touchpoint |
| `POST` | `/api/emails/send/{customer_id}` | Dispatch transactional email and write to timeline |
| `GET` | `/api/followups` | Categorized task pipelines (today, overdue, upcoming) |
| `POST` | `/api/imports/preview` | Inspect Excel/CSV headers and preview rows |
| `POST` | `/api/imports/process` | Execute safe customer import with validation |
| `GET` | `/api/dashboard/stats` | Aggregated employee and admin CRM metrics |
| `GET` | `/api/audit` | System audit logs (Admin only) |

---

## 🧪 Running Automated Tests

Run the complete backend test suite:
```bash
pytest tests/test_backend.py -v
```

---

## 📄 License
MIT License. Free for commercial and private enterprise use.
