# EventX - College Event Management System

EventX is a full-stack Flask-based college event management system designed to manage the complete event lifecycle from creation and approval to registration, attendance, feedback, certificates, analytics, and reporting.

## Overview

EventX provides separate workflows for Students, Organizers, and Administrators.

The system combines event planning, participant management, attendance tracking, communication, competition management, operational planning, sponsorship management, resource management, and reporting into one platform.

## Features

### Student

- Browse and discover college events
- Search and filter events
- View event details
- Register for events
- Automatic waitlist handling
- Receive registration and event notifications
- View registered events
- Access QR registration passes
- Submit event feedback and ratings
- View attendance-related information
- Download participation certificates
- View competition information and leaderboards
- Use the event calendar

### Organizer

- Create and manage events
- Submit events for admin approval
- View event registrations
- Manage event attendance
- QR-based participant check-in
- Support multiple attendance sessions
- View attendance analytics
- View department participation
- Send announcements to registered students
- Manage volunteers
- Track event budgets
- Manage event risks
- Maintain event preparation checklists
- Request event resources
- Manage event gallery content
- Manage competition teams and rounds
- Record competition scores
- View leaderboards

### Administrator

- Manage users
- Manage clubs
- Manage venues
- Approve submitted events
- Manage shared resources
- Review resource requests
- Manage event sponsorships
- View all events
- Generate event reports
- Download event reports as PDF
- Support administrative event operations

## Event Lifecycle

Organizer creates event
        |
        v
Admin reviews and approves
        |
        v
Students discover the event
        |
        v
Students register
        |
        v
Capacity and waitlist handling
        |
        v
Organizer prepares the event
        |
        v
QR attendance check-in
        |
        v
Attendance analytics
        |
        v
Student feedback
        |
        v
Participation certificates
        |
        v
Final event report

## Technology Stack

### Backend

- Python
- Flask
- Flask-SQLAlchemy
- SQLAlchemy
- Flask-Login
- SQLite

### Frontend

- HTML
- CSS
- JavaScript
- Jinja2 templates

### Browser Libraries

- Chart.js
- FullCalendar
- html5-qrcode

### Additional Tools

- qrcode for QR image generation
- ReportLab for PDF certificate and report generation

## Project Structure

EventX/
    app.py
    models.py
    run.py
    seed.py
    requirements.txt
    PROJECT_MAP.md
    .env.example
    .gitignore

    docs/
        EventX_User_Guide.pdf

    static/
        css/
        js/
        images/

    templates/
        admin/
        organizer/
        student/
        components/
        ...

## Requirements

Make sure the following are installed:

- Python 3.9 or newer
- Git
- Visual Studio Code
- A modern web browser

## Installation - Windows

Open PowerShell or the VS Code terminal.

    cd event_management_system

Create a virtual environment:

    py -m venv .venv

Activate the virtual environment:

    .\.venv\Scripts\Activate.ps1

Install the required dependencies:

    pip install -r requirements.txt

Create demo data:

    python seed.py

Start the application:

    python app.py

Then open:

    http://127.0.0.1:5000

## Installation - macOS / Linux

Open Terminal and navigate to the project directory.

    cd event_management_system

Create a virtual environment:

    python3 -m venv .venv

Activate it:

    source .venv/bin/activate

Install the required dependencies:

    pip install -r requirements.txt

Create demo data:

    python seed.py

Start the application:

    python app.py

Then open:

    http://127.0.0.1:5000

## Demo Accounts

These accounts are intended for local demonstration and testing only.

### Student

Email: akshat@eventx.local

Password: Student@123

### Organizer

Email: organizer@eventx.local

Password: Organizer@123

### Admin

Email: admin@eventx.local

Password: Admin@123

Change passwords and configure a secure SECRET_KEY before any real deployment.

## Documentation

The complete EventX User Guide is available here:

[EventX User Guide](docs/EventX_User_Guide.pdf)

The guide explains how to use EventX as an Admin, Organizer, or Student and covers event management, registration, waitlists, QR attendance, notifications, certificates, competitions, resources, sponsorships, analytics, reports, and troubleshooting.

## Security and Configuration

Environment-specific configuration should be stored in a .env file rather than committed to GitHub.

The repository includes:

    .env.example

Use it as a starting point for local configuration.

Private runtime data such as the local SQLite database and environment secrets are excluded through .gitignore.

## Development Notes

The core application is self-contained for local development.

The project uses CDN-based browser libraries for charts, calendar views, and QR camera scanning.

External services such as production SMTP email, PostgreSQL, Google Calendar, and other integrations can be added separately for deployment.

## GitHub

This is a collaborative GitHub repository for the EventX group project.

Team members can contribute using Git branches and pull requests.

Repository:

https://github.com/Anonymous202618/EventX

## License

This project was created as a college group project for educational and demonstration purposes.