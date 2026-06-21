"""
pytest bootstrap. Ensures the backend tests run against an in-memory SQLite DB
without needing Postgres or a .env file. This is import-time so it runs before
the app module (which reads DATABASE_URL on import) is loaded.
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
