# backend/app.py
import os
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import joinedload

from database import db, init_app
# Import models and domain helpers. get_eastern_today lives in models so app.py
# and the streak math share one source of truth for "today" (US Eastern).
from models import (
    Setting,
    DailyLog,
    ApplicationLog,
    GoalHistory,
    get_settings,
    get_current_status,
    get_analytics,
    get_eastern_today,
)

# Initialize Flask app
app = Flask(__name__)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Configure and initialize the database
init_app(app)

# Enable Cross-Origin Resource Sharing (CORS)
CORS(app)

# --- Database Setup ---
with app.app_context():
    db.create_all() # This will now create both tables if they don't exist
    get_settings()

# --- API Endpoints ---

@app.route('/api/health', methods=['GET'])
def health():
    """ Lightweight liveness/readiness probe: confirms the API is up and the DB
    is reachable. Useful for Docker healthchecks and uptime monitoring. """
    db_ok = True
    try:
        # Cheap round-trip to the DB.
        get_settings()
    except Exception as e:
        db_ok = False
        app.logger.error(f"Health check DB error: {e}")
    payload = {"status": "ok" if db_ok else "degraded", "database": db_ok}
    return jsonify(payload), (200 if db_ok else 503)


@app.route('/api/state', methods=['GET'])
def get_state():
    """ Endpoint to get the current application state (unchanged logic). """
    try:
        settings = get_settings()
        status_data = get_current_status()
        return jsonify({"dailyGoal": settings.daily_goal, **status_data})
    except Exception as e:
        app.logger.error(f"Error fetching state: {e}")
        return jsonify({"error": "Failed to fetch application state"}), 500

@app.route('/api/goal', methods=['PUT'])
def update_goal():
    """ Endpoint to update the daily application goal. Records goal history. """
    data = request.get_json(silent=True)
    if not data or 'goal' not in data: return jsonify({"error": "Missing 'goal'"}), 400
    try:
        new_goal = int(data.get('goal'))
        if new_goal <= 0: raise ValueError("Goal must be positive")
    except (TypeError, ValueError): return jsonify({"error": "Invalid goal value"}), 400
    try:
        settings = get_settings()
        # Only record a history entry when the goal actually changes.
        if settings.daily_goal != new_goal:
            db.session.add(GoalHistory(daily_goal=new_goal))
        settings.daily_goal = new_goal
        db.session.commit()
        return jsonify({"dailyGoal": settings.daily_goal})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error updating goal: {e}")
        return jsonify({"error": "Failed to update goal"}), 500

# --- Get session data including applications ---
@app.route('/api/session/<string:log_date_str>', methods=['GET'])
def get_session_data(log_date_str):
    """
    Gets the existing log data AND associated applications for a specific date.
    Used for resuming a session.
    """
    try:
        log_date = date.fromisoformat(log_date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    try:
        # Use joinedload to efficiently fetch related applications.
        # NOTE: joinedload is imported from sqlalchemy.orm (it is NOT an
        # attribute of the Flask-SQLAlchemy `db` object, which previously raised
        # an AttributeError here).
        log_entry = DailyLog.query.options(
            joinedload(DailyLog.applications)
        ).get(log_date)

        if log_entry:
            # Convert application logs to dictionaries
            applications_data = [a.to_dict() for a in log_entry.applications]
            return jsonify({
                "found": True,
                "log_date": log_entry.log_date.isoformat(),
                "status": log_entry.status,
                "completed_count": log_entry.completed_count,
                "elapsed_seconds": log_entry.elapsed_seconds,
                "notes": log_entry.notes,
                "applications": applications_data # Include applications list
            })
        else:
            return jsonify({"found": False}), 404
    except Exception as e:
        app.logger.error(f"Error fetching session data for {log_date_str}: {e}")
        return jsonify({"error": "Failed to fetch session data"}), 500

# --- Finish Day (saves applications) ---
@app.route('/api/finish_day', methods=['POST'])
def finish_day():
    """
    Logs/updates status for the current day AND saves the application details.
    Accepts JSON: {
        "completedCount": <int>,
        "elapsedSeconds": <int>,
        "applications": [ { "jobName": "...", "company": "...", "resume": "..." }, ... ],
        "notes": <str optional>
    }
    """
    today = get_eastern_today()
    data = request.get_json(silent=True)

    # Validate incoming data
    if not data or 'completedCount' not in data or 'elapsedSeconds' not in data or 'applications' not in data:
        return jsonify({"error": "Missing 'completedCount', 'elapsedSeconds', or 'applications' in request body"}), 400
    if not isinstance(data['applications'], list):
         return jsonify({"error": "'applications' must be a list."}), 400

    try:
        completed_count = int(data['completedCount'])
        elapsed_seconds = int(data['elapsedSeconds'])
        applications_list = data['applications'] # List of application dicts from frontend
        if completed_count < 0 or elapsed_seconds < 0:
            raise ValueError("Counts and time cannot be negative.")
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid completedCount or elapsedSeconds."}), 400

    notes = data.get('notes')
    if notes is not None and not isinstance(notes, str):
        return jsonify({"error": "'notes' must be a string."}), 400

    try:
        settings = get_settings()
        daily_goal = settings.daily_goal
        status = 'complete' if completed_count >= daily_goal else 'incomplete'

        # --- UPSERT DailyLog ---
        existing_log = DailyLog.query.get(today)
        was_update = existing_log is not None
        if existing_log:
            existing_log.status = status
            existing_log.completed_count = completed_count
            existing_log.elapsed_seconds = elapsed_seconds
            if notes is not None:
                existing_log.notes = notes
            # --- Delete existing ApplicationLogs for this date ---
            # This ensures the stored applications match the finished session exactly
            ApplicationLog.query.filter_by(log_date=today).delete()
        else:
            existing_log = DailyLog( # Assign so we can add apps below
                log_date=today,
                status=status,
                completed_count=completed_count,
                elapsed_seconds=elapsed_seconds,
                notes=notes,
            )
            db.session.add(existing_log)

        # --- Insert new ApplicationLogs ---
        for app_data in applications_list:
            if not isinstance(app_data, dict):
                # Skip malformed entries rather than crashing the whole request.
                continue
            new_app_log = ApplicationLog(
                log_date=today, # Link to the current day's log
                job_name=(app_data.get('jobName') or None),
                company=(app_data.get('company') or None),
                resume_used=(app_data.get('resume') or None)
                # 'done' status is implicit, not stored
            )
            db.session.add(new_app_log)

        db.session.commit()

        status_data = get_current_status()
        return jsonify({
            "message": f"Day log {'updated' if was_update else 'created'} successfully with status: {status}",
            **status_data
        }), 200 # Use 200 OK for update/create consistency here

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error finishing day: {e}")
        return jsonify({"error": "Failed to log day"}), 500


@app.route('/api/calendar_data', methods=['GET'])
def get_calendar_data():
    """ Endpoint to get logged status for calendar dates (unchanged). """
    try:
        month_str = request.args.get('month')
        year_str = request.args.get('year')
        if not month_str or not year_str: return jsonify({"error": "Missing 'month' or 'year'"}), 400
        month = int(month_str); year = int(year_str)
        if not (1 <= month <= 12): return jsonify({"error": "Month must be 1-12"}), 400
    except (TypeError, ValueError): return jsonify({"error": "Invalid month/year"}), 400
    try:
        start_date = date(year, month, 1)
        end_date = date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)
        logs = DailyLog.query.filter( DailyLog.log_date >= start_date, DailyLog.log_date < end_date ).all()
        logged_days_status = [
            {"date": log.log_date.isoformat(), "status": log.status, "completedCount": log.completed_count}
            for log in logs
        ]
        return jsonify({"loggedDaysStatus": logged_days_status})
    except Exception as e:
        app.logger.error(f"Error fetching calendar data: {e}")
        return jsonify({"error": "Failed to fetch calendar data"}), 500

# --- Get application logs for a specific date ---
@app.route('/api/logs/<string:log_date_str>', methods=['GET'])
def get_logs_for_date(log_date_str):
    """ Gets the list of applications logged on a specific date. """
    try:
        log_date = date.fromisoformat(log_date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    try:
        # Query ApplicationLog directly for the given date
        app_logs = ApplicationLog.query.filter_by(log_date=log_date).order_by(ApplicationLog.timestamp).all()
        applications_data = [a.to_dict() for a in app_logs]

        # Also fetch the summary status for context
        daily_log_summary = DailyLog.query.get(log_date)
        log_status = daily_log_summary.status if daily_log_summary else None
        notes = daily_log_summary.notes if daily_log_summary else None

        return jsonify({
            "log_date": log_date_str,
            "status": log_status,
            "notes": notes,
            "applications": applications_data
        })
    except Exception as e:
        app.logger.error(f"Error fetching logs for {log_date_str}: {e}")
        return jsonify({"error": "Failed to fetch logs for date"}), 500


# --- NEW: Edit a past day's log (count / applications / notes) ---
@app.route('/api/logs/<string:log_date_str>', methods=['PUT'])
def update_logs_for_date(log_date_str):
    """ Edit a previously logged day. Accepts any subset of:
        { "completedCount": <int>, "elapsedSeconds": <int>,
          "notes": <str>, "applications": [ {...} ] }
    Status is recomputed against the current daily goal. If 'applications' is
    provided it fully replaces the day's applications (same semantics as
    finish_day). The day's log must already exist. """
    try:
        log_date = date.fromisoformat(log_date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Missing request body."}), 400

    log_entry = DailyLog.query.get(log_date)
    if not log_entry:
        return jsonify({"error": "No log exists for that date."}), 404

    try:
        if 'completedCount' in data:
            cc = int(data['completedCount'])
            if cc < 0:
                raise ValueError("completedCount cannot be negative.")
            log_entry.completed_count = cc
        if 'elapsedSeconds' in data:
            es = int(data['elapsedSeconds'])
            if es < 0:
                raise ValueError("elapsedSeconds cannot be negative.")
            log_entry.elapsed_seconds = es
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid completedCount or elapsedSeconds."}), 400

    if 'notes' in data:
        if data['notes'] is not None and not isinstance(data['notes'], str):
            return jsonify({"error": "'notes' must be a string."}), 400
        log_entry.notes = data['notes']

    if 'applications' in data:
        if not isinstance(data['applications'], list):
            return jsonify({"error": "'applications' must be a list."}), 400
        ApplicationLog.query.filter_by(log_date=log_date).delete()
        for app_data in data['applications']:
            if not isinstance(app_data, dict):
                continue
            db.session.add(ApplicationLog(
                log_date=log_date,
                job_name=(app_data.get('jobName') or None),
                company=(app_data.get('company') or None),
                resume_used=(app_data.get('resume') or None),
            ))

    try:
        # Recompute status against the current goal.
        settings = get_settings()
        log_entry.status = 'complete' if log_entry.completed_count >= settings.daily_goal else 'incomplete'
        db.session.commit()
        return jsonify({"message": "Log updated.", **log_entry.to_dict(),
                        **get_current_status()}), 200
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error updating logs for {log_date_str}: {e}")
        return jsonify({"error": "Failed to update log."}), 500


# --- NEW: Delete a single day's log entirely ---
@app.route('/api/logs/<string:log_date_str>', methods=['DELETE'])
def delete_logs_for_date(log_date_str):
    """ Delete a day's DailyLog and its applications (cascade). Useful for
    correcting a mistaken entry without wiping all data. """
    try:
        log_date = date.fromisoformat(log_date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    log_entry = DailyLog.query.get(log_date)
    if not log_entry:
        return jsonify({"error": "No log exists for that date."}), 404

    try:
        # cascade="all, delete-orphan" on DailyLog.applications removes the
        # child ApplicationLog rows when the parent is deleted.
        db.session.delete(log_entry)
        db.session.commit()
        return jsonify({"message": f"Log for {log_date_str} deleted.",
                        **get_current_status()}), 200
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error deleting log for {log_date_str}: {e}")
        return jsonify({"error": "Failed to delete log."}), 500


# --- NEW: Analytics summary ---
@app.route('/api/analytics', methods=['GET'])
def analytics():
    """ Aggregate stats across all logged days (totals, averages, completion
    rate, best day, longest streak, per-weekday breakdown). """
    try:
        return jsonify(get_analytics()), 200
    except Exception as e:
        app.logger.error(f"Error computing analytics: {e}")
        return jsonify({"error": "Failed to compute analytics"}), 500


# --- NEW: Goal change history ---
@app.route('/api/goal_history', methods=['GET'])
def goal_history():
    """ Returns the chronological history of daily-goal changes. """
    try:
        history = GoalHistory.query.order_by(GoalHistory.changed_at).all()
        return jsonify({"history": [h.to_dict() for h in history]}), 200
    except Exception as e:
        app.logger.error(f"Error fetching goal history: {e}")
        return jsonify({"error": "Failed to fetch goal history"}), 500


@app.route('/api/reset', methods=['DELETE'])
def reset_data():
    """ Endpoint to delete all logs and reset settings. """
    try:
        # Order matters due to foreign key constraint: delete applications first
        db.session.query(ApplicationLog).delete()
        db.session.query(DailyLog).delete()
        db.session.query(GoalHistory).delete()
        db.session.query(Setting).delete()
        db.session.commit()
        get_settings()
        return jsonify({"message": "All data reset successfully"}), 200
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Failed to reset data: {e}")
        return jsonify({"error": "Failed to reset data", "details": str(e)}), 500

@app.route('/api/export_logs', methods=['GET'])
def export_logs():
    """
    Export all logs (DailyLog + ApplicationLog) as CSV or JSON.
    Query param: ?format=csv or ?format=json (default: json)
    """
    format = request.args.get('format', 'json').lower()
    # Fetch all logs, order by date
    logs = DailyLog.query.order_by(DailyLog.log_date).all()
    export_data = []
    for log in logs:
        applications = [a.to_dict() for a in log.applications]
        export_data.append({
            'log_date': log.log_date.isoformat(),
            'status': log.status,
            'completed_count': log.completed_count,
            'elapsed_seconds': log.elapsed_seconds,
            'notes': log.notes,
            'applications': applications
        })

    if format == 'csv':
        # Flatten for CSV: one row per application, include day info
        import csv
        from io import StringIO
        si = StringIO()
        writer = csv.writer(si)
        # Header
        writer.writerow([
            'log_date', 'status', 'completed_count', 'elapsed_seconds', 'notes',
            'jobName', 'company', 'resume'
        ])
        for log in export_data:
            if log['applications']:
                for app_row in log['applications']:
                    writer.writerow([
                        log['log_date'], log['status'], log['completed_count'], log['elapsed_seconds'],
                        log.get('notes', '') or '',
                        app_row.get('jobName', ''), app_row.get('company', ''), app_row.get('resume', '')
                    ])
            else:
                # No applications for this day
                writer.writerow([
                    log['log_date'], log['status'], log['completed_count'], log['elapsed_seconds'],
                    log.get('notes', '') or '', '', '', ''
                ])
        output = si.getvalue()
        return Response(
            output,
            mimetype='text/csv',
            headers={
                'Content-Disposition': 'attachment; filename=jobtracker_logs.csv'
            }
        )
    else:
        # Default: JSON
        return jsonify(export_data), 200

@app.route('/api/server_time', methods=['GET'])
def get_server_time():
    """ Current time in US Eastern. """
    # Prefer the stdlib zoneinfo (Python 3.9+); fall back to pytz.
    try:
        from zoneinfo import ZoneInfo
        eastern = ZoneInfo('America/New_York')
    except Exception:
        import pytz
        eastern = pytz.timezone('America/New_York')
    now = datetime.now(eastern)
    tz_abbr = now.tzname()
    return jsonify({
        'iso': now.isoformat(),
        'date': now.strftime('%Y-%m-%d'),
        'time': now.strftime('%H:%M:%S'),
        'datetime': now.strftime('%A, %B %d, %Y %H:%M:%S'),
        'tz': tz_abbr
    })

@app.route('/api/debug_streaks', methods=['GET'])
def debug_streaks():
    logs = DailyLog.query.order_by(DailyLog.log_date).all()
    log_list = [
        {"log_date": log.log_date.isoformat(), "status": log.status} for log in logs
    ]
    streaks = get_current_status()
    return {
        # Use the shared Eastern helper so this matches the streak logic instead
        # of the container's local clock (previously used date.today()).
        "backend_today": get_eastern_today().isoformat(),
        "logs": log_list,
        "streaks": streaks
    }

# --- Main Execution ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
