"""
Self-contained API tests for the Job Application Tracker backend.

These run against an in-memory SQLite database (no Postgres required) by setting
DATABASE_URL before importing the app. They are NOT part of any build step.

Run from the backend/ directory:

    DATABASE_URL=sqlite:///:memory: python -m pytest

(or just `python -m pytest` — the conftest/sets a default below.)
"""
import os
import sys
from datetime import timedelta

# Ensure the in-memory SQLite URL is set before importing app/database.
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

# Make `backend/` importable when pytest is run from the repo root or backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import app as app_module
from database import db
from models import DailyLog, get_eastern_today


@pytest.fixture
def client():
    app_module.app.config['TESTING'] = True
    with app_module.app.app_context():
        db.drop_all()
        db.create_all()
        # Re-seed default settings after the wipe.
        from models import get_settings
        get_settings()
    with app_module.app.test_client() as c:
        yield c
    with app_module.app.app_context():
        db.drop_all()


def _finish_today(client, count, apps=None, elapsed=60, notes=None):
    payload = {
        'completedCount': count,
        'elapsedSeconds': elapsed,
        'applications': apps if apps is not None else [],
    }
    if notes is not None:
        payload['notes'] = notes
    return client.post('/api/finish_day', json=payload)


def test_health(client):
    r = client.get('/api/health')
    assert r.status_code == 200
    assert r.get_json()['status'] == 'ok'


def test_state_empty(client):
    r = client.get('/api/state')
    data = r.get_json()
    assert data['dailyGoal'] == 5
    assert data['totalStreak'] == 0
    assert data['goalStreak'] == 0
    assert data['nextMilestone'] == 3


def test_finish_day_complete_and_streak(client):
    # goal is 5; logging 5 -> complete -> goalStreak 1
    r = _finish_today(client, 5, apps=[{'jobName': 'Eng', 'company': 'Acme', 'resume': 'v1'}])
    assert r.status_code == 200
    data = r.get_json()
    assert 'created' in data['message']
    assert data['goalStreak'] == 1
    assert data['totalStreak'] == 1
    # Re-finishing the same day is an upsert -> message says updated, still 1 day
    r2 = _finish_today(client, 6, apps=[{'jobName': 'Eng2', 'company': 'B', 'resume': 'v2'}])
    assert 'updated' in r2.get_json()['message']
    assert r2.get_json()['totalDaysLogged'] == 1


def test_finish_day_incomplete(client):
    r = _finish_today(client, 2)
    assert r.get_json()['goalStreak'] == 0
    assert r.get_json()['totalStreak'] == 1


def test_finish_day_validation(client):
    assert client.post('/api/finish_day', json={}).status_code == 400
    assert _finish_today(client, -1).status_code == 400
    bad = client.post('/api/finish_day', json={'completedCount': 1, 'elapsedSeconds': 1, 'applications': 'nope'})
    assert bad.status_code == 400


def test_session_includes_applications(client):
    # Regression test for the joinedload bug (db.joinedload -> AttributeError).
    today = get_eastern_today().isoformat()
    _finish_today(client, 1, apps=[{'jobName': 'X', 'company': 'Y', 'resume': 'Z'}], notes='hello')
    r = client.get(f'/api/session/{today}')
    assert r.status_code == 200
    data = r.get_json()
    assert data['found'] is True
    assert len(data['applications']) == 1
    assert data['notes'] == 'hello'


def test_edit_log(client):
    today = get_eastern_today().isoformat()
    _finish_today(client, 2)  # incomplete
    r = client.put(f'/api/logs/{today}', json={'completedCount': 5, 'notes': 'edited'})
    assert r.status_code == 200
    data = r.get_json()
    assert data['status'] == 'complete'
    assert data['notes'] == 'edited'
    assert data['goalStreak'] == 1


def test_edit_missing_log_404(client):
    r = client.put('/api/logs/2020-01-01', json={'completedCount': 5})
    assert r.status_code == 404


def test_delete_log(client):
    today = get_eastern_today().isoformat()
    _finish_today(client, 5)
    assert client.delete(f'/api/logs/{today}').status_code == 200
    assert client.get('/api/state').get_json()['totalDaysLogged'] == 0
    assert client.delete(f'/api/logs/{today}').status_code == 404


def test_invalid_date_format(client):
    assert client.get('/api/logs/not-a-date').status_code == 400
    assert client.put('/api/logs/not-a-date', json={}).status_code == 400
    assert client.delete('/api/logs/not-a-date').status_code == 400


def test_analytics(client):
    _finish_today(client, 5, apps=[{'jobName': 'A', 'company': 'C', 'resume': 'r'}])
    r = client.get('/api/analytics')
    assert r.status_code == 200
    data = r.get_json()
    assert data['totalDaysLogged'] == 1
    assert data['totalApplications'] == 5
    assert data['completionRate'] == 100.0
    assert data['longestGoalStreak'] == 1
    assert len(data['byWeekday']) == 7


def test_goal_history(client):
    client.put('/api/goal', json={'goal': 7})
    client.put('/api/goal', json={'goal': 7})  # no change -> no new history row
    client.put('/api/goal', json={'goal': 10})
    r = client.get('/api/goal_history')
    assert r.status_code == 200
    hist = r.get_json()['history']
    assert [h['dailyGoal'] for h in hist] == [7, 10]


def test_goal_validation(client):
    assert client.put('/api/goal', json={'goal': 0}).status_code == 400
    assert client.put('/api/goal', json={'goal': 'x'}).status_code == 400
    assert client.put('/api/goal', json={}).status_code == 400


def test_reset(client):
    _finish_today(client, 5)
    client.put('/api/goal', json={'goal': 9})
    assert client.delete('/api/reset').status_code == 200
    state = client.get('/api/state').get_json()
    assert state['totalDaysLogged'] == 0
    assert state['dailyGoal'] == 5  # re-seeded default
    assert client.get('/api/goal_history').get_json()['history'] == []


def test_server_time_eastern(client):
    r = client.get('/api/server_time')
    assert r.status_code == 200
    assert r.get_json()['tz'] in ('EST', 'EDT')
