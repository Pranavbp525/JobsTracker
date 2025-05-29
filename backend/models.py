# backend/models.py
from database import db
from datetime import date, timedelta, datetime # Added datetime
from sqlalchemy import desc, ForeignKey # Added ForeignKey
from sqlalchemy.orm import relationship # Added relationship

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

    # Relationship to ApplicationLog (one-to-many)
    # cascade="all, delete-orphan": ensures applications are deleted if the DailyLog is deleted.
    applications = relationship("ApplicationLog", back_populates="daily_log", cascade="all, delete-orphan")

    def __repr__(self):
        return f'<DailyLog Date: {self.log_date} Status: {self.status} Count: {self.completed_count}>'

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

def get_current_status():
    """ Calculates streaks, total days, last log date/status (fixed logic, always uses US Eastern Time for today). """
    from datetime import datetime, timedelta
    try:
        from zoneinfo import ZoneInfo
        eastern = ZoneInfo('America/New_York')
        today = datetime.now(eastern).date()
    except Exception:
        import pytz
        eastern = pytz.timezone('America/New_York')
        today = datetime.now(eastern).date()
    logs = DailyLog.query.order_by(DailyLog.log_date).all()  # ASC order
    log_map = {log.log_date: log.status for log in logs}
    if not logs:
        return {"totalStreak": 0, "goalStreak": 0, "totalDaysLogged": 0, "lastCompletedDate": None, "lastLogStatus": None}
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
    return {
        "totalStreak": total_streak,
        "goalStreak": goal_streak,
        "totalDaysLogged": total_days,
        "lastCompletedDate": last_completed_iso,
        "lastLogStatus": last_log_status
    }

