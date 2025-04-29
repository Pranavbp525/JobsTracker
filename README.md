# Job Application Tracker

A web application designed to help users track their daily job application progress, set goals, maintain streaks, and visualize their activity on a calendar. Inspired by workout logging apps like Hevy, this tool aims to bring similar discipline and tracking to the job search process.

## Features

* **Daily Goal Setting:** Set a target number of job applications to complete each day.
* **Session Logging:**
    * Start a timed logging session for the current day.
    * Add individual job applications (Job Title, Company, Resume Used) to a table.
    * Mark applications as 'Done'.
    * Pause and Resume the logging timer and activity.
* **Progress Tracking:** A progress bar shows the percentage of the daily goal achieved based on marked 'Done' applications.
* **Flexible Finishing:** Finish logging for the day at any time.
    * If the goal is met or exceeded, the day is marked as 'Complete' (Blue indicator).
    * If the goal is not met, the day is marked as 'Incomplete' (Red indicator).
* **Resume Logging:** Continue logging applications for the current day even after finishing once (entries are added to the existing log).
* **Dual Streak Counters:**
    * **Total Streak:** Counts consecutive days where *any* logging was finished (Complete or Incomplete).
    * **Goal Streak:** Counts consecutive days where the daily goal was met or exceeded ('Complete' status).
* **Calendar View:**
    * Monthly calendar interface.
    * Days with completed goals are marked with a blue circle.
    * Days logged but with unmet goals are marked with a red circle.
    * Click on a logged day (red or blue) to view the list of applications submitted on that specific day.
* **Persistence:** All data (settings, logs, applications) is stored in a PostgreSQL database.
* **Dockerized:** Easy setup and deployment using Docker and Docker Compose.

## Prerequisites

* [Docker](https://docs.docker.com/get-docker/)
* [Docker Compose](https://docs.docker.com/compose/install/) (Usually included with Docker Desktop)

## Project Structure

job_tracker/├── backend/            # Python Flask API and database logic│   ├── app.py│   ├── models.py│   ├── database.py│   ├── requirements.txt│   ├── Dockerfile│   └── .dockerignore│   └── wait-for-db.sh  # Script to ensure DB is ready│   └── .env            # Local development environment variables (ignored by git)├── frontend/           # Static HTML, CSS, JS files│   └── index.html└── docker-compose.yml  # Docker Compose configuration file└── README.md           # This file
## Setup and Running

1.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url>
    cd job_tracker
    ```

2.  **Configure Database Credentials:**
    * Open the `docker-compose.yml` file.
    * Locate the `db` service section.
    * Change the `POSTGRES_PASSWORD` value (`your_strong_password`) to a secure password.
    * Locate the `backend` service section.
    * Update the `DATABASE_URL` environment variable to use the **same password** you set for `POSTGRES_PASSWORD`. The line should look like:
        ```yaml
        DATABASE_URL: postgresql://jobtracker_user:YOUR_NEW_PASSWORD@db:5432/jobtracker_db
        ```
        (Replace `YOUR_NEW_PASSWORD` with the password you chose).

3.  **Build and Run with Docker Compose:**
    * Open your terminal in the root `job_tracker` directory (where `docker-compose.yml` is located).
    * Run the following command:
        ```bash
        docker-compose up --build
        ```
        * `--build` ensures the backend image is built correctly the first time or after code changes.
        * Add `-d` at the end (`docker-compose up --build -d`) to run in detached mode (background).

4.  **Database Initialization:** The first time you run `docker-compose up`, the PostgreSQL database will be initialized, and the backend application will create the necessary tables. The `wait-for-db.sh` script ensures the backend waits until the database is ready before attempting to connect.

## Usage

1.  **Access the Application:** Open your web browser and navigate to:
    `http://localhost:8080`
    (Assuming you haven't changed the port mapping in `docker-compose.yml`).

2.  **Set Daily Goal:** Adjust the number in the "Daily Goal" input field. This value is saved automatically.

3.  **Start Logging:**
    * Click the "Start Logging" button.
    * The timer will start, and the logging table will appear.

4.  **Add Applications:**
    * Click the "+ Add Application" button to add a new row.
    * Fill in the Job/Position, Company, and Resume Used details.
    * Click the checkmark button in the "Done" column for each application submitted. The progress bar will update.

5.  **Pause/Resume:**
    * Click the "Pause" button to stop the timer and disable adding/editing logs.
    * Click the "Resume" button to continue the timer and re-enable logging.

6.  **Finish Day:**
    * Click the "Finish Day" button at any time during an active session.
    * The session details (total count, elapsed time, application list) are saved to the database.
    * The calendar will update with a **blue circle** if the goal was met or a **red circle** if it wasn't.
    * Streak counters will update based on the day's status.
    * The logging area will disappear.

7.  **Continue Logging (Same Day):**
    * If you have already finished logging for the day, the "Start Logging" button will change to "Continue Logging".
    * Clicking it will fetch the previously logged count and time, allowing you to add more applications. The previously logged applications will appear in the table.
    * Finishing again will update the day's log entry with the new total count, time, and application list.

8.  **View Past Logs:**
    * Click on any day in the calendar that has a red or blue circle.
    * A table will appear below the calendar showing the applications logged on that specific day, along with the day's final status (Complete/Incomplete).
    * Clicking a different logged day will update the display. Clicking an unlogged day or navigating months will hide the display.

9.  **Reset Data:**
    * Click the "Reset All Data" button.
    * Confirm the action in the modal popup.
    * **Warning:** This will permanently delete all settings, daily logs, and application entries from the database.

## Technologies Used

* **Frontend:** HTML, Tailwind CSS (via CDN), JavaScript, Font Awesome
* **Backend:** Python, Flask, Flask-SQLAlchemy, Flask-CORS, psycopg2
* **Database:** PostgreSQL
* **Containerization:** Docker, Docker Compose
