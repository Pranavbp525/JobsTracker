# JobTracker Backend

This is the backend service for the JobTracker application, built with Flask and SQLAlchemy. It provides a RESTful API for tracking daily job application progress, storing application details, and managing user streaks and goals.

## Features
- Track daily job application goals and progress
- Log individual job applications with details (job, company, resume used)
- View streaks, total days logged, and last completion status
- Calendar view of logged days
- Reset all data
- Dockerized for easy deployment

## Requirements
- Python 3.9+
- PostgreSQL database
- (Recommended) Docker & Docker Compose

## Setup

### 1. Clone the repository
```bash
git clone <repo-url>
cd JobTracker/backend
```

### 2. Install dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Variables
Create a `.env` file in the backend directory with:
```
DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<dbname>
```

### 4. Run the server
```bash
flask run --host=0.0.0.0 --port=5001
```

Or use Docker (recommended):

### 5. Docker Usage
Build and run the backend service:
```bash
docker build -t jobtracker-backend .
docker run --env-file .env -p 5001:5001 jobtracker-backend
```
Or use `docker-compose` from the project root for full stack.

## File Overview
- `app.py` - Main Flask app, API endpoints
- `models.py` - SQLAlchemy models (Setting, DailyLog, ApplicationLog)
- `database.py` - DB connection/init logic
- `requirements.txt` - Python dependencies
- `Dockerfile` - Docker build instructions
- `wait-for-db.sh` - Entrypoint script to wait for DB
- `.dockerignore` - Files ignored by Docker

## API Endpoints
- `GET /api/state` - Get current goal, streaks, and status
- `PUT /api/goal` - Update daily goal
- `GET /api/session/<date>` - Get log and applications for a date
- `POST /api/finish_day` - Log/finish a day (with applications)
- `GET /api/calendar_data?month=&year=` - Get status for calendar
- `GET /api/logs/<date>` - Get applications for a date
- `DELETE /api/reset` - Reset all data

## Database Models
- **Setting**: Stores global settings (daily goal)
- **DailyLog**: Stores daily summary (date, status, completed count, elapsed time)
- **ApplicationLog**: Stores individual job applications (job, company, resume, timestamp)

## Development Notes
- Uses Flask-CORS for frontend/backend communication
- Uses python-dotenv for environment variable management
- All data is stored in PostgreSQL
- The backend is stateless except for the database

---
MIT License 