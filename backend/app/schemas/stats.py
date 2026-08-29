from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

class KPICards(BaseModel):
    total_customers: int
    calls_today: int
    calls_this_week: int
    calls_this_month: int
    total_calls_all_time: Optional[int] = 0
    current_month_name: Optional[str] = "August"
    current_year: Optional[int] = 2026
    current_date_formatted: Optional[str] = "29 Aug 2026"
    current_month_year_formatted: Optional[str] = "August 2026"
    emails_sent_today: int
    pending_followups: int
    overdue_followups: int
    completed_followups: int
    avg_duration_today_seconds: Optional[int] = 0
    avg_duration_today_formatted: Optional[str] = "00:00 min"
    total_talk_time_today_seconds: Optional[int] = 0
    total_talk_time_today_formatted: Optional[str] = "0s"
    call_connect_rate_percent: Optional[float] = 100.0
    answered_calls_today: Optional[int] = 0
    missed_calls_today: Optional[int] = 0

class EmployeePerformance(BaseModel):
    user_id: int
    full_name: str
    email: str
    role: str
    phone: Optional[str] = None
    allowed_caller_id: Optional[str] = None
    designation: Optional[str] = "Employee"
    assigned_customers_count: int
    calls_logged: int
    interactions_logged: int
    followups_completed: int

class EmployeeCallingPerformance(BaseModel):
    user_id: int
    full_name: str
    email: str
    designation: Optional[str] = "Employee"
    allowed_caller_id: Optional[str] = None
    total_calls: int
    outbound_calls: int
    inbound_calls: int
    connected_calls: int
    missed_calls: int
    connect_rate_percent: float
    avg_duration_seconds: int
    avg_duration_formatted: str
    total_talk_time_seconds: int
    total_talk_time_formatted: str

class TodayCallingSummary(BaseModel):
    total_calls: int
    outbound_calls: int
    inbound_calls: int
    connected_calls: int
    missed_calls: int
    connect_rate_percent: float
    avg_call_duration_seconds: int
    avg_call_duration_formatted: str
    total_talk_time_seconds: int
    total_talk_time_formatted: str
    most_calls_employee: Optional[Dict[str, Any]] = None
    least_calls_employee: Optional[Dict[str, Any]] = None
    most_connected_employee: Optional[Dict[str, Any]] = None
    top_performer: Optional[Dict[str, Any]] = None

class DashboardStatsResponse(BaseModel):
    role: str
    user_name: str
    kpis: KPICards
    recent_calls: List[Dict[str, Any]]
    recent_interactions: List[Dict[str, Any]]
    today_followups: List[Dict[str, Any]]
    overdue_followups: List[Dict[str, Any]]
    team_activity: Optional[List[EmployeePerformance]] = None
    call_trends: Optional[List[Dict[str, Any]]] = None
    calling_summary_today: Optional[TodayCallingSummary] = None
    employee_calling_today: Optional[List[EmployeeCallingPerformance]] = None
    smartflo_token: Optional[Dict[str, Any]] = None

class ImportSummaryResponse(BaseModel):
    job_id: int
    filename: str
    total_rows: int
    imported_count: int
    updated_count: int
    duplicate_count: int
    error_count: int
    errors: List[Dict[str, Any]]
    status: str
    created_at: datetime
