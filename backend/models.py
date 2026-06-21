# backend/models.py
from database import db
from datetime import date, timedelta, datetime # Added datetime
from sqlalchemy import desc, ForeignKey # Added ForeignKey
from sqlalchemy.orm import relationship # Added relationship


# --- Shared timezone helper -------------------------------------------------
# "Today" is always evaluated in US Eastern Time so streak logic is independent
# of the container's local clock. Both app.py and the streak math below rely on
# this single helper instead of date.today().
def get_eastern_today():
    """ Returns the current date in US Eastern Time. """
    try:
        from zoneinfo import ZoneInfo  # Python 3.9+
        eastern = ZoneInfo('America/New_York')
    except Exception:
        import pytz
        eastern = pytz.timezone('America/New_York')
    return datetime.now(eastern).date()


class Setting(db.Model):
    """ Model to store application settings (unchanged). """
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False, default='global_settings')
    daily_goal = db.Column(db.Integer, nullable=False, default=5)

    def __repr__(self):
        return f'<Setting {self.key} Goal: {self.daily_goal}>'

class DailyLog(db.Model):
    """ Model to store summary for each day logging was finished. """
    __tablename__ = 'daily_logs'
    log_date = db.Column(db.Date, primary_key=True)
    status = db.Column(db.String(20), nullable=False, default='incomplete') # 'complete' or 'incomplete'
    completed_count = db.Column(db.Integer, nullable=False, default=0)
    elapsed_seconds = db.Column(db.Integer, nullable=False, default=0)
    # Free-form note for the day (additive column; requires a fresh DB/volume to
    # materialize since there is no migration tooling). Nullable so existing rows
    # remain valid.
    notes = db.Column(db.Text, nullable=True)

    # Relationship to ApplicationLog (one-to-many)
    # cascade="all, delete-orphan": ensures applications are deleted if the DailyLog is deleted.
    applications = relationship("ApplicationLog", back_populates="daily_log", cascade="all, delete-orphan")

    def __repr__(self):
        return f'<DailyLog Date: {self.log_date} Status: {self.status} Count: {self.completed_count}>'

    def to_dict(self):
        return {
            "log_date": self.log_date.isoformat(),
            "status": self.status,
            "completedCount": self.completed_count,
            "elapsedSeconds": self.elapsed_seconds,
            "notes": self.notes,
        }

# --- NEW Model: ApplicationLog ---
class ApplicationLog(db.Model):
    """ Model to store individual application details for a specific log date. """
    __tablename__ = 'application_logs'
    id = db.Column(db.Integer, primary_key=True)
    # Foreign Key linking to the DailyLog table's primary key (log_date)
    log_date = db.Column(db.Date, ForeignKey('daily_logs.log_date'), nullable=False)
    job_name = db.Column(db.String(200), nullable=True)
    company = db.Column(db.String(200), nullable=True)
    resume_used = db.Column(db.String(200), nullable=True)
    # Add a timestamp for potential future ordering within a day
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship back to DailyLog (many-to-one)
    daily_log = relationship("DailyLog", back_populates="applications")

    def __repr__(self):
        return f'<AppLog ID: {self.id} Date: {self.log_date} Job: {self.job_name}>'

    # Helper to convert to dictionary for JSON response
    def to_dict(self):
        return {
            "id": self.id, # Keep frontend ID consistent if needed, though backend ID is primary
            "jobName": self.job_name,
            "company": self.company,
            "resume": self.resume_used,
            "done": True # Assume if it's logged, it was marked done in that session
                       # Note: 'done' status isn't stored, as only 'done' items contribute to count
        }


# --- NEW Model: GoalHistory ---
class GoalHistory(db.Model):
    """ Records every change to the daily goal so progress can be judged against
    the goal that was actually in effect over time. Additive table; only
    materializes on a fresh DB (no migration tooling in this project). """
    __tablename__ = 'goal_history'
    id = db.Column(db.Integer, primary_key=True)
    daily_goal = db.Column(db.Integer, nullable=False)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "dailyGoal": self.daily_goal,
            "changedAt": self.changed_at.isoformat() if self.changed_at else None,
        }


# --- Helper Functions ---

def get_settings():
    """ Gets the global settings (unchanged). """
    settings = Setting.query.filter_by(key='global_settings').first()
    if not settings:
        print("Settings not found, creating default settings.")
        settings = Setting(key='global_settings', daily_goal=5)
        db.session.add(settings)
        db.session.commit()
    return settings


def _milestone_for(streak):
    """ Returns the most recent milestone reached for a streak length, or None. """
    milestones = [365, 180, 100, 50, 30, 14, 7, 3]
    for m in milestones:
        if streak >= m:
            return m
    return None


def get_current_status():
    """ Calculates streaks, total days, last log date/status (fixed logic, always uses US Eastern Time for today). """
    today = get_eastern_today()
    logs = DailyLog.query.order_by(DailyLog.log_date).all()  # ASC order
    log_map = {log.log_date: log.status for log in logs}
    if not logs:
        return {
            "totalStreak": 0,
            "goalStreak": 0,
            "totalDaysLogged": 0,
            "lastCompletedDate": None,
            "lastLogStatus": None,
            "currentMilestone": None,
            "nextMilestone": 3,
        }
    last_log = logs[-1]
    last_log_date = last_log.log_date
    last_log_status = last_log.status
    total_days = len(logs)
    # --- Calculate goal streak ---
    goal_streak = 0
    streak_date = today
    while True:
        status = log_map.get(streak_date)
        if status != 'complete':
            break
        goal_streak += 1
        streak_date -= timedelta(days=1)
    # --- Calculate total streak ---
    total_streak = 0
    streak_date = today
    while True:
        status = log_map.get(streak_date)
        if status is None:
            break
        total_streak += 1
        streak_date -= timedelta(days=1)
    last_completed_iso = last_log_date.isoformat() if last_log_date else None

    # --- Milestones (badge-style, borrowed from habit trackers) ---
    current_milestone = _milestone_for(goal_streak)
    milestone_ladder = [3, 7, 14, 30, 50, 100, 180, 365]
    next_milestone = next((m for m in milestone_ladder if m > goal_streak), None)

    return {
        "totalStreak": total_streak,
        "goalStreak": goal_streak,
        "totalDaysLogged": total_days,
        "lastCompletedDate": last_completed_iso,
        "lastLogStatus": last_log_status,
        "currentMilestone": current_milestone,
        "nextMilestone": next_milestone,
    }


def get_analytics():
    """ Aggregate analytics across all logged days. No schema dependency beyond
    the existing tables. Returns camelCase keys for the frontend. """
    logs = DailyLog.query.order_by(DailyLog.log_date).all()
    total_days = len(logs)
    if total_days == 0:
        return {
            "totalDaysLogged": 0,
            "totalApplications": 0,
            "totalCompleteDays": 0,
            "completionRate": 0,
            "avgApplicationsPerDay": 0,
            "avgMinutesPerDay": 0,
            "totalMinutes": 0,
            "bestDay": None,
            "longestGoalStreak": 0,
            "byWeekday": [],
        }

    total_apps = sum(l.completed_count for l in logs)
    total_complete = sum(1 for l in logs if l.status == 'complete')
    total_seconds = sum(l.elapsed_seconds for l in logs)

    # Best (most productive) day
    best = max(logs, key=lambda l: l.completed_count)
    best_day = {
        "date": best.log_date.isoformat(),
        "completedCount": best.completed_count,
    } if best.completed_count > 0 else None

    # Longest goal streak ever (not just current). Walk all complete days.
    complete_dates = sorted(l.log_date for l in logs if l.status == 'complete')
    longest = 0
    run = 0
    prev = None
    for d in complete_dates:
        if prev is not None and (d - prev) == timedelta(days=1):
            run += 1
        else:
            run = 1
        longest = max(longest, run)
        prev = d

    # Per-weekday breakdown (Mon=0 ... Sun=6)
    weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    weekday_apps = [0] * 7
    weekday_days = [0] * 7
    for l in logs:
        wd = l.log_date.weekday()
        weekday_apps[wd] += l.completed_count
        weekday_days[wd] += 1
    by_weekday = [
        {
            "weekday": weekday_names[i],
            "totalApplications": weekday_apps[i],
            "daysLogged": weekday_days[i],
            "avgApplications": round(weekday_apps[i] / weekday_days[i], 2) if weekday_days[i] else 0,
        }
        for i in range(7)
    ]

    return {
        "totalDaysLogged": total_days,
        "totalApplications": total_apps,
        "totalCompleteDays": total_complete,
        "completionRate": round(total_complete / total_days * 100, 1),
        "avgApplicationsPerDay": round(total_apps / total_days, 2),
        "avgMinutesPerDay": round((total_seconds / total_days) / 60, 1),
        "totalMinutes": round(total_seconds / 60, 1),
        "bestDay": best_day,
        "longestGoalStreak": longest,
        "byWeekday": by_weekday,
    }
