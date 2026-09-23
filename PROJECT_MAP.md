# Project map

## Student
- Landing / discovery
- Search and filters
- Event details
- Registration and waitlist
- QR pass
- My Events
- Calendar
- Certificates
- Feedback
- Profile
- Notifications
- Persistent dark/light theme

## Organizer
- Dashboard
- Event submission
- Venue conflict checking
- Registrations
- QR attendance scanner + manual fallback
- Announcements
- Certificate generation
- Analytics / department participation
- Volunteers
- Budget
- Risks
- Command Center

## Admin
- Dashboard
- Event approvals
- Event directory
- User directory
- Club management
- Venue management

## Database entities
User, Club, Venue, Event, Registration, Attendance, Certificate, Notification,
Announcement, Feedback, Volunteer, BudgetItem, Risk, Resource, ResourceRequest,
Competition, Team, TeamMember, CompetitionRound, Score, ActivityLog.

## Data flow
Organizer creates event → admin approves → event is published → student registers →
registration code/QR generated → organizer scans at venue → attendance stored →
certificate can be generated → student downloads certificate → feedback feeds analytics.
