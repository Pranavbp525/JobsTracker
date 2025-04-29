# backend/Dockerfile

# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1 # Prevents python from writing pyc files
ENV PYTHONUNBUFFERED 1      # Prevents python from buffering stdout/stderr

# Set the working directory in the container
WORKDIR /app

# Install system dependencies: netcat for the wait script
# Use --no-install-recommends to keep image size down
# Add sed for fixing line endings
RUN apt-get update && apt-get install -y --no-install-recommends bash netcat-openbsd sed && rm -rf /var/lib/apt/lists/*

# Install pip requirements
# Copy only requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the wait script first
COPY ./wait-for-db.sh /usr/local/bin/wait-for-db.sh

# --- FIX: Ensure Unix line endings and make executable ---
RUN sed -i 's/\r$//' /usr/local/bin/wait-for-db.sh && \
    chmod +x /usr/local/bin/wait-for-db.sh

# Copy the rest of the application code into the working directory
COPY . .

# Expose the port the app runs on
# Make sure this matches the port in app.py (default 5001)
EXPOSE 5001

# Command to run the application using the wait script
# Use 0.0.0.0 to make it accessible outside the container
# Ensure FLASK_APP is set (can also be done in docker-compose.yml)
ENV FLASK_APP=app.py
# The wait script takes the host ('db') and the original command as arguments
CMD ["wait-for-db.sh", "db", "flask", "run", "--host=0.0.0.0", "--port=5001"]
