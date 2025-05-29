# backend/app.py
import os
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from datetime import date, datetime, timedelta, timezone

from database import db, init_app
# Import ApplicationLog model as well
from models import Setting, DailyLog, ApplicationLog, get_settings, get_current_status

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
    """ Endpoint to update the daily application goal (unchanged). """
    data = request.get_json()
    if not data or 'goal' not in data: return jsonify({"error": "Missing 'goal'"}), 400
    try:
        new_goal = int(data.get('goal'))
        if new_goal <= 0: raise ValueError("Goal must be positive")
    except (TypeError, ValueError): return jsonify({"error": "Invalid goal value"}), 400
    try:
        settings = get_settings()
        settings.daily_goal = new_goal
        db.session.commit()
        return jsonify({"dailyGoal": settings.daily_goal})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error updating goal: {e}")
        return jsonify({"error": "Failed to update goal"}), 500

# --- UPDATED Endpoint: Get session data including applications ---
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
        # Use joinedload to efficiently fetch related applications
        log_entry = DailyLog.query.options(
            db.joinedload(DailyLog.applications)
        ).get(log_date)

        if log_entry:
            # Convert application logs to dictionaries
            applications_data = [app.to_dict() for app in log_entry.applications]
            return jsonify({
                "found": True,
                "log_date": log_entry.log_date.isoformat(),
                "status": log_entry.status,
                "completed_count": log_entry.completed_count,
                "elapsed_seconds": log_entry.elapsed_seconds,
                "applications": applications_data # Include applications list
            })
        else:
            return jsonify({"found": False}), 404
    except Exception as e:
        app.logger.error(f"Error fetching session data for {log_date_str}: {e}")
        return jsonify({"error": "Failed to fetch session data"}), 500

# --- UPDATED Endpoint: Finish Day (now saves applications) ---
@app.route('/api/finish_day', methods=['POST'])
def finish_day():
    """
    Logs/updates status for the current day AND saves the application details.
    Accepts JSON: {
        "completedCount": <int>,
        "elapsedSeconds": <int>,
        "applications": [ { "jobName": "...", "company": "...", "resume": "..." }, ... ]
    }
    """
    today = get_eastern_today()
    data = request.get_json()

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

    try:
        settings = get_settings()
        daily_goal = settings.daily_goal
        status = 'complete' if completed_count >= daily_goal else 'incomplete'

        # --- UPSERT DailyLog ---
        existing_log = DailyLog.query.get(today)
        if existing_log:
            existing_log.status = status
            existing_log.completed_count = completed_count
            existing_log.elapsed_seconds = elapsed_seconds
            print(f"Updating DailyLog for {today}")
            # --- Delete existing ApplicationLogs for this date ---
            # This ensures the stored applications match the finished session exactly
            ApplicationLog.query.filter_by(log_date=today).delete()
            print(f"Deleted existing ApplicationLogs for {today}")
        else:
            existing_log = DailyLog( # Assign to existing_log so we can add apps below
                log_date=today,
                status=status,
                completed_count=completed_count,
                elapsed_seconds=elapsed_seconds
            )
            db.session.add(existing_log)
            print(f"Inserting new DailyLog for {today}")

        # --- Insert new ApplicationLogs ---
        for app_data in applications_list:
            # Basic validation of app_data if needed
            new_app_log = ApplicationLog(
                log_date=today, # Link to the current day's log
                job_name=app_data.get('jobName'),
                company=app_data.get('company'),
                resume_used=app_data.get('resume')
                # 'done' status is implicit, not stored
            )
            db.session.add(new_app_log)
        print(f"Inserted {len(applications_list)} ApplicationLogs for {today}")

        db.session.commit()

        status_data = get_current_status()
        return jsonify({
            "message": f"Day log {'updated' if existing_log else 'created'} successfully with status: {status}",
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
        logged_days_status = [{"date": log.log_date.isoformat(), "status": log.status} for log in logs]
        return jsonify({"loggedDaysStatus": logged_days_status})
    except Exception as e:
        app.logger.error(f"Error fetching calendar data: {e}")
        return jsonify({"error": "Failed to fetch calendar data"}), 500

# --- NEW Endpoint: Get application logs for a specific date ---
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
        applications_data = [app.to_dict() for app in app_logs]

        # Also fetch the summary status for context
        daily_log_summary = DailyLog.query.get(log_date)
        log_status = daily_log_summary.status if daily_log_summary else None

        return jsonify({
            "log_date": log_date_str,
            "status": log_status,
            "applications": applications_data
        })
    except Exception as e:
        app.logger.error(f"Error fetching logs for {log_date_str}: {e}")
        return jsonify({"error": "Failed to fetch logs for date"}), 500


@app.route('/api/reset', methods=['DELETE'])
def reset_data():
    """ Endpoint to delete all logs and reset settings (unchanged). """
    try:
        # Order matters due to foreign key constraint: delete applications first
        db.session.query(ApplicationLog).delete()
        db.session.query(DailyLog).delete()
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
        applications = [app.to_dict() for app in log.applications]
        export_data.append({
            'log_date': log.log_date.isoformat(),
            'status': log.status,
            'completed_count': log.completed_count,
            'elapsed_seconds': log.elapsed_seconds,
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
            'log_date', 'status', 'completed_count', 'elapsed_seconds',
            'jobName', 'company', 'resume'
        ])
        for log in export_data:
            if log['applications']:
                for app in log['applications']:
                    writer.writerow([
                        log['log_date'], log['status'], log['completed_count'], log['elapsed_seconds'],
                        app.get('jobName', ''), app.get('company', ''), app.get('resume', '')
                    ])
            else:
                # No applications for this day
                writer.writerow([
                    log['log_date'], log['status'], log['completed_count'], log['elapsed_seconds'], '', '', ''
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
    # Use US Eastern Time
    try:
        # Python 3.9+: use zoneinfo
        eastern = ZoneInfo('America/New_York')
        now = datetime.now(eastern)
        tz_abbr = now.tzname()
    except Exception:
        # Fallback for pytz
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
    from models import DailyLog, get_current_status
    from datetime import date
    logs = DailyLog.query.order_by(DailyLog.log_date).all()
    log_list = [
        {"log_date": log.log_date.isoformat(), "status": log.status} for log in logs
    ]
    streaks = get_current_status()
    return {
        "backend_today": date.today().isoformat(),
        "logs": log_list,
        "streaks": streaks
    }

# --- Helper: Always get today in US Eastern Time ---
def get_eastern_today():
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        eastern = ZoneInfo('America/New_York')
        return datetime.now(eastern).date()
    except Exception:
        import pytz
        eastern = pytz.timezone('America/New_York')
        return datetime.now(eastern).date()

# --- Main Execution ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
