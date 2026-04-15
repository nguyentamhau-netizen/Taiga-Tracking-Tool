# Taiga QC Tracker

Local web app for QC sprint tracking on Taiga.

## Features

- Login with your own Taiga account
- Track User Stories, Tasks, and Issues
- Filter by one or many sprints
- View items without sprint
- Search across all item types
- Update status, assignee, sprint, watchers, and comment
- Export the current filtered list to Excel
- Frontend bundle served directly by FastAPI for easier team usage

## Tech Stack

- Backend: FastAPI
- Frontend: React + Vite

## Local Config

Copy `config.example.json` to `config.local.json`.

```json
{
  "taigaBaseUrl": "https://projects.kyanon.digital",
  "projectSlug": "amaze-all-in-one",
  "qcNames": [],
  "warningDaysBeforeSprintEnd": 3,
  "warningDaysWithoutUpdate": 5,
  "autoRefreshMinutes": 10
}
```

`config.local.json` is gitignored.

## Quick Start For Team

1. Clone the repo
2. Copy `config.example.json` to `config.local.json`
3. Fill your local QC names and Taiga base URL if needed
4. Double-click [Open Taiga QC Tracker.vbs](C:\Users\Archer\SC-NEW\taiga-qc-tracker\Open%20Taiga%20QC%20Tracker.vbs)

Or run:

```powershell
.\start-app.ps1
```

The script will:

- build the frontend bundle if needed
- create the backend virtual environment if needed
- install backend dependencies
- start the app
- open the browser at `http://127.0.0.1:8000`

## Development Mode

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e .
uvicorn app.main:app --reload --port 8000
```

```powershell
cd frontend
npm install
npm run build
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000)

## Frontend Dev Server

```powershell
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173)
