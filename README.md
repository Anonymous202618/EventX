# EventX — College Event Management System

A full-stack Flask college event platform based on the feature set discussed in the project PDFs.

## Included
- Student, Organizer and Admin roles
- Event discovery, filters and featured events
- Event registration + automatic waitlist promotion
- QR registration passes and organizer QR attendance scanner
- Automatic participation certificate generation (PDF)
- Event calendar
- Notifications and organizer announcements
- Feedback and ratings
- Attendance analytics + department breakdown
- Competition-ready models (teams/rounds/scores)
- Volunteer management
- Event budget tracking
- Risk management
- Venue conflict checking
- Admin approval workflow
- Dark/light theme toggle persisted with localStorage
- Demo seed data

## Stack
- Python + Flask
- Flask-SQLAlchemy / SQLAlchemy 2.x
- Flask-Login
- SQLite for local development
- Jinja2 + HTML/CSS/JavaScript
- Chart.js, FullCalendar and html5-qrcode through CDN
- qrcode for server-side QR image generation
- ReportLab for certificates

Flask 3.1.x supports Python 3.9+; current SQLAlchemy 2.x documentation is the reference style used here. See official docs cited in the accompanying answer.

## VS Code setup

### Windows PowerShell
```powershell
cd event_management_system
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python seed.py
python app.py
```

Open http://127.0.0.1:5000

### macOS/Linux
```bash
cd event_management_system
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python seed.py
python app.py
```

## Demo accounts
- Student: `akshat@eventx.local` / `Student@123`
- Organizer: `organizer@eventx.local` / `Organizer@123`
- Admin: `admin@eventx.local` / `Admin@123`

Change passwords and SECRET_KEY before any real deployment.

## Important note
The core application is self-contained. CDN libraries are used only for rich browser-side features (charts, calendar and QR camera scanning). Google Calendar, GitHub, SMTP email and production PostgreSQL are left as integration points rather than fake implementations.




## Documentation

The complete EventX User Guide is available here:

[📖 EventX User Guide](docs/EventX_User_Guide.pdf)

The guide explains how to use EventX as an Admin, Organizer, or Student and covers event management, registration, waitlists, QR attendance, notifications, certificates, competitions, resources, sponsorships, analytics, reports, and troubleshooting.## Documentation

The complete EventX User Guide is available here:

[📖 EventX User Guide](docs/EventX_User_Guide.pdf)

The guide explains how to use EventX as an Admin, Organizer, or Student and covers event management, registration, waitlists, QR attendance, notifications, certificates, competitions, resources, sponsorships, analytics, reports, and troubleshooting.