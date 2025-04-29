# backend/database.py
import os
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

# Load environment variables from .env file (primarily for DATABASE_URL)
load_dotenv()

# Create the SQLAlchemy database instance
db = SQLAlchemy()

def init_app(app):
    """
    Initializes the database connection using the DATABASE_URL from environment variables.
    Raises an error if the DATABASE_URL is not set.
    """
    # Get the database connection string from environment variables
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL environment variable not set. Please create a .env file with DATABASE_URL=postgresql://user:password@host:port/dbname")

    # Configure Flask-SQLAlchemy
    # Example: postgresql://jobuser:password123@localhost:5432/jobtrackerdb
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url

    # Disable modification tracking to save resources, as we don't use the event system
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Associate the SQLAlchemy instance with the Flask app
    db.init_app(app)

    print(f"Database initialized with URL: {db_url.split('@')[1]}") # Print host/db for confirmation, hide user/pass
