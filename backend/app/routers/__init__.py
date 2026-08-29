from backend.app.routers.auth import router as auth_router
from backend.app.routers.customers import router as customers_router
from backend.app.routers.calls import router as calls_router
from backend.app.routers.interactions import router as interactions_router
from backend.app.routers.emails import router as emails_router
from backend.app.routers.followups import router as followups_router
from backend.app.routers.dashboard import router as dashboard_router
from backend.app.routers.employees import router as employees_router
from backend.app.routers.imports import router as imports_router
from backend.app.routers.audit import router as audit_router
from backend.app.routers.documents import router as documents_router

__all__ = [
    "auth_router",
    "customers_router",
    "calls_router",
    "interactions_router",
    "emails_router",
    "followups_router",
    "dashboard_router",
    "employees_router",
    "imports_router",
    "audit_router",
    "documents_router"
]
