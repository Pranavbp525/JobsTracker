# JobTracker Frontend

This is the frontend for the JobTracker application. It is a single-page HTML/JS app that interacts with the Flask backend to help users track their daily job application progress.

## Features
- Set and update your daily job application goal
- Start, pause, and finish daily logging sessions
- Add, edit, and mark job applications as done
- Visual progress bar and streak counters
- Calendar view of monthly progress (complete/incomplete days)
- View detailed logs for any day by clicking on the calendar
- Reset all data (dangerous!)
- Responsive, modern UI using Tailwind CSS and FontAwesome

## Usage
1. Make sure the backend server is running (see backend/README.md).
2. Open `index.html` in your browser (or serve it via a static file server).
3. The app will connect to the backend at `http://localhost:5001/api` by default.

## File Overview
- `index.html` - Main HTML file with embedded JavaScript and styles

## How it Works
- All data is stored on the backend (no local storage)
- The frontend fetches and updates state via REST API calls
- UI updates in real time as you log applications and finish days
- Calendar view shows your progress and allows viewing past logs

## API Integration
- The frontend expects the backend API to be available at `http://localhost:5001/api`
- See backend/README.md for API details

## Customization
- You can change the API base URL in the script section of `index.html` if needed
- Styles use Tailwind CSS (via CDN) and FontAwesome for icons

---
MIT License 