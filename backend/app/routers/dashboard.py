from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, or_
from datetime import datetime, timezone, timedelta
from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.customer import Customer
from backend.app.models.call import Call
from backend.app.models.interaction import CustomerInteraction
from backend.app.models.follow_up import FollowUp
from backend.app.schemas.stats import (
    DashboardStatsResponse, KPICards, EmployeePerformance,
    TodayCallingSummary, EmployeeCallingPerformance
)
from backend.app.utils.security import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard & Analytics"])

@router.get("/stats", response_model=DashboardStatsResponse)
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve comprehensive CRM and CTI analytics for employee or admin view."""
    # Real-Time Indian Standard Time (IST UTC+05:30)
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(timezone.utc).astimezone(ist_tz)
    
    today_start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_ist.astimezone(timezone.utc)
    week_start_utc = (today_start_ist - timedelta(days=now_ist.weekday())).astimezone(timezone.utc)
    month_start_utc = today_start_ist.replace(day=1).astimezone(timezone.utc)

    month_name = now_ist.strftime("%B")
    year_num = now_ist.year
    date_formatted = now_ist.strftime("%d %b %Y")
    month_year_formatted = now_ist.strftime("%B %Y")

    is_admin = current_user.role == "admin"

    # Base query filters
    cust_query = db.query(Customer).filter(Customer.is_archived == False)
    call_query = db.query(Call)
    inter_query = db.query(CustomerInteraction)
    fu_query = db.query(FollowUp)

    if not is_admin:
        # Employee view: personalize stats
        cust_query = cust_query.filter(Customer.assigned_employee_id == current_user.id)
        user_cid = current_user.allowed_caller_id or current_user.vid
        if user_cid:
            norm_cid = user_cid.replace("+", "").lstrip("0")
            call_query = call_query.filter(
                (Call.user_id == current_user.id) |
                (Call.call_to_number == user_cid) |
                (Call.call_to_number.like(f"%{norm_cid[-10:]}")) |
                (Call.agent_number == user_cid) |
                (Call.agent_number.like(f"%{norm_cid[-10:]}"))
            )
        else:
            call_query = call_query.filter(Call.user_id == current_user.id)
        inter_query = inter_query.filter(CustomerInteraction.user_id == current_user.id)
        fu_query = fu_query.filter(
            or_(
                FollowUp.assigned_user_id == current_user.id,
                FollowUp.customer.has(Customer.assigned_employee_id == current_user.id)
            )
        )

    # 1. KPI Counts & Real Telephony Calculations
    total_customers = cust_query.count()
    today_calls_list = call_query.filter(Call.start_time >= today_start_utc).all()
    calls_today = len(today_calls_list)
    calls_this_week = call_query.filter(Call.start_time >= week_start_utc).count()
    calls_this_month = call_query.filter(Call.start_time >= month_start_utc).count()
    total_calls_all_time = call_query.count()
    
    emails_today = inter_query.filter(
        CustomerInteraction.interaction_type == "email",
        CustomerInteraction.interaction_time >= today_start_utc
    ).count()

    pending_fu = fu_query.filter(FollowUp.status.in_(["Pending", "In Progress"])).count()
    overdue_fu = fu_query.filter(
        FollowUp.status.in_(["Pending", "In Progress"]),
        FollowUp.due_date < today_start_utc
    ).count()
    completed_fu = fu_query.filter(FollowUp.status == "Completed").count()

    # Dynamic Real Telephony Metrics
    answered_calls_today = sum(1 for c in today_calls_list if c.status == "completed" or (c.duration_seconds or 0) > 0)
    missed_calls_today = sum(1 for c in today_calls_list if c.status == "missed" and (c.duration_seconds or 0) == 0)
    total_talk_secs = sum(c.duration_seconds or 0 for c in today_calls_list if c.status == "completed" or (c.duration_seconds or 0) > 0)

    if calls_today > 0 and answered_calls_today > 0:
        avg_talk_secs = total_talk_secs // answered_calls_today
        connect_rate = round((answered_calls_today / calls_today) * 100, 1)
    else:
        # Fast SQL aggregation fallback
        agg_res = db.query(
            func.count(Call.id),
            func.coalesce(func.sum(Call.duration_seconds), 0),
            func.coalesce(func.avg(Call.duration_seconds), 0)
        ).filter(
            (Call.status == "completed") | (Call.duration_seconds > 0)
        ).first()
        
        comp_count = agg_res[0] if agg_res else 0
        total_talk_all = int(agg_res[1]) if agg_res else 0
        avg_talk_secs = int(agg_res[2]) if agg_res else 0
        connect_rate = round((comp_count / max(1, total_calls_all_time)) * 100, 1) if total_calls_all_time > 0 else 100.0
        total_talk_secs = total_talk_all

    avg_duration_formatted = f"{avg_talk_secs // 60:02d}:{avg_talk_secs % 60:02d} min"
    if total_talk_secs >= 3600:
        total_talk_formatted = f"{total_talk_secs // 3600}h {(total_talk_secs % 3600) // 60}m"
    elif total_talk_secs >= 60:
        total_talk_formatted = f"{total_talk_secs // 60}m {total_talk_secs % 60}s"
    else:
        total_talk_formatted = f"{total_talk_secs}s"

    kpis = KPICards(
        total_customers=total_customers,
        calls_today=calls_today,
        calls_this_week=calls_this_week,
        calls_this_month=calls_this_month,
        total_calls_all_time=total_calls_all_time,
        current_month_name=month_name,
        current_year=year_num,
        current_date_formatted=date_formatted,
        current_month_year_formatted=month_year_formatted,
        emails_sent_today=emails_today,
        pending_followups=pending_fu,
        overdue_followups=overdue_fu,
        completed_followups=completed_fu,
        avg_duration_today_seconds=avg_talk_secs,
        avg_duration_today_formatted=avg_duration_formatted,
        total_talk_time_today_seconds=total_talk_secs,
        total_talk_time_today_formatted=total_talk_formatted,
        call_connect_rate_percent=connect_rate,
        answered_calls_today=answered_calls_today,
        missed_calls_today=missed_calls_today
    )

    # 2. Recent Calls (fast single query)
    recent_calls_db = call_query.order_by(desc(Call.start_time)).limit(6).all()
    recent_calls = []
    for c in recent_calls_db:
        recent_calls.append({
            "id": c.id,
            "call_id": c.call_id,
            "phone_number": c.phone_number,
            "customer_name": c.customer.party_name if (c.customer and hasattr(c.customer, 'party_name')) else "Unknown Caller",
            "customer_id": c.customer.id if c.customer else None,
            "direction": c.direction,
            "status": c.status,
            "duration": f"{(c.duration_seconds or 0) // 60:02d}:{(c.duration_seconds or 0) % 60:02d}",
            "time": c.start_time.isoformat() if c.start_time else None
        })

    # 3. Recent Interactions
    recent_inters_db = inter_query.order_by(desc(CustomerInteraction.interaction_time)).limit(6).all()
    recent_interactions = []
    for i in recent_inters_db:
        recent_interactions.append({
            "id": i.id,
            "type": i.interaction_type,
            "subject": i.subject,
            "customer_name": i.customer.party_name if (i.customer and hasattr(i.customer, 'party_name')) else "Unknown",
            "customer_id": i.customer_id,
            "time": i.interaction_time.isoformat() if i.interaction_time else None,
            "agent": i.user.full_name if i.user else "System"
        })

    # 4. Today's and Overdue Follow-ups
    today_fu_db = (
        fu_query.filter(
            FollowUp.status.in_(["Pending", "In Progress"]),
            FollowUp.due_date >= today_start_utc,
            FollowUp.due_date < today_start_utc + timedelta(days=1)
        )
        .order_by(FollowUp.due_date.asc())
        .limit(6)
        .all()
    )
    today_followups = [
        {
            "id": f.id,
            "title": f.title,
            "customer_name": f.customer.party_name if (f.customer and hasattr(f.customer, 'party_name')) else "N/A",
            "customer_id": f.customer_id,
            "phone": f.customer.phone_1 if f.customer else "",
            "due_date": f.due_date.isoformat() if f.due_date else None,
            "priority": f.priority,
            "status": f.status
        }
        for f in today_fu_db
    ]

    overdue_fu_db = (
        fu_query.filter(
            FollowUp.status.in_(["Pending", "In Progress"]),
            FollowUp.due_date < today_start_utc
        )
        .order_by(FollowUp.due_date.asc())
        .limit(6)
        .all()
    )
    overdue_followups = [
        {
            "id": f.id,
            "title": f.title,
            "customer_name": f.customer.party_name if (f.customer and hasattr(f.customer, 'party_name')) else "N/A",
            "customer_id": f.customer_id,
            "phone": f.customer.phone_1 if f.customer else "",
            "due_date": f.due_date.isoformat() if f.due_date else None,
            "priority": f.priority,
            "status": f.status
        }
        for f in overdue_fu_db
    ]

    # 5. Team Performance (Fast aggregate)
    team_performance = []
    all_users = db.query(User).filter(User.is_active == True).order_by(User.full_name).all() if is_admin else [current_user]

    for emp in all_users:
        assigned_count = db.query(Customer).filter(Customer.assigned_employee_id == emp.id, Customer.is_archived == False).count()
        calls_count = db.query(Call).filter(Call.user_id == emp.id).count()
        inter_count = db.query(CustomerInteraction).filter(CustomerInteraction.user_id == emp.id).count()
        fu_done = db.query(FollowUp).filter(FollowUp.assigned_user_id == emp.id, FollowUp.status == "Completed").count()
        desig = emp.designation if (emp.designation and emp.designation != "NA") else ("Admin" if emp.role == "admin" else "Employee")

        team_performance.append(EmployeePerformance(
            user_id=emp.id,
            full_name=emp.full_name,
            email=emp.email,
            role=emp.role,
            phone=emp.phone,
            allowed_caller_id=emp.allowed_caller_id or emp.vid,
            designation=desig,
            assigned_customers_count=assigned_count,
            calls_logged=calls_count,
            interactions_logged=inter_count,
            followups_completed=fu_done
        ))

    # 6. TODAY'S EMPLOYEE-WISE CALLING PERFORMANCE (In-Memory instant calculation from today_calls_list)
    employee_calling_today = []
    perf_employees = [u for u in all_users if u.role == "employee"] if is_admin else [current_user]

    for emp in perf_employees:
        user_cid = str(emp.allowed_caller_id or emp.vid or "").strip()
        norm_cid = user_cid.replace("+", "").lstrip("0") if user_cid else ""
        emp_name_lower = emp.full_name.lower() if emp.full_name else ""

        emp_today_calls = []
        for c in today_calls_list:
            matches_user = (c.user_id == emp.id)
            matches_cid = False
            if norm_cid:
                c_to = str(c.call_to_number or "")
                c_agent = str(c.agent_number or "")
                if c_to == user_cid or (norm_cid[-10:] in c_to) or c_agent == user_cid or (norm_cid[-10:] in c_agent):
                    matches_cid = True
            matches_name = bool(emp_name_lower and c.agent_name and emp_name_lower in c.agent_name.lower())
            if matches_user or matches_cid or matches_name:
                emp_today_calls.append(c)

        emp_total = len(emp_today_calls)
        emp_outbound = sum(1 for c in emp_today_calls if c.direction == "outgoing")
        emp_inbound = sum(1 for c in emp_today_calls if c.direction == "incoming")
        emp_connected = sum(1 for c in emp_today_calls if c.status == "completed" or (c.duration_seconds or 0) > 0)
        emp_missed = sum(1 for c in emp_today_calls if c.status in ["missed", "cancelled", "rejected"] and (c.duration_seconds or 0) == 0)
        emp_talk_secs = sum(c.duration_seconds or 0 for c in emp_today_calls if c.status == "completed" or (c.duration_seconds or 0) > 0)
        emp_avg_duration_secs = (emp_talk_secs // emp_connected) if emp_connected > 0 else 0
        emp_avg_dur_formatted = f"{emp_avg_duration_secs // 60:02d}:{emp_avg_duration_secs % 60:02d} min"
        emp_connect_rate = round((emp_connected / emp_total * 100), 1) if emp_total > 0 else 0.0

        if emp_talk_secs >= 3600:
            emp_talk_formatted = f"{emp_talk_secs // 3600}h {(emp_talk_secs % 3600) // 60}m"
        elif emp_talk_secs >= 60:
            emp_talk_formatted = f"{emp_talk_secs // 60}m {emp_talk_secs % 60}s"
        else:
            emp_talk_formatted = f"{emp_talk_secs}s"

        desig = emp.designation if (emp.designation and emp.designation != "NA") else "Employee"

        employee_calling_today.append(EmployeeCallingPerformance(
            user_id=emp.id,
            full_name=emp.full_name,
            email=emp.email,
            designation=desig,
            allowed_caller_id=emp.allowed_caller_id or emp.vid,
            total_calls=emp_total,
            outbound_calls=emp_outbound,
            inbound_calls=emp_inbound,
            connected_calls=emp_connected,
            missed_calls=emp_missed,
            connect_rate_percent=emp_connect_rate,
            avg_duration_seconds=emp_avg_duration_secs,
            avg_duration_formatted=emp_avg_dur_formatted,
            total_talk_time_seconds=emp_talk_secs,
            total_talk_time_formatted=emp_talk_formatted
        ))

    employee_calling_today.sort(key=lambda x: (x.total_calls, x.connected_calls, x.total_talk_time_seconds), reverse=True)

    # 7. Highlights & Leaderboards (Most Calls, Least Calls, Top Performer)
    most_calls_emp = None
    least_calls_emp = None
    most_connected_emp = None
    top_performer_emp = None

    active_emp_list = [e for e in employee_calling_today if e.total_calls > 0]
    if active_emp_list:
        # Most Calls
        best_caller = max(active_emp_list, key=lambda x: x.total_calls)
        most_calls_emp = {
            "name": best_caller.full_name,
            "count": best_caller.total_calls,
            "connected": best_caller.connected_calls,
            "connect_rate": best_caller.connect_rate_percent,
            "designation": best_caller.designation
        }
        # Most Connected Calls
        best_connected = max(active_emp_list, key=lambda x: (x.connected_calls, x.connect_rate_percent))
        most_connected_emp = {
            "name": best_connected.full_name,
            "count": best_connected.connected_calls,
            "total": best_connected.total_calls,
            "connect_rate": best_connected.connect_rate_percent,
            "designation": best_connected.designation
        }
        # Top Performer (Composite: Connected calls + Talk time + Connect rate)
        top_perf = max(
            active_emp_list,
            key=lambda x: (x.connected_calls * 10) + (x.total_talk_time_seconds // 30) + (x.connect_rate_percent * 0.5)
        )
        top_performer_emp = {
            "name": top_perf.full_name,
            "connected_calls": top_perf.connected_calls,
            "total_calls": top_perf.total_calls,
            "talk_time": top_perf.total_talk_time_formatted,
            "connect_rate": top_perf.connect_rate_percent,
            "designation": top_perf.designation
        }
    
    if employee_calling_today:
        # Least Calls among team
        lowest_caller = min(employee_calling_today, key=lambda x: x.total_calls)
        least_calls_emp = {
            "name": lowest_caller.full_name,
            "count": lowest_caller.total_calls,
            "connected": lowest_caller.connected_calls,
            "designation": lowest_caller.designation
        }

    calling_summary_today = TodayCallingSummary(
        total_calls=calls_today,
        outbound_calls=sum(1 for c in today_calls_list if c.direction == "outgoing"),
        inbound_calls=sum(1 for c in today_calls_list if c.direction == "incoming"),
        connected_calls=answered_calls_today,
        missed_calls=sum(1 for c in today_calls_list if c.status in ["missed", "cancelled", "rejected"] and (c.duration_seconds or 0) == 0),
        connect_rate_percent=connect_rate,
        avg_call_duration_seconds=avg_talk_secs,
        avg_call_duration_formatted=avg_duration_formatted,
        total_talk_time_seconds=total_talk_secs,
        total_talk_time_formatted=total_talk_formatted,
        most_calls_employee=most_calls_emp,
        least_calls_employee=least_calls_emp,
        most_connected_employee=most_connected_emp,
        top_performer=top_performer_emp
    )

    # 8. Call trends (past 7 days)
    call_trends = []
    for day_offset in range(6, -1, -1):
        day_ist = (today_start_ist - timedelta(days=day_offset))
        day_utc = day_ist.astimezone(timezone.utc)
        next_day_utc = day_utc + timedelta(days=1)
        cnt = call_query.filter(Call.start_time >= day_utc, Call.start_time < next_day_utc).count()
        call_trends.append({
            "day": day_ist.strftime("%a %d"),
            "calls": cnt
        })

    from backend.app.services.token_service import SmartfloTokenService
    token_meta = SmartfloTokenService.get_token_metadata() if current_user.role == "admin" else None

    return DashboardStatsResponse(
        role=current_user.role,
        user_name=current_user.full_name,
        kpis=kpis,
        recent_calls=recent_calls,
        recent_interactions=recent_interactions,
        today_followups=today_followups,
        overdue_followups=overdue_followups,
        team_activity=team_activity,
        call_trends=call_trends,
        calling_summary_today=calling_summary_today,
        employee_calling_today=employee_calling_today,
        smartflo_token=token_meta
    )
