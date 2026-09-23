from datetime import datetime
import secrets

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


def registration_code():
    return f"EVT-{secrets.token_hex(5).upper()}"


def certificate_code():
    return f"CERT-{datetime.utcnow():%Y%m%d}-{secrets.token_hex(3).upper()}"


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="student")
    department = db.Column(db.String(80), default="CSE")
    roll_number = db.Column(db.String(40), unique=True, nullable=True)
    interests = db.Column(db.String(255), default="Technical,Workshop")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    registrations = db.relationship("Registration", back_populates="student", cascade="all, delete-orphan")
    volunteers = db.relationship("Volunteer", back_populates="student", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Club(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text, default="")


class Venue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    capacity = db.Column(db.Integer, nullable=False, default=100)
    location = db.Column(db.String(255), default="Campus")
    equipment = db.Column(db.String(255), default="Projector, Microphone")


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(60), nullable=False, default="Technical")
    event_type = db.Column(db.String(40), default="Workshop")
    eligibility = db.Column(db.String(255), default="All students")
    start_datetime = db.Column(db.DateTime, nullable=False)
    end_datetime = db.Column(db.DateTime, nullable=False)
    registration_deadline = db.Column(db.DateTime, nullable=False)
    max_participants = db.Column(db.Integer, nullable=False, default=100)
    status = db.Column(db.String(30), default="submitted")
    banner = db.Column(db.String(255), default="")
    featured = db.Column(db.Boolean, default=False)
    organizer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    club_id = db.Column(db.Integer, db.ForeignKey("club.id"), nullable=True)
    venue_id = db.Column(db.Integer, db.ForeignKey("venue.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organizer = db.relationship("User", foreign_keys=[organizer_id])
    club = db.relationship("Club")
    venue = db.relationship("Venue")
    registrations = db.relationship("Registration", back_populates="event", cascade="all, delete-orphan")
    announcements = db.relationship("Announcement", back_populates="event", cascade="all, delete-orphan")
    feedback = db.relationship("Feedback", back_populates="event", cascade="all, delete-orphan")
    volunteers = db.relationship("Volunteer", back_populates="event", cascade="all, delete-orphan")
    budget_items = db.relationship("BudgetItem", back_populates="event", cascade="all, delete-orphan")
    risks = db.relationship("Risk", back_populates="event", cascade="all, delete-orphan")
    checklist_items = db.relationship("ChecklistItem", back_populates="event", cascade="all, delete-orphan")
    resource_requests = db.relationship("ResourceRequest", back_populates="event", cascade="all, delete-orphan")
    sponsors = db.relationship("Sponsor", back_populates="event", cascade="all, delete-orphan")

    @property
    def active_registrations(self):
        return sum(1 for r in self.registrations if r.status == "registered")

    @property
    def waitlist_count(self):
        return sum(1 for r in self.registrations if r.status == "waitlisted")

    @property
    def attendance_count(self):
        return sum(1 for r in self.registrations if r.attendance)

    @property
    def progress_percent(self):
        return round(min(100, (self.active_registrations / self.max_participants) * 100)) if self.max_participants else 0


class Registration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(
        db.Integer,
        db.ForeignKey("event.id"),
        nullable=False
    )
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )
    registration_number = db.Column(
        db.String(80),
        unique=True,
        nullable=False,
        default=registration_code
    )
    status = db.Column(
        db.String(30),
        default="registered"
    )
    registered_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    event = db.relationship(
        "Event",
        back_populates="registrations"
    )
    student = db.relationship(
        "User",
        back_populates="registrations"
    )

    attendances = db.relationship(
        "Attendance",
        back_populates="registration",
        cascade="all, delete-orphan",
        order_by="Attendance.check_in_time"
    )

    @property
    def attendance(self):
        return self.attendances[0] if self.attendances else None

    certificate = db.relationship(
        "Certificate",
        back_populates="registration",
        uselist=False,
        cascade="all, delete-orphan"
    )


class Attendance(db.Model):
    id = db.Column(
        db.Integer,
        primary_key=True
    )

    registration_id = db.Column(
        db.Integer,
        db.ForeignKey("registration.id"),
        nullable=False
    )

    check_in_time = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    session_label = db.Column(
        db.String(100),
        default="Main Session"
    )

    status = db.Column(
        db.String(30),
        default="present"
    )

    registration = db.relationship(
        "Registration",
        back_populates="attendances"
    )

    __table_args__ = (
        db.UniqueConstraint(
            "registration_id",
            "session_label",
            name="uq_attendance_registration_session"
        ),
    )
class Certificate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    registration_id = db.Column(db.Integer, db.ForeignKey("registration.id"), nullable=True)
    certificate_number = db.Column(db.String(100), unique=True, nullable=False, default=certificate_code)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    file_path = db.Column(db.String(255), default="")

    event = db.relationship("Event")
    student = db.relationship("User")
    registration = db.relationship("Registration", back_populates="certificate")


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User")


class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    event = db.relationship("Event", back_populates="announcements")
    author = db.relationship("User")


class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    rating = db.Column(db.Integer, default=5)
    speaker_rating = db.Column(db.Integer, default=5)
    organization_rating = db.Column(db.Integer, default=5)
    venue_rating = db.Column(db.Integer, default=5)
    comment = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    event = db.relationship("Event", back_populates="feedback")
    student = db.relationship("User")


class Volunteer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    assignment = db.Column(db.String(100), default="Registration Desk")
    status = db.Column(db.String(30), default="assigned")
    event = db.relationship("Event", back_populates="volunteers")
    student = db.relationship("User", back_populates="volunteers")


class BudgetItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    description = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(80), default="Other")
    amount = db.Column(db.Float, default=0)
    spent_at = db.Column(db.DateTime, default=datetime.utcnow)
    event = db.relationship("Event", back_populates="budget_items")


class Risk(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    probability = db.Column(db.String(30), default="Medium")
    impact = db.Column(db.String(30), default="Medium")
    mitigation = db.Column(db.Text, default="")
    status = db.Column(db.String(30), default="Open")
    event = db.relationship("Event", back_populates="risks")

class ChecklistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(
        db.Integer,
        db.ForeignKey("event.id"),
        nullable=False
    )
    title = db.Column(
        db.String(180),
        nullable=False
    )
    completed = db.Column(
        db.Boolean,
        default=False
    )
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    event = db.relationship(
        "Event",
        back_populates="checklist_items"
    )


class Resource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    quantity = db.Column(db.Integer, default=1)
    description = db.Column(db.String(255), default="")


class ResourceRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    resource_id = db.Column(db.Integer, db.ForeignKey("resource.id"), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    status = db.Column(db.String(30), default="pending")
    event = db.relationship("Event", back_populates="resource_requests")
    resource = db.relationship("Resource")

class Sponsor(db.Model):
    id = db.Column(
        db.Integer,
        primary_key=True
    )

    event_id = db.Column(
        db.Integer,
        db.ForeignKey("event.id"),
        nullable=False
    )

    name = db.Column(
        db.String(180),
        nullable=False
    )

    contribution = db.Column(
        db.Float,
        default=0
    )

    contact = db.Column(
        db.String(180),
        default=""
    )

    promised_benefits = db.Column(
        db.Text,
        default=""
    )

    status = db.Column(
        db.String(30),
        default="Prospective"
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    event = db.relationship(
        "Event",
        back_populates="sponsors"
    )


class Competition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False, unique=True)
    team_allowed = db.Column(db.Boolean, default=True)
    status = db.Column(db.String(30), default="upcoming")
    event = db.relationship("Event")
    teams = db.relationship("Team", back_populates="competition", cascade="all, delete-orphan")
    rounds = db.relationship("CompetitionRound", back_populates="competition", cascade="all, delete-orphan")


class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey("competition.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    captain_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    points = db.Column(db.Float, default=0)
    competition = db.relationship("Competition", back_populates="teams")
    captain = db.relationship("User")
    members = db.relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")


class TeamMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    team = db.relationship("Team", back_populates="members")
    student = db.relationship("User")


class CompetitionRound(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey("competition.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    round_number = db.Column(db.Integer, default=1)
    status = db.Column(db.String(30), default="upcoming")
    competition = db.relationship("Competition", back_populates="rounds")


class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey("competition_round.id"), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)
    score = db.Column(db.Float, default=0)


class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=True)
    action = db.Column(db.String(180), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User")
    event = db.relationship("Event")
class EventGallery(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    event_id = db.Column(
        db.Integer,
        db.ForeignKey("event.id"),
        nullable=False,
        index=True
    )

    image_path = db.Column(
        db.String(255),
        nullable=False
    )

    caption = db.Column(
        db.String(255),
        default=""
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    event = db.relationship(
        "Event"
    )