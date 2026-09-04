import re
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.config import settings
import logging

logger = logging.getLogger(__name__)

# Normalize DATABASE_URL for SQLAlchemy if needed (e.g., postgres:// -> postgresql://)
db_url = settings.DATABASE_URL.strip()
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# Remove problematic channel_binding query parameter if present (causes hanging with psycopg2 / serverless poolers)
if "channel_binding=" in db_url:
    db_url = re.sub(r'[?&]channel_binding=[^&]+', '', db_url)
    if '?' not in db_url and '&' in db_url:
        db_url = db_url.replace('&', '?', 1)

# Connection pooling configurations based on dialect
if db_url.startswith("sqlite"):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False, "timeout": 30}
    )
else:
    # PostgreSQL configuration with connection pooling, timeout, and health check
    engine = create_engine(
        db_url,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_pre_ping=True,
        pool_recycle=300,  # recycle connections after 5 mins for serverless
        connect_args={
            "connect_timeout": 10,
            "application_name": "khandelia_cti_crm"
        }
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def ensure_schema_columns(target_engine):
    """Safely ensure newly added columns exist in SQLite/Postgres without data loss."""
    from sqlalchemy import inspect, text
    try:
        inspector = inspect(target_engine)
        tables = inspector.get_table_names()
        with target_engine.connect() as conn:
            # 1. users table
            if "users" in tables:
                user_cols = [c["name"] for c in inspector.get_columns("users")]
                if "allowed_caller_id" not in user_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN allowed_caller_id VARCHAR(100)"))
                if "vid" not in user_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN vid VARCHAR(100)"))
                if "phone" not in user_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN phone VARCHAR(50)"))
                if "agent_id" not in user_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN agent_id VARCHAR(50)"))
                if "intercom" not in user_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN intercom VARCHAR(50)"))
                if "designation" not in user_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN designation VARCHAR(100)"))
                if "tcs_username" not in user_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN tcs_username VARCHAR(255)"))
                if "tcs_password" not in user_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN tcs_password VARCHAR(255)"))
                conn.commit()

            # 2. calls table
            if "calls" in tables:
                call_cols = [c["name"] for c in inspector.get_columns("calls")]
                new_call_cols = {
                    "uuid": "VARCHAR(100)",
                    "call_to_number": "VARCHAR(50)",
                    "operator": "VARCHAR(100)",
                    "circle": "VARCHAR(100)",
                    "agent_name": "VARCHAR(100)",
                    "agent_number": "VARCHAR(50)",
                    "hangup_cause": "VARCHAR(150)",
                    "reason_key": "VARCHAR(150)",
                    "hangup_code": "VARCHAR(50)",
                    "hangup_key": "VARCHAR(100)",
                    "billsec": "INTEGER DEFAULT 0",
                    "provider": "VARCHAR(50) DEFAULT 'smartflo'"
                }
                for col_name, col_type in new_call_cols.items():
                    if col_name not in call_cols:
                        conn.execute(text(f"ALTER TABLE calls ADD COLUMN {col_name} {col_type}"))
                conn.commit()

            # 3. customers table (Customer Intelligence)
            if "customers" in tables:
                cust_cols = [c["name"] for c in inspector.get_columns("customers")]
                if "rating" not in cust_cols:
                    conn.execute(text("ALTER TABLE customers ADD COLUMN rating INTEGER DEFAULT 0"))
                if "category" not in cust_cols:
                    conn.execute(text("ALTER TABLE customers ADD COLUMN category VARCHAR(50) DEFAULT 'Regular'"))
                conn.commit()

            # 4. customer_rating_history table
            if "customer_rating_history" not in tables:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS customer_rating_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        customer_id INTEGER NOT NULL,
                        previous_rating INTEGER,
                        new_rating INTEGER NOT NULL,
                        previous_category VARCHAR(50),
                        new_category VARCHAR(50) NOT NULL,
                        user_id INTEGER,
                        notes TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_cust_rating_hist_cust ON customer_rating_history(customer_id, created_at)"))
                conn.commit()
    except Exception as e:
        logger.warning(f"Schema column check: {e}")

# Run schema sync
ensure_schema_columns(engine)

def get_db():
    """FastAPI Dependency for obtaining transactional database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
