import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from backend.app.config import settings
from backend.app.database import Base, engine, SessionLocal
from backend.app.routers import (
    auth_router,
    customers_router,
    calls_router,
    interactions_router,
    emails_router,
    followups_router,
    dashboard_router,
    employees_router,
    imports_router,
    audit_router,
    documents_router
)
from backend.app.utils.seed_data import seed_database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables and auto-seed demo data if DB is fresh
    try:
        logger.info("Initializing database schema...")
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            seed_database(db)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
    yield
    # Shutdown
    logger.info("Application shutting down...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Enterprise CTI & Customer Management System for Fast Call Handling and Unified Customer History",
    lifespan=lifespan
)

# Global Unhandled Exception Handler (Logs full stacktrace directly into Render/Cloud logs)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    error_trace = traceback.format_exc()
    logger.error(f"🚨 [RENDER LOG ERROR] {request.method} {request.url.path} -> {exc}\n{error_trace}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal Server Error: {str(exc)}", "path": request.url.path}
    )

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Routers
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(customers_router, prefix=settings.API_V1_STR)
app.include_router(calls_router, prefix=settings.API_V1_STR)
app.include_router(interactions_router, prefix=settings.API_V1_STR)
app.include_router(emails_router, prefix=settings.API_V1_STR)
app.include_router(followups_router, prefix=settings.API_V1_STR)
app.include_router(dashboard_router, prefix=settings.API_V1_STR)
app.include_router(employees_router, prefix=settings.API_V1_STR)
app.include_router(imports_router, prefix=settings.API_V1_STR)
app.include_router(audit_router, prefix=settings.API_V1_STR)
app.include_router(documents_router, prefix=settings.API_V1_STR)

@app.get("/api/health")
def healthcheck():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT
    }

# Mount static images and frontend files if directory exists
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
images_dir = os.path.join(root_dir, "images")
frontend_dir = os.path.join(root_dir, "frontend")

if os.path.exists(images_dir):
    app.mount("/images", StaticFiles(directory=images_dir), name="images")

if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    def serve_frontend_index():
        return FileResponse(os.path.join(frontend_dir, "index.html"))
