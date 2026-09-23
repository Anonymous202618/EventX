import os
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

import qrcode
from dotenv import load_dotenv
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from sqlalchemy import func, or_
from werkzeug.utils import secure_filename

from models import (
    ActivityLog, Score, Announcement, Attendance, BudgetItem, Certificate, ChecklistItem, Club, Competition,
    CompetitionRound, Event, Feedback, Notification, Registration, Resource, ResourceRequest,
    Risk, Sponsor, Team, TeamMember, User, Venue, Volunteer, db, EventGallery, 
)

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
IS_VERCEL = os.getenv("VERCEL") == "1"

if IS_VERCEL:
    DB_PATH = Path("/tmp/eventx.db")
    UPLOAD_PATH = Path("/tmp/eventx_uploads")
else:
    DB_PATH = BASE_DIR / "instance" / "eventx.db"
    UPLOAD_PATH = BASE_DIR / "static" / "uploads"

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{DB_PATH}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = str(UPLOAD_PATH)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

UPLOAD_PATH.mkdir(parents=True, exist_ok=True) 
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.context_processor
def inject_globals():
    unread = 0
    if current_user.is_authenticated:
        unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return {"unread_notifications": unread, "now": datetime.utcnow()}


def role_required(*roles):
    def decorator(fn):
        from functools import wraps

        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            user_role = (current_user.role or "").strip().lower()
            allowed_roles = {
                str(role).strip().lower()
                for role in roles
            }

            if user_role not in allowed_roles:
                abort(403)

            return fn(*args, **kwargs)

        return wrapped

    return decorator

def log_action(action, event=None):
    db.session.add(ActivityLog(user_id=current_user.id if current_user.is_authenticated else None, event_id=event.id if event else None, action=action))


def notify(user_id, title, message):
    db.session.add(Notification(user_id=user_id, title=title, message=message))


def parse_dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def event_overlap(venue_id, start_dt, end_dt, ignore_id=None):

    q = Event.query.filter(
        Event.venue_id == venue_id,
        Event.start_datetime < end_dt,
        Event.end_datetime > start_dt,
        Event.status.in_([
            "submitted",
            "approved",
            "published",
            "live"
        ])
    )

    if ignore_id:
        q = q.filter(Event.id != ignore_id)

    return q.first()


def approved_resource_quantity(resource_id, event, exclude_request_id=None):
    """
    Return the number of units of a resource already allocated
    to overlapping events.
    """

    approved_requests = ResourceRequest.query.filter_by(
        resource_id=resource_id,
        status="approved"
    ).all()

    used = 0

    for resource_request in approved_requests:

        if (
            exclude_request_id is not None
            and resource_request.id == exclude_request_id
        ):
            continue

        other_event = resource_request.event

        if not other_event:
            continue

        overlaps = (
            other_event.start_datetime < event.end_datetime
            and other_event.end_datetime > event.start_datetime
        )

        if overlaps:
            used += resource_request.quantity

    return used


def available_resource_quantity(resource, event):
    """
    Return available units for this event based on
    approved requests for overlapping events.
    """

    used = approved_resource_quantity(
        resource.id,
        event
    )

    return max(
        0,
        resource.quantity - used
    )

@app.errorhandler(403)
def forbidden(error):
    return render_template("403.html"), 403


@app.route("/")
def home():
    featured = Event.query.filter_by(status="published", featured=True).order_by(Event.start_datetime).limit(3).all()
    upcoming = Event.query.filter(Event.status.in_(["approved", "published", "live"]), Event.start_datetime >= datetime.utcnow()).order_by(Event.start_datetime).limit(6).all()
    return render_template("home.html", featured=featured, upcoming=upcoming)
@app.route("/events/<int:event_id>/leaderboard")
@login_required
def event_leaderboard(event_id):

    event = db.get_or_404(Event, event_id)

    competition = Competition.query.filter_by(
        event_id=event.id
    ).first()

    if not competition:
        flash(
            "This event does not have a competition leaderboard.",
            "warning"
        )

        return redirect(
            url_for(
                "event_detail",
                event_id=event.id
            )
        )

    teams = Team.query.filter_by(
        competition_id=competition.id
    ).order_by(
        Team.points.desc(),
        Team.name.asc()
    ).all()

    rounds = CompetitionRound.query.filter_by(
        competition_id=competition.id
    ).order_by(
        CompetitionRound.round_number
    ).all()

    return render_template(
        "leaderboard.html",
        event=event,
        competition=competition,
        teams=teams,
        rounds=rounds
    )

@app.route("/events")
def events():
    q = Event.query.filter(Event.status.in_(["approved", "published", "live"]))
    search = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    event_type = request.args.get("type", "").strip()
    if search:
        like = f"%{search}%"
        q = q.filter(or_(Event.title.ilike(like), Event.description.ilike(like), Event.category.ilike(like)))
    if category:
        q = q.filter_by(category=category)
    if event_type:
        q = q.filter_by(event_type=event_type)
    events_list = q.order_by(Event.start_datetime).all()
    categories = [x[0] for x in db.session.query(Event.category).distinct().order_by(Event.category).all()]
    return render_template("events.html", events=events_list, categories=categories, search=search, category=category, event_type=event_type)


@app.route("/events/<int:event_id>")
def event_detail(event_id):
    event = db.get_or_404(Event, event_id)

    registration = None
    feedback_submitted = False

    if current_user.is_authenticated and current_user.role == "student":
        registration = Registration.query.filter_by(
            event_id=event.id,
            student_id=current_user.id
        ).first()

        feedback_submitted = (
            Feedback.query.filter_by(
                event_id=event.id,
                student_id=current_user.id
            ).first()
            is not None
        )
    gallery = EventGallery.query.filter_by(
    event_id=event.id
    ).order_by(
    EventGallery.created_at.desc()
    ).all()

    avg = (
        db.session.query(func.avg(Feedback.rating))
        .filter_by(event_id=event.id)
        .scalar()
    )

    return render_template(
    "event_detail.html",
    event=event,
    registration=registration,
    avg_rating=round(avg or 0, 1),
    feedback_submitted=feedback_submitted,
    gallery=gallery,

    )
@app.route(
    "/organizer/events/<int:event_id>/competition/scores",
    methods=["GET", "POST"]
)

@role_required("organizer", "admin")
def organizer_competition_scores(event_id):

    event = db.get_or_404(Event, event_id)

    if (
        current_user.role == "organizer"
        and event.organizer_id != current_user.id
    ):
        abort(403)

    competition = Competition.query.filter_by(
        event_id=event.id
    ).first()

    if not competition:
        flash(
            "This event does not have a competition.",
            "warning"
        )

        return redirect(
            url_for(
                "organizer_competition",
                event_id=event.id
            )
        )

    rounds = CompetitionRound.query.filter_by(
        competition_id=competition.id
    ).order_by(
        CompetitionRound.round_number
    ).all()

    teams = Team.query.filter_by(
        competition_id=competition.id
    ).order_by(
        Team.name
    ).all()


    if request.method == "POST":

        round_id = request.form.get(
            "round_id",
            type=int
        )

        team_id = request.form.get(
            "team_id",
            type=int
        )

        score_value = request.form.get(
            "score",
            ""
        ).strip()


        selected_round = CompetitionRound.query.filter_by(
            id=round_id,
            competition_id=competition.id
        ).first()

        team = Team.query.filter_by(
            id=team_id,
            competition_id=competition.id
        ).first()


        if not selected_round:
            flash(
                "Competition round not found.",
                "danger"
            )

        elif not team:
            flash(
                "Competition team not found.",
                "danger"
            )

        elif selected_round.status == "upcoming":
            flash(
                "You cannot enter scores for an upcoming round.",
                "warning"
            )

        else:

            try:
                score_value = float(score_value)

            except ValueError:
                score_value = None


            if score_value is None:
                flash(
                    "Enter a valid numeric score.",
                    "warning"
                )

            elif score_value < 0:
                flash(
                    "Score cannot be negative.",
                    "warning"
                )

            else:

                existing_score = Score.query.filter_by(
                    round_id=selected_round.id,
                    team_id=team.id
                ).first()


                if existing_score:

                    existing_score.score = score_value

                else:

                    db.session.add(
                        Score(
                            round_id=selected_round.id,
                            team_id=team.id,
                            score=score_value
                        )
                    )


                # Recalculate total points for every team
                # from all recorded round scores.
                for competition_team in teams:

                    total = (
                        db.session.query(
                            db.func.coalesce(
                                db.func.sum(Score.score),
                                0
                            )
                        )
                        .filter(
                            Score.team_id == competition_team.id,
                            Score.round_id.in_(
                                [r.id for r in rounds]
                            )
                        )
                        .scalar()
                    )

                    competition_team.points = float(
                        total or 0
                    )


                log_action(
                    f"Updated score for {team.name} "
                    f"in {selected_round.name} "
                    f"for {event.title}",
                    event
                )

                db.session.commit()

                flash(
                    f"{team.name} scored {score_value:g} "
                    f"in {selected_round.name}.",
                    "success"
                )


        return redirect(
            url_for(
                "organizer_competition_scores",
                event_id=event.id,
                round_id=round_id
            )
        )


    selected_round_id = request.args.get(
        "round_id",
        type=int
    )

    selected_round = None

    if selected_round_id:
        selected_round = CompetitionRound.query.filter_by(
            id=selected_round_id,
            competition_id=competition.id
        ).first()

    if not selected_round and rounds:
        selected_round = rounds[0]


    scores = {}

    if selected_round:

        existing_scores = Score.query.filter_by(
            round_id=selected_round.id
        ).all()

        scores = {
            score.team_id: score.score
            for score in existing_scores
        }


    return render_template(
        "organizer/competition_scores.html",
        event=event,
        competition=competition,
        rounds=rounds,
        teams=teams,
        selected_round=selected_round,
        scores=scores
    )
@app.route("/student/events/<int:event_id>/leaderboard")
@role_required("student")
def student_event_leaderboard(event_id):

    event = db.get_or_404(Event, event_id)

    competition = Competition.query.filter_by(
        event_id=event.id
    ).first()

    if not competition:
        flash(
            "This event does not have a competition leaderboard.",
            "warning"
        )

        return redirect(
            url_for(
                "event_detail",
                event_id=event.id
            )
        )

    teams = Team.query.filter_by(
        competition_id=competition.id
    ).order_by(
        Team.points.desc(),
        Team.name.asc()
    ).all()

    rounds = CompetitionRound.query.filter_by(
        competition_id=competition.id
    ).order_by(
        CompetitionRound.round_number
    ).all()

    return render_template(
        "leaderboard.html",
        event=event,
        competition=competition,
        teams=teams,
        rounds=rounds
    )
@app.route("/student/events/<int:event_id>/competition", methods=["GET", "POST"])
@role_required("student")
def student_competition(event_id):

    event = db.get_or_404(Event, event_id)

    competition = Competition.query.filter_by(
        event_id=event.id
    ).first()

    if not competition:
        flash(
            "This event does not have a competition.",
            "warning"
        )
        return redirect(
            url_for(
                "event_detail",
                event_id=event.id
            )
        )

    if not competition.team_allowed:
        flash(
            "Team registration is not enabled for this competition.",
            "warning"
        )
        return redirect(
            url_for(
                "event_detail",
                event_id=event.id
            )
        )

    # Student must have a confirmed registration
    # for the event.
    registration = Registration.query.filter_by(
        event_id=event.id,
        student_id=current_user.id,
        status="registered"
    ).first()

    if not registration:
        flash(
            "You must be registered for the event before joining a team.",
            "warning"
        )
        return redirect(
            url_for(
                "event_detail",
                event_id=event.id
            )
        )


    # Find the student's existing team.
    my_membership = (
        db.session.query(TeamMember)
        .join(Team)
        .filter(
            Team.competition_id == competition.id,
            TeamMember.student_id == current_user.id
        )
        .first()
    )

    my_team = (
        my_membership.team
        if my_membership
        else None
    )


    if request.method == "POST":

        action = request.form.get(
            "action",
            ""
        ).strip()


        # =====================================================
        # CREATE TEAM
        # =====================================================

        if action == "create_team":

            if my_team:
                flash(
                    "You are already a member of a team.",
                    "info"
                )

            else:

                team_name = request.form.get(
                    "team_name",
                    ""
                ).strip()

                if not team_name:
                    flash(
                        "Enter a team name.",
                        "warning"
                    )

                elif len(team_name) > 120:
                    flash(
                        "Team name is too long.",
                        "warning"
                    )

                else:

                    name_taken = any(
                        team.name.strip().lower()
                        == team_name.lower()
                        for team in competition.teams
                    )

                    if name_taken:
                        flash(
                            "That team name is already being used.",
                            "warning"
                        )

                    else:

                        team = Team(
                            competition_id=competition.id,
                            name=team_name,
                            captain_id=current_user.id,
                            points=0
                        )

                        db.session.add(team)
                        db.session.flush()

                        # Captain is automatically a team member.
                        captain_member = TeamMember(
                            team_id=team.id,
                            student_id=current_user.id
                        )

                        db.session.add(
                            captain_member
                        )

                        log_action(
                            f"Created team {team.name} "
                            f"for {event.title}",
                            event
                        )

                        db.session.commit()

                        flash(
                            f"Team '{team.name}' created successfully.",
                            "success"
                        )


        # =====================================================
        # ADD MEMBER
        # =====================================================

        elif action == "add_member":

            if not my_team:
                flash(
                    "Create a team first.",
                    "warning"
                )

            elif my_team.captain_id != current_user.id:
                flash(
                    "Only the team captain can add members.",
                    "warning"
                )

            else:

                member_email = request.form.get(
                    "member_email",
                    ""
                ).strip().lower()

                if not member_email:
                    flash(
                        "Enter the student's email.",
                        "warning"
                    )

                else:

                    member = User.query.filter_by(
                        email=member_email
                    ).first()

                    if not member:
                        flash(
                            "No EventX user was found with that email.",
                            "warning"
                        )

                    elif member.role != "student":
                        flash(
                            "Only student accounts can join competition teams.",
                            "warning"
                        )

                    elif member.id == current_user.id:
                        flash(
                            "You are already the team captain.",
                            "info"
                        )

                    else:

                        member_registration = Registration.query.filter_by(
                            event_id=event.id,
                            student_id=member.id,
                            status="registered"
                        ).first()

                        if not member_registration:
                            flash(
                                "That student must be registered for the event first.",
                                "warning"
                            )

                        else:

                            existing_membership = (
                                db.session.query(TeamMember)
                                .join(Team)
                                .filter(
                                    Team.competition_id == competition.id,
                                    TeamMember.student_id == member.id
                                )
                                .first()
                            )

                            if existing_membership:
                                flash(
                                    "That student is already in a team.",
                                    "warning"
                                )

                            else:

                                db.session.add(
                                    TeamMember(
                                        team_id=my_team.id,
                                        student_id=member.id
                                    )
                                )

                                log_action(
                                    f"Added {member.name} to "
                                    f"team {my_team.name}",
                                    event
                                )

                                db.session.commit()

                                flash(
                                    f"{member.name} added to the team.",
                                    "success"
                                )


        # =====================================================
        # REMOVE MEMBER
        # =====================================================

        elif action == "remove_member":

            if not my_team:
                flash(
                    "You are not in a team.",
                    "warning"
                )

            elif my_team.captain_id != current_user.id:
                flash(
                    "Only the team captain can remove members.",
                    "warning"
                )

            else:

                member_id = request.form.get(
                    "member_id",
                    type=int
                )

                member = TeamMember.query.filter_by(
                    id=member_id,
                    team_id=my_team.id
                ).first()

                if not member:
                    flash(
                        "Team member not found.",
                        "warning"
                    )

                elif member.student_id == my_team.captain_id:
                    flash(
                        "The team captain cannot be removed.",
                        "warning"
                    )

                else:

                    member_name = member.student.name

                    db.session.delete(member)

                    log_action(
                        f"Removed {member_name} from "
                        f"team {my_team.name}",
                        event
                    )

                    db.session.commit()

                    flash(
                        f"{member_name} removed from the team.",
                        "info"
                    )


        return redirect(
            url_for(
                "student_competition",
                event_id=event.id
            )
        )


    teams = Team.query.filter_by(
        competition_id=competition.id
    ).order_by(
        Team.points.desc(),
        Team.name
    ).all()


    return render_template(
        "student/competition.html",
        event=event,
        competition=competition,
        my_team=my_team,
        teams=teams
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("portal_redirect"))
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        department = request.form.get("department", "CSE")
        roll_number = request.form.get("roll_number", "").strip() or None
        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "danger")
            return redirect(url_for("register"))
        user = User(name=name, email=email, role="student", department=department, roll_number=roll_number)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Welcome to EventX!", "success")
        return redirect(url_for("student_dashboard"))
    return render_template("auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("portal_redirect"))
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))
        login_user(user)
        flash(f"Welcome back, {user.name.split()[0]}!", "success")
        return redirect(url_for("portal_redirect"))
    return render_template("auth.html", mode="login")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/portal")
@login_required
def portal_redirect():
    return redirect(url_for({"student": "student_dashboard", "organizer": "organizer_dashboard", "admin": "admin_dashboard"}[current_user.role]))


# -------------------- STUDENT --------------------
@app.route("/student/dashboard")
@role_required("student")
def student_dashboard():
    registrations = Registration.query.filter_by(student_id=current_user.id).all()
    upcoming = [r for r in registrations if r.status == "registered" and r.event.start_datetime >= datetime.utcnow()]
    upcoming.sort(key=lambda r: r.event.start_datetime)
    certificates = Certificate.query.filter_by(student_id=current_user.id).count()
    attended = sum(1 for r in registrations if r.attendance)
    recommended = Event.query.filter(Event.status.in_(["published", "approved"]), Event.category.in_([x.strip() for x in (current_user.interests or "Technical").split(",")]), Event.start_datetime >= datetime.utcnow()).order_by(Event.start_datetime).limit(4).all()
    return render_template("student/dashboard.html", upcoming=upcoming[:3], recommended=recommended, total=len(registrations), attended=attended, certificates=certificates)


@app.route("/student/events")
@role_required("student")
def student_events():
    regs = Registration.query.filter_by(student_id=current_user.id).order_by(Registration.registered_at.desc()).all()
    return render_template("student/my_events.html", regs=regs)
@app.route(
    "/organizer/events/<int:event_id>/competition",
    methods=["GET", "POST"]
)
@role_required("organizer", "admin")
def organizer_competition(event_id):

    event = db.get_or_404(Event, event_id)

    if (
        current_user.role == "organizer"
        and event.organizer_id != current_user.id
    ):
        abort(403)

    competition = Competition.query.filter_by(
        event_id=event.id
    ).first()

    if request.method == "POST":

        action = request.form.get("action", "").strip()


        # -----------------------------------------------------
        # CREATE COMPETITION
        # -----------------------------------------------------

        if action == "create_competition":

            if competition:
                flash(
                    "A competition already exists for this event.",
                    "info"
                )

            else:

                competition = Competition(
                    event_id=event.id,
                    team_allowed=True,
                    status="upcoming"
                )

                db.session.add(competition)

                log_action(
                    f"Created competition for {event.title}",
                    event
                )

                db.session.commit()

                flash(
                    "Competition created successfully.",
                    "success"
                )


        # -----------------------------------------------------
        # ADD ROUND
        # -----------------------------------------------------

        elif action == "add_round":

            if not competition:
                flash(
                    "Create the competition first.",
                    "warning"
                )

            else:

                name = request.form.get(
                    "round_name",
                    ""
                ).strip()

                if not name:
                    flash(
                        "Enter a round name.",
                        "warning"
                    )

                else:

                    existing_rounds = CompetitionRound.query.filter_by(
                        competition_id=competition.id
                    ).count()

                    round_number = existing_rounds + 1

                    competition_round = CompetitionRound(
                        competition_id=competition.id,
                        name=name,
                        round_number=round_number,
                        status="upcoming"
                    )

                    db.session.add(
                        competition_round
                    )

                    log_action(
                        f"Added competition round {name} "
                        f"for {event.title}",
                        event
                    )

                    db.session.commit()

                    flash(
                        f"Round {round_number} added.",
                        "success"
                    )


        # -----------------------------------------------------
        # CHANGE ROUND STATUS
        # -----------------------------------------------------

        elif action == "round_status":

            if not competition:
                flash(
                    "Competition not found.",
                    "warning"
                )

            else:

                round_id = request.form.get(
                    "round_id",
                    type=int
                )

                new_status = request.form.get(
                    "status",
                    ""
                ).strip().lower()

                allowed_statuses = {
                    "upcoming",
                    "active",
                    "completed"
                }

                if (
                    round_id
                    and new_status in allowed_statuses
                ):

                    competition_round = CompetitionRound.query.filter_by(
                        id=round_id,
                        competition_id=competition.id
                    ).first()

                    if competition_round:

                        competition_round.status = new_status

                        db.session.commit()

                        flash(
                            f"{competition_round.name} is now "
                            f"{new_status}.",
                            "success"
                        )

                    else:
                        flash(
                            "Round not found.",
                            "danger"
                        )

                else:
                    flash(
                        "Invalid round update.",
                        "danger"
                    )


        return redirect(
            url_for(
                "organizer_competition",
                event_id=event.id
            )
        )


    rounds = []

    if competition:
        rounds = CompetitionRound.query.filter_by(
            competition_id=competition.id
        ).order_by(
            CompetitionRound.round_number
        ).all()


    return render_template(
        "organizer/competition.html",
        event=event,
        competition=competition,
        rounds=rounds
    )

@app.route("/organizer/events/<int:event_id>/gallery", methods=["GET", "POST"])
@role_required("organizer", "admin")
def organizer_gallery(event_id):

    event = db.get_or_404(Event, event_id)

    if (
        current_user.role == "organizer"
        and event.organizer_id != current_user.id
    ):
        abort(403)

    if request.method == "POST":

        files = request.files.getlist("images")
        caption = request.form.get("caption", "").strip()

        uploaded = 0

        for file in files:

            if not file or not file.filename:
                continue

            filename = secure_filename(file.filename)

            if not filename:
                continue

            allowed_extensions = {
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".gif"
            }

            extension = Path(filename).suffix.lower()

            if extension not in allowed_extensions:
                continue

            stem = (
                f"gallery_{datetime.utcnow().timestamp()}_"
                f"{uploaded}_{filename}"
            )

            path = (
                Path(app.config["UPLOAD_FOLDER"])
                / stem
            )

            file.save(path)

            gallery_item = EventGallery(
                event_id=event.id,
                image_path=f"uploads/{stem}",
                caption=caption
            )

            db.session.add(gallery_item)

            uploaded += 1

        if uploaded:
            log_action(
                f"Uploaded {uploaded} gallery image(s) for {event.title}",
                event
            )

            db.session.commit()

            flash(
                f"{uploaded} image(s) added to the gallery.",
                "success"
            )

        else:
            flash(
                "No valid image files were uploaded.",
                "warning"
            )

        return redirect(
            url_for(
                "organizer_gallery",
                event_id=event.id
            )
        )

    gallery = EventGallery.query.filter_by(
        event_id=event.id
    ).order_by(
        EventGallery.created_at.desc()
    ).all()

    return render_template(
        "organizer/gallery.html",
        event=event,
        gallery=gallery
    )


@app.post("/organizer/gallery/<int:gallery_id>/delete")
@role_required("organizer", "admin")
def delete_gallery_image(gallery_id):

    gallery_item = db.get_or_404(
        EventGallery,
        gallery_id
    )

    event = gallery_item.event

    if (
        current_user.role == "organizer"
        and event.organizer_id != current_user.id
    ):
        abort(403)

    file_path = (
        Path(app.config["UPLOAD_FOLDER"])
        / Path(gallery_item.image_path).name
    )

    if file_path.exists():
        file_path.unlink()

    db.session.delete(gallery_item)

    log_action(
        f"Deleted gallery image from {event.title}",
        event
    )

    db.session.commit()

    flash(
        "Gallery image deleted.",
        "info"
    )

    return redirect(
        url_for(
            "organizer_gallery",
            event_id=event.id
        )
    )


@app.route("/student/calendar")
@role_required("student")
def student_calendar():
    return render_template("student/calendar.html")


@app.route("/student/certificates")
@role_required("student")
def student_certificates():
    certificates = Certificate.query.filter_by(student_id=current_user.id).order_by(Certificate.generated_at.desc()).all()
    return render_template("student/certificates.html", certificates=certificates)


@app.route("/student/profile", methods=["GET", "POST"])
@role_required("student")
def student_profile():
    if request.method == "POST":
        current_user.name = request.form["name"].strip()
        current_user.department = request.form.get("department", "CSE")
        current_user.roll_number = request.form.get("roll_number", "").strip() or None
        current_user.interests = request.form.get("interests", "Technical,Workshop")
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("student_profile"))
    return render_template("student/profile.html")


@app.post("/student/events/<int:event_id>/register")
@role_required("student")
def student_register_event(event_id):
    event = db.get_or_404(Event, event_id)
    existing = Registration.query.filter_by(event_id=event.id, student_id=current_user.id).first()
    if existing and existing.status in ["registered", "waitlisted"]:
        flash("You already have a registration for this event.", "info")
        return redirect(url_for("event_detail", event_id=event.id))
    if datetime.utcnow() > event.registration_deadline:
        flash("Registration deadline has passed.", "danger")
        return redirect(url_for("event_detail", event_id=event.id))
    active = event.active_registrations
    status = "registered" if active < event.max_participants else "waitlisted"
    if existing:
        existing.status = status
        existing.registered_at = datetime.utcnow()
        registration = existing
    else:
        registration = Registration(event_id=event.id, student_id=current_user.id, status=status)
        db.session.add(registration)
    db.session.flush()
    notify(current_user.id, "Registration confirmed" if status == "registered" else "Added to waitlist", f"{event.title} — your status is {status}.")
    log_action(f"Registered for {event.title}" + (" (waitlist)" if status == "waitlisted" else ""), event)
    db.session.commit()
    flash("Registration confirmed." if status == "registered" else "The event is full; you were added to the waitlist.", "success" if status == "registered" else "warning")
    return redirect(url_for("student_events"))


@app.post("/student/registrations/<int:registration_id>/cancel")
@role_required("student")
def cancel_registration(registration_id):
    reg = db.get_or_404(Registration, registration_id)
    if reg.student_id != current_user.id:
        abort(403)
    was_registered = reg.status == "registered"
    reg.status = "cancelled"
    if was_registered:
        waitlisted = Registration.query.filter_by(event_id=reg.event_id, status="waitlisted").order_by(Registration.registered_at).first()
        if waitlisted:
            waitlisted.status = "registered"
            notify(waitlisted.student_id, "Seat available", f"You have been promoted from the waitlist for {reg.event.title}.")
    log_action(f"Cancelled registration for {reg.event.title}", reg.event)
    db.session.commit()
    flash("Registration cancelled.", "info")
    return redirect(url_for("student_events"))


@app.route("/student/qr/<int:registration_id>")
@role_required("student")
def student_qr(registration_id):
    reg = db.get_or_404(Registration, registration_id)

    if reg.student_id != current_user.id:
        abort(403)

    if reg.status != "registered":
        flash("A QR pass is available only for confirmed registrations.", "warning")
        return redirect(url_for("event_detail", event_id=reg.event_id))

    return render_template(
        "student/qr_pass.html",
        registration=reg,
        event=reg.event,
    )


@app.route("/student/qr/<int:registration_id>/image")
@role_required("student")
def student_qr_image(registration_id):
    reg = db.get_or_404(Registration, registration_id)

    if reg.student_id != current_user.id:
        abort(403)

    if reg.status != "registered":
        abort(404)

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )

    qr.add_data(reg.registration_number)
    qr.make(fit=True)

    image = qr.make_image()

    buf = BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)

    return send_file(
        buf,
        mimetype="image/png",
        download_name=f"{reg.registration_number}.png",
    )


@app.post("/student/events/<int:event_id>/feedback")
@role_required("student")
def submit_feedback(event_id):
    event = db.get_or_404(Event, event_id)

    registration = Registration.query.filter_by(
        event_id=event.id,
        student_id=current_user.id
    ).first()

    if not registration or not registration.attendance:
        flash(
            "Feedback is available after attendance is recorded.",
            "warning"
        )
        return redirect(
            url_for("event_detail", event_id=event.id)
        )

    existing = Feedback.query.filter_by(
        event_id=event.id,
        student_id=current_user.id
    ).first()

    if existing:
        flash(
            "You already submitted feedback.",
            "info"
        )
        return redirect(
            url_for("event_detail", event_id=event.id)
        )

    def clean_rating(field_name, default=5):
        try:
            value = int(request.form.get(field_name, default))
        except (TypeError, ValueError):
            value = default

        return max(1, min(5, value))

    comment = request.form.get(
        "comment",
        ""
    ).strip()

    if len(comment) > 1000:
        flash(
            "Feedback comment must be 1000 characters or less.",
            "danger"
        )
        return redirect(
            url_for("event_detail", event_id=event.id)
        )

    feedback = Feedback(
        event_id=event.id,
        student_id=current_user.id,
        rating=clean_rating("rating"),
        speaker_rating=clean_rating("speaker_rating"),
        organization_rating=clean_rating("organization_rating"),
        venue_rating=clean_rating("venue_rating"),
        comment=comment,
    )

    db.session.add(feedback)
    db.session.commit()

    flash(
        "Thanks for your feedback!",
        "success"
    )

    return redirect(
        url_for("event_detail", event_id=event.id)
    )
    event = db.get_or_404(Event, event_id)
    reg = Registration.query.filter_by(event_id=event.id, student_id=current_user.id).first()
    if not reg or not reg.attendance:
        flash("Feedback is available after attendance is recorded.", "warning")
        return redirect(url_for("event_detail", event_id=event.id))
    existing = Feedback.query.filter_by(event_id=event.id, student_id=current_user.id).first()
    if existing:
        flash("You already submitted feedback.", "info")
        return redirect(url_for("event_detail", event_id=event.id))
    fb = Feedback(event_id=event.id, student_id=current_user.id,
                  rating=int(request.form.get("rating", 5)),
                  speaker_rating=int(request.form.get("speaker_rating", 5)),
                  organization_rating=int(request.form.get("organization_rating", 5)),
                  venue_rating=int(request.form.get("venue_rating", 5)),
                  comment=request.form.get("comment", "").strip())
    db.session.add(fb)
    db.session.commit()
    flash("Thanks for your feedback!", "success")
    return redirect(url_for("event_detail", event_id=event.id))


# -------------------- ORGANIZER --------------------
@app.route("/organizer/dashboard")
@role_required("organizer")
def organizer_dashboard():
    own_events = Event.query.filter_by(organizer_id=current_user.id).order_by(Event.start_datetime.desc()).all()
    regs = sum(e.active_registrations for e in own_events)
    attendance = sum(e.attendance_count for e in own_events)
    avg_attendance = round((attendance / regs) * 100, 1) if regs else 0
    return render_template("organizer/dashboard.html", events=own_events[:8], total_events=len(own_events), total_regs=regs, attendance=attendance, avg_attendance=avg_attendance)


@app.route("/organizer/events")
@role_required("organizer")
def organizer_events():
    events_list = Event.query.filter_by(organizer_id=current_user.id).order_by(Event.created_at.desc()).all()
    return render_template("organizer/events.html", events=events_list)


@app.route("/organizer/events/create", methods=["GET", "POST"])
@role_required("organizer")
def create_event():
    clubs = Club.query.order_by(Club.name).all()
    venues = Venue.query.order_by(Venue.name).all()
    if request.method == "POST":
        start = parse_dt(request.form["start_datetime"])
        end = parse_dt(request.form["end_datetime"])
        deadline = parse_dt(request.form["registration_deadline"])
        venue_id = int(request.form["venue_id"])
        overlap = event_overlap(venue_id, start, end)
        if overlap:
            flash(f"Venue conflict: {overlap.title} overlaps this time.", "danger")
            return render_template("organizer/event_form.html", clubs=clubs, venues=venues, event=None)
        event = Event(title=request.form["title"].strip(), description=request.form["description"].strip(),
                      category=request.form["category"], event_type=request.form.get("event_type", "Workshop"),
                      eligibility=request.form.get("eligibility", "All students"), start_datetime=start,
                      end_datetime=end, registration_deadline=deadline, max_participants=int(request.form["max_participants"]),
                      status="submitted", featured=False, organizer_id=current_user.id,
                      club_id=int(request.form["club_id"]) if request.form.get("club_id") else None, venue_id=venue_id)
        if "banner" in request.files and request.files["banner"].filename:
            file = request.files["banner"]
            filename = secure_filename(file.filename)
            stem = f"event_{datetime.utcnow().timestamp()}_{filename}"
            path = Path(app.config["UPLOAD_FOLDER"]) / stem
            file.save(path)
            event.banner = f"uploads/{stem}"
        db.session.add(event)
        db.session.flush()
        log_action(f"Created event {event.title}", event)
        admins = User.query.filter_by(
            role="admin").all()
        for admin in admins:
            notify(
                admin.id,
                "New event awaiting approval",
                f"{event.title} was submitted by {current_user.name} and is awaiting your approval."
            )
        db.session.commit()
        flash("Event submitted for admin approval.", "success")
        return redirect(url_for("organizer_events"))
    return render_template("organizer/event_form.html", clubs=clubs, venues=venues, event=None)


@app.route("/organizer/events/<int:event_id>")
@role_required("organizer")
def organizer_event(event_id):
    event = db.get_or_404(Event, event_id)
    if event.organizer_id != current_user.id:
        abort(403)
    return render_template("organizer/command_center.html", event=event)


@app.route("/organizer/events/<int:event_id>/registrations")
@role_required("organizer")
def organizer_registrations(event_id):
    event = db.get_or_404(Event, event_id)
    if event.organizer_id != current_user.id:
        abort(403)
    regs = Registration.query.filter_by(event_id=event.id).order_by(Registration.registered_at).all()
    return render_template("organizer/registrations.html", event=event, regs=regs)


@app.route("/organizer/events/<int:event_id>/attendance")
@role_required("organizer")
def organizer_attendance(event_id):
    event = db.get_or_404(Event, event_id)
    if event.organizer_id != current_user.id:
        abort(403)
    return render_template("organizer/attendance.html", event=event)


@app.route("/organizer/events/<int:event_id>/analytics")
@role_required("organizer")
def organizer_analytics(event_id):
    event = db.get_or_404(Event, event_id)
    if event.organizer_id != current_user.id:
        abort(403)
    feedback = Feedback.query.filter_by(event_id=event.id).all()
    dept_rows = db.session.query(User.department, func.count(Registration.id)).join(Registration, Registration.student_id == User.id).filter(Registration.event_id == event.id, Registration.status == "registered").group_by(User.department).all()
    dept_data = {dept: count for dept, count in dept_rows}
    return render_template("organizer/analytics.html", event=event, feedback=feedback, dept_data=dept_data)


@app.route("/organizer/events/<int:event_id>/volunteers", methods=["GET", "POST"])
@role_required("organizer")
def organizer_volunteers(event_id):
    event = db.get_or_404(Event, event_id)
    if event.organizer_id != current_user.id:
        abort(403)
    if request.method == "POST":
        student = db.get_or_404(User, int(request.form["student_id"]))
        db.session.add(Volunteer(event_id=event.id, student_id=student.id, assignment=request.form.get("assignment", "Registration Desk")))
        notify(student.id, "Volunteer assignment", f"You were assigned to {event.title} as {request.form.get('assignment', 'Registration Desk')}.")
        db.session.commit()
        flash("Volunteer assigned.", "success")
        return redirect(url_for("organizer_volunteers", event_id=event.id))
    volunteers = Volunteer.query.filter_by(event_id=event.id).all()
    students = User.query.filter_by(role="student").order_by(User.name).all()
    return render_template("organizer/volunteers.html", event=event, volunteers=volunteers, students=students)


@app.route("/organizer/events/<int:event_id>/budget", methods=["GET", "POST"])
@role_required("organizer")
def organizer_budget(event_id):
    event = db.get_or_404(Event, event_id)
    if event.organizer_id != current_user.id:
        abort(403)
    if request.method == "POST":
        item = BudgetItem(event_id=event.id, description=request.form["description"].strip(), category=request.form.get("category", "Other"), amount=float(request.form.get("amount", 0)))
        db.session.add(item)
        db.session.commit()
        flash("Budget item added.", "success")
        return redirect(url_for("organizer_budget", event_id=event.id))
    items = BudgetItem.query.filter_by(event_id=event.id).order_by(BudgetItem.spent_at.desc()).all()
    return render_template("organizer/budget.html", event=event, items=items, total=sum(i.amount for i in items))


@app.route("/organizer/events/<int:event_id>/risks", methods=["GET", "POST"])
@role_required("organizer")
def organizer_risks(event_id):
    event = db.get_or_404(Event, event_id)
    if event.organizer_id != current_user.id:
        abort(403)
    if request.method == "POST":
        db.session.add(Risk(event_id=event.id, title=request.form["title"].strip(), probability=request.form.get("probability", "Medium"), impact=request.form.get("impact", "Medium"), mitigation=request.form.get("mitigation", "").strip()))
        db.session.commit()
        flash("Risk added.", "success")
        return redirect(url_for("organizer_risks", event_id=event.id))
    return render_template("organizer/risks.html", event=event)
@app.route(
    "/organizer/events/<int:event_id>/checklist",
    methods=["GET", "POST"]
)
@role_required("organizer")
def organizer_checklist(event_id):

    event = db.get_or_404(
        Event,
        event_id
    )

    if event.organizer_id != current_user.id:
        abort(403)

    if request.method == "POST":

        action = request.form.get(
            "action",
            ""
        ).strip()

        # ADD
        if action == "add":

            title = request.form.get(
                "title",
                ""
            ).strip()

            if not title:
                flash(
                    "Checklist item title is required.",
                    "warning"
                )

            elif len(title) > 180:
                flash(
                    "Checklist item is too long.",
                    "warning"
                )

            else:
                item = ChecklistItem(
                    event_id=event.id,
                    title=title,
                    completed=False
                )

                db.session.add(item)

                log_action(
                    f"Added checklist item: {title}",
                    event
                )

                db.session.commit()

                flash(
                    "Checklist item added.",
                    "success"
                )

        # TOGGLE
        elif action == "toggle":

            item_id = request.form.get(
                "item_id",
                type=int
            )

            item = ChecklistItem.query.filter_by(
                id=item_id,
                event_id=event.id
            ).first()

            if not item:

                flash(
                    "Checklist item not found.",
                    "danger"
                )

            else:

                item.completed = not item.completed

                log_action(
                    (
                        "Completed checklist item: "
                        if item.completed
                        else "Reopened checklist item: "
                    )
                    + item.title,
                    event
                )

                db.session.commit()

                flash(
                    (
                        "Checklist item completed."
                        if item.completed
                        else "Checklist item reopened."
                    ),
                    "success"
                )

        # DELETE
        elif action == "delete":

            item_id = request.form.get(
                "item_id",
                type=int
            )

            item = ChecklistItem.query.filter_by(
                id=item_id,
                event_id=event.id
            ).first()

            if not item:

                flash(
                    "Checklist item not found.",
                    "danger"
                )

            else:

                title = item.title

                db.session.delete(item)

                log_action(
                    f"Deleted checklist item: {title}",
                    event
                )

                db.session.commit()

                flash(
                    "Checklist item deleted.",
                    "info"
                )

        return redirect(
            url_for(
                "organizer_checklist",
                event_id=event.id
            )
        )

    items = (
        ChecklistItem.query
        .filter_by(event_id=event.id)
        .order_by(
            ChecklistItem.completed.asc(),
            ChecklistItem.id.asc()
        )
        .all()
    )

    total_items = len(items)

    completed_items = sum(
        1
        for item in items
        if item.completed
    )

    progress = round(
        (completed_items / total_items) * 100
    ) if total_items else 0

    return render_template(
        "organizer/checklist.html",
        event=event,
        items=items,
        total_items=total_items,
        completed_items=completed_items,
        progress=progress
    )
@app.route(
    "/organizer/events/<int:event_id>/resources",
    methods=["GET", "POST"]
)
@role_required("organizer")
def organizer_resources(event_id):

    event = db.get_or_404(
        Event,
        event_id
    )

    if event.organizer_id != current_user.id:
        abort(403)

    if request.method == "POST":

        resource_id = request.form.get(
            "resource_id",
            type=int
        )

        quantity = request.form.get(
            "quantity",
            type=int
        )

        if not resource_id:
            flash(
                "Select a resource.",
                "warning"
            )
            return redirect(
                url_for(
                    "organizer_resources",
                    event_id=event.id
                )
            )

        if not quantity or quantity < 1:
            flash(
                "Quantity must be at least 1.",
                "warning"
            )
            return redirect(
                url_for(
                    "organizer_resources",
                    event_id=event.id
                )
            )

        resource = db.session.get(
            Resource,
            resource_id
        )

        if not resource:
            flash(
                "Resource not found.",
                "danger"
            )
            return redirect(
                url_for(
                    "organizer_resources",
                    event_id=event.id
                )
            )

        # Prevent requesting more than the entire inventory.
        if quantity > resource.quantity:
            flash(
                f"Only {resource.quantity} unit(s) of "
                f"{resource.name} exist.",
                "warning"
            )
            return redirect(
                url_for(
                    "organizer_resources",
                    event_id=event.id
                )
            )

        # Prevent duplicate active requests for the same event/resource.
        existing_request = (
            ResourceRequest.query
            .filter(
                ResourceRequest.event_id == event.id,
                ResourceRequest.resource_id == resource.id,
                ResourceRequest.status.in_(
                    ["pending", "approved"]
                )
            )
            .first()
        )

        if existing_request:
            flash(
                f"You already have an active request for "
                f"{resource.name}.",
                "info"
            )
            return redirect(
                url_for(
                    "organizer_resources",
                    event_id=event.id
                )
            )

        available = available_resource_quantity(
            resource,
            event
        )

        if quantity > available:
            flash(
                f"Only {available} unit(s) of "
                f"{resource.name} are currently available "
                f"for this event time.",
                "warning"
            )
            return redirect(
                url_for(
                    "organizer_resources",
                    event_id=event.id
                )
            )

        resource_request = ResourceRequest(
            event_id=event.id,
            resource_id=resource.id,
            quantity=quantity,
            status="pending"
        )

        db.session.add(
            resource_request
        )

        log_action(f"Requested {quantity} x {resource.name} "f"for {event.title}", event)
        admins = User.query.filter_by(
            role="admin"
        ).all()

        for admin in admins:
            notify(
                admin.id,
                "New resource request",
                (
                    f"{current_user.name} requested "
                    f"{quantity} x {resource.name} "
                    f"for {event.title}. "
                    f"Approval is required."
                )
            )


        db.session.commit()

        flash(
            f"Resource request submitted for "
            f"{resource.name}.",
            "success"
        )

        return redirect(
            url_for(
                "organizer_resources",
                event_id=event.id
            )
        )

    resources = (
        Resource.query
        .order_by(Resource.name)
        .all()
    )

    requests = (
        ResourceRequest.query
        .filter_by(event_id=event.id)
        .order_by(ResourceRequest.id.desc())
        .all()
    )

    availability = {
        resource.id: available_resource_quantity(
            resource,
            event
        )
        for resource in resources
    }

    return render_template(
        "organizer/resources.html",
        event=event,
        resources=resources,
        requests=requests,
        availability=availability
    )


@app.post("/organizer/events/<int:event_id>/announcement")
@role_required("organizer")
def organizer_announcement(event_id):
    event = db.get_or_404(Event, event_id)
    if event.organizer_id != current_user.id:
        abort(403)
    ann = Announcement(event_id=event.id, author_id=current_user.id, title=request.form["title"].strip(), message=request.form["message"].strip())
    db.session.add(ann)
    for reg in event.registrations:
        if reg.status == "registered":
            notify(reg.student_id, ann.title, ann.message)
    db.session.commit()
    flash("Announcement sent to registered students.", "success")
    return redirect(url_for("organizer_event", event_id=event.id))


# -------------------- ADMIN --------------------

@app.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():

    counts = {
        "events": Event.query.count(),
        "pending": Event.query.filter_by(
            status="submitted"
        ).count(),
        "users": User.query.count(),
        "clubs": Club.query.count(),
        "venues": Venue.query.count(),
    }

    return render_template(
        "admin/dashboard.html",
        counts=counts
    )


@app.route("/admin/events/pending")
@role_required("admin")
def admin_pending():

    events_list = (
        Event.query
        .filter_by(status="submitted")
        .order_by(Event.created_at.desc())
        .all()
    )

    return render_template(
        "admin/pending.html",
        events=events_list
    )


@app.post("/admin/events/<int:event_id>/approve")
@role_required("admin")
def admin_approve(event_id):

    event = db.get_or_404(
        Event,
        event_id
    )

    event.status = "published"

    notify(
        event.organizer_id,
        "Event approved",
        f"{event.title} has been approved and published."
    )

    log_action(
        f"Approved event {event.title}",
        event
    )

    db.session.commit()

    flash(
        "Event published.",
        "success"
    )

    return redirect(
        url_for("admin_pending")
    )


@app.post("/admin/events/<int:event_id>/reject")
@role_required("admin")
def admin_reject(event_id):

    event = db.get_or_404(
        Event,
        event_id
    )

    event.status = "rejected"

    notify(
        event.organizer_id,
        "Event rejected",
        f"{event.title} was rejected by admin. Please review and resubmit."
    )

    db.session.commit()

    flash(
        "Event rejected.",
        "info"
    )

    return redirect(
        url_for("admin_pending")
    )


@app.route("/admin/events")
@role_required("admin")
def admin_events():

    events_list = (
        Event.query
        .order_by(Event.start_datetime.desc())
        .all()
    )

    return render_template(
        "admin/events.html",
        events=events_list
    )


@app.route("/admin/users")
@role_required("admin")
def admin_users():

    users = (
        User.query
        .order_by(User.created_at.desc())
        .all()
    )

    return render_template(
        "admin/users.html",
        users=users
    )


@app.route("/admin/clubs")
@role_required("admin")
def admin_clubs():

    clubs = (
        Club.query
        .order_by(Club.name)
        .all()
    )

    return render_template(
        "admin/clubs.html",
        clubs=clubs
    )


@app.route("/admin/venues")
@role_required("admin")
def admin_venues():

    venues = (
        Venue.query
        .order_by(Venue.name)
        .all()
    )

    return render_template(
        "admin/venues.html",
        venues=venues
    )


@app.post("/admin/venues")
@role_required("admin")
def add_venue():

    venue = Venue(
        name=request.form["name"].strip(),
        capacity=int(
            request.form["capacity"]
        ),
        location=request.form.get(
            "location",
            "Campus"
        ),
        equipment=request.form.get(
            "equipment",
            "Projector, Microphone"
        )
    )

    db.session.add(venue)
    db.session.commit()

    flash(
        "Venue added.",
        "success"
    )

    return redirect(
        url_for("admin_venues")
    )


@app.post("/admin/clubs")
@role_required("admin")
def add_club():

    club = Club(
        name=request.form["name"].strip(),
        description=request.form.get(
            "description",
            ""
        )
    )

    db.session.add(club)
    db.session.commit()

    flash(
        "Club added.",
        "success"
    )

    return redirect(
        url_for("admin_clubs")
    )
# -------------------- ADMIN REPORTS --------------------

@app.route("/admin/reports")
@role_required("admin")
def admin_reports():

    events_list = (
        Event.query
        .order_by(Event.start_datetime.desc())
        .all()
    )

    selected_event = None

    event_id = request.args.get(
        "event_id",
        type=int
    )

    if event_id:
        selected_event = db.session.get(
            Event,
            event_id
        )

        if not selected_event:
            flash(
                "Event not found.",
                "danger"
            )
            return redirect(
                url_for("admin_reports")
            )

    report = None

    if selected_event:

        registrations = (
            Registration.query
            .filter_by(
                event_id=selected_event.id
            )
            .order_by(
                Registration.registered_at.asc()
            )
            .all()
        )

        registered_count = sum(
            1
            for reg in registrations
            if reg.status == "registered"
        )

        cancelled_count = sum(
            1
            for reg in registrations
            if reg.status == "cancelled"
        )

        waitlisted_count = sum(
            1
            for reg in registrations
            if reg.status == "waitlisted"
        )

        registration_ids = [
            reg.id
            for reg in registrations
        ]

        attendance_count = 0

        if registration_ids:
            attendance_count = (
                Attendance.query
                .filter(
                    Attendance.registration_id.in_(
                        registration_ids
                    ),
                    Attendance.status == "present"
                )
                .count()
            )

        certificate_count = (
            Certificate.query
            .filter_by(
                event_id=selected_event.id
            )
            .count()
        )

        feedback_items = (
            Feedback.query
            .filter_by(
                event_id=selected_event.id
            )
            .order_by(
                Feedback.created_at.desc()
            )
            .all()
        )

        average_rating = (
            round(
                sum(
                    feedback.rating
                    for feedback in feedback_items
                )
                / len(feedback_items),
                1
            )
            if feedback_items
            else 0
        )

        department_counts = {}

        for reg in registrations:

            if reg.status != "registered":
                continue

            student = reg.student

            department = (
                student.department
                if student and student.department
                else "Not specified"
            )

            department_counts[department] = (
                department_counts.get(
                    department,
                    0
                ) + 1
            )

        report = {
            "registrations": registrations,
            "registered_count": registered_count,
            "cancelled_count": cancelled_count,
            "waitlisted_count": waitlisted_count,
            "attendance_count": attendance_count,
            "certificate_count": certificate_count,
            "feedback_items": feedback_items,
            "feedback_count": len(feedback_items),
            "average_rating": average_rating,
            "department_counts": dict(
                sorted(
                    department_counts.items(),
                    key=lambda item: item[1],
                    reverse=True
                )
            ),
        }

    return render_template(
        "admin/reports.html",
        events=events_list,
        selected_event=selected_event,
        report=report
    )
@app.get("/admin/reports/<int:event_id>/pdf")
@role_required("admin")
def admin_report_pdf(event_id):

    event = db.get_or_404(
        Event,
        event_id
    )

    registrations = (
        Registration.query
        .filter_by(
            event_id=event.id
        )
        .order_by(
            Registration.registered_at.asc()
        )
        .all()
    )

    registered_count = sum(
        1
        for reg in registrations
        if reg.status == "registered"
    )

    cancelled_count = sum(
        1
        for reg in registrations
        if reg.status == "cancelled"
    )

    waitlisted_count = sum(
        1
        for reg in registrations
        if reg.status == "waitlisted"
    )

    registration_ids = [
        reg.id
        for reg in registrations
    ]

    attendance_count = 0

    if registration_ids:
        attendance_count = (
            Attendance.query
            .filter(
                Attendance.registration_id.in_(
                    registration_ids
                ),
                Attendance.status == "present"
            )
            .count()
        )

    certificate_count = (
        Certificate.query
        .filter_by(
            event_id=event.id
        )
        .count()
    )

    feedback_items = (
        Feedback.query
        .filter_by(
            event_id=event.id
        )
        .order_by(
            Feedback.created_at.desc()
        )
        .all()
    )

    average_rating = (
        round(
            sum(
                feedback.rating
                for feedback in feedback_items
            )
            / len(feedback_items),
            1
        )
        if feedback_items
        else 0
    )

    department_counts = {}

    for reg in registrations:

        if reg.status != "registered":
            continue

        student = reg.student

        department = (
            student.department
            if student and student.department
            else "Not specified"
        )

        department_counts[department] = (
            department_counts.get(
                department,
                0
            ) + 1
        )

    buf = BytesIO()

    page_width, page_height = A4

    pdf = canvas.Canvas(
        buf,
        pagesize=A4
    )

    left = 45
    right = page_width - 45
    y = page_height - 50

    def ensure_space(required=35):
        nonlocal y

        if y < required:
            pdf.showPage()
            y = page_height - 50

    def draw_text(
        text,
        size=10,
        bold=False,
        gap=16
    ):
        nonlocal y

        ensure_space(gap + 10)

        pdf.setFont(
            "Helvetica-Bold" if bold else "Helvetica",
            size
        )

        pdf.drawString(
            left,
            y,
            str(text)
        )

        y -= gap

    pdf.setTitle(
        f"EventX Report - {event.title}"
    )

    pdf.setFont(
        "Helvetica-Bold",
        22
    )

    pdf.drawString(
        left,
        y,
        "EVENTX EVENT REPORT"
    )

    y -= 30

    pdf.setFont(
        "Helvetica-Bold",
        15
    )

    pdf.drawString(
        left,
        y,
        event.title
    )

    y -= 22

    pdf.setFont(
        "Helvetica",
        10
    )

    pdf.drawString(
        left,
        y,
        f"Status: {event.status}"
    )

    y -= 15

    pdf.drawString(
        left,
        y,
        f"Venue: {event.venue.name if event.venue else 'Not specified'}"
    )

    y -= 15

    pdf.drawString(
        left,
        y,
        f"Event date: {event.start_datetime.strftime('%d %b %Y')}"
        if event.start_datetime
        else "Event date: Not specified"
    )

    y -= 30

    pdf.setLineWidth(1)

    pdf.line(
        left,
        y,
        right,
        y
    )

    y -= 25

    draw_text(
        "EVENT SUMMARY",
        13,
        True,
        20
    )

    draw_text(
        f"Registered participants: {registered_count}"
    )

    draw_text(
        f"Cancelled registrations: {cancelled_count}"
    )

    draw_text(
        f"Waitlisted participants: {waitlisted_count}"
    )

    draw_text(
        f"Attendance records: {attendance_count}"
    )

    draw_text(
        f"Attendance rate: "
        f"{(
            attendance_count / registered_count * 100
        ):.1f}%"
        if registered_count
        else "Attendance rate: 0.0%"
    )

    draw_text(
        f"Certificates generated: {certificate_count}"
    )

    draw_text(
        f"Feedback responses: {len(feedback_items)}"
    )

    draw_text(
        f"Average feedback rating: {average_rating}/5"
    )

    y -= 8

    draw_text(
        "PARTICIPATION BY DEPARTMENT",
        13,
        True,
        20
    )

    if department_counts:

        for department, count in department_counts.items():

            draw_text(
                f"{department}: {count}"
            )

    else:

        draw_text(
            "No registered participant data available."
        )

    y -= 8

    draw_text(
        "PARTICIPANTS",
        13,
        True,
        20
    )

    if registrations:

        for index, reg in enumerate(
            registrations,
            start=1
        ):

            student = reg.student

            student_name = (
                student.name
                if student
                else "Unknown student"
            )

            roll_number = (
                student.roll_number
                if student and student.roll_number
                else "-"
            )

            status = reg.status or "-"

            line = (
                f"{index}. {student_name} | "
                f"Roll: {roll_number} | "
                f"Status: {status}"
            )

            draw_text(
                line,
                9,
                False,
                14
            )

    else:

        draw_text(
            "No registrations found."
        )

    y -= 8

    draw_text(
        "FEEDBACK",
        13,
        True,
        20
    )

    if feedback_items:

        for feedback in feedback_items:

            student = feedback.student

            student_name = (
                student.name
                if student
                else "Student"
            )

            comment = (
                feedback.comment or ""
            ).replace(
                "\n",
                " "
            ).strip()

            feedback_text = (
                f"{student_name} — "
                f"{feedback.rating}/5"
            )

            if comment:
                feedback_text += (
                    f" — {comment}"
                )

            draw_text(
                feedback_text,
                9,
                False,
                15
            )

    else:

        draw_text(
            "No feedback responses found."
        )

    pdf.showPage()
    pdf.save()

    buf.seek(0)

    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=(
            f"EventX-Report-"
            f"{event.id}.pdf"
        )
    )


# =====================================================
# RESOURCE INVENTORY
# =====================================================

@app.route(
    "/admin/resources",
    methods=["GET", "POST"]
)
@role_required("admin")
def admin_resources():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        quantity = request.form.get(
            "quantity",
            type=int
        )

        if not name:

            flash(
                "Resource name is required.",
                "warning"
            )

            return redirect(
                url_for("admin_resources")
            )

        if not quantity or quantity < 1:

            flash(
                "Quantity must be at least 1.",
                "warning"
            )

            return redirect(
                url_for("admin_resources")
            )

        # Check whether this resource already exists.
        existing = Resource.query.filter(
            db.func.lower(
                Resource.name
            ) == name.lower()
        ).first()

        # If it exists, increase its inventory quantity.
        if existing:

            existing.quantity += quantity

            # Update description only when a new
            # description was provided.
            if description:
                existing.description = description

            db.session.commit()

            flash(
                f"{existing.name} inventory increased by "
                f"{quantity} unit(s). Total quantity: "
                f"{existing.quantity}.",
                "success"
            )

            return redirect(
                url_for("admin_resources")
            )

        # Otherwise create a new resource.
        resource = Resource(
            name=name,
            quantity=quantity,
            description=description
        )

        db.session.add(resource)
        db.session.commit()

        flash(
            f"{name} added to the resource inventory.",
            "success"
        )

        return redirect(
            url_for("admin_resources")
        )

    resources = (
        Resource.query
        .order_by(Resource.name)
        .all()
    )

    pending_count = (
        ResourceRequest.query
        .filter_by(status="pending")
        .count()
    )

    return render_template(
        "admin/resource.html",
        resources=resources,
        pending_count=pending_count
    )

@app.post(
    "/admin/resources/<int:resource_id>/delete"
)
@role_required("admin")
def delete_resource(resource_id):

    resource = db.get_or_404(
        Resource,
        resource_id
    )

    active_requests = (
        ResourceRequest.query
        .filter(
            ResourceRequest.resource_id == resource.id,
            ResourceRequest.status.in_(
                ["pending", "approved"]
            )
        )
        .count()
    )

    if active_requests:

        flash(
            "This resource cannot be deleted while it has pending or approved event requests.",
            "warning"
        )

        return redirect(
            url_for("admin_resources")
        )

    resource_name = resource.name

    db.session.delete(resource)
    db.session.commit()

    flash(
        f"{resource_name} was removed from the inventory.",
        "info"
    )

    return redirect(
        url_for("admin_resources")
    )


# =====================================================
# RESOURCE REQUESTS
# =====================================================

@app.route("/admin/resource-requests")
@role_required("admin")
def admin_resource_requests():

    requests = (
        ResourceRequest.query
        .order_by(ResourceRequest.id.desc())
        .all()
    )

    return render_template(
        "admin/resource_requests.html",
        requests=requests
    )


@app.post(
    "/admin/resource-requests/<int:request_id>/status"
)
@role_required("admin")
def update_resource_request(request_id):

    resource_request = db.get_or_404(
        ResourceRequest,
        request_id
    )

    new_status = request.form.get(
        "status",
        ""
    ).strip().lower()

    if new_status not in {
        "approved",
        "rejected"
    }:

        flash(
            "Invalid resource request status.",
            "danger"
        )

        return redirect(
            url_for("admin_resource_requests")
        )

    event = resource_request.event
    resource = resource_request.resource

    if not event or not resource:

        flash(
            "Resource request data is incomplete.",
            "danger"
        )

        return redirect(
            url_for("admin_resource_requests")
        )

    # -------------------------------------------------
    # APPROVE
    # -------------------------------------------------

    if new_status == "approved":

        used_quantity = approved_resource_quantity(
            resource.id,
            event,
            exclude_request_id=resource_request.id
        )

        available = max(
            0,
            resource.quantity - used_quantity
        )

        if resource_request.quantity > available:

            flash(
                f"Cannot approve this request. Only "
                f"{available} unit(s) of {resource.name} "
                f"are available for this event time.",
                "danger"
            )

            return redirect(
                url_for("admin_resource_requests")
            )

        resource_request.status = "approved"

        notify(
            event.organizer_id,
            "Resource request approved",
            f"{resource_request.quantity} x "
            f"{resource.name} was approved for "
            f"{event.title}."
        )

        log_action(
            f"Approved resource request: "
            f"{resource_request.quantity} x "
            f"{resource.name} for {event.title}",
            event
        )

        flash(
            "Resource request approved.",
            "success"
        )

    # -------------------------------------------------
    # REJECT
    # -------------------------------------------------

    else:

        resource_request.status = "rejected"

        notify(
            event.organizer_id,
            "Resource request rejected",
            f"{resource_request.quantity} x "
            f"{resource.name} was rejected for "
            f"{event.title}."
        )

        log_action(
            f"Rejected resource request: "
            f"{resource_request.quantity} x "
            f"{resource.name} for {event.title}",
            event
        )

        flash(
            "Resource request rejected.",
            "info"
        )

    db.session.commit()

    return redirect(
        url_for("admin_resource_requests")
    )
# -------------------- ADMIN SPONSORSHIP --------------------

@app.route("/admin/sponsors", methods=["GET", "POST"])
@role_required("admin")
def admin_sponsors():

    if request.method == "POST":

        event_id = request.form.get(
            "event_id",
            type=int
        )

        name = request.form.get(
            "name",
            ""
        ).strip()

        contribution_raw = request.form.get(
            "contribution",
            "0"
        ).strip()

        contact = request.form.get(
            "contact",
            ""
        ).strip()

        promised_benefits = request.form.get(
            "promised_benefits",
            ""
        ).strip()

        status = request.form.get(
            "status",
            "Prospective"
        ).strip()

        # ---------------------------------------------
        # VALIDATION
        # ---------------------------------------------

        if not event_id:

            flash(
                "Please select an event.",
                "warning"
            )

            return redirect(
                url_for("admin_sponsors")
            )

        event = db.session.get(
            Event,
            event_id
        )

        if not event:

            flash(
                "Event not found.",
                "danger"
            )

            return redirect(
                url_for("admin_sponsors")
            )

        if not name:

            flash(
                "Sponsor name is required.",
                "warning"
            )

            return redirect(
                url_for("admin_sponsors")
            )

        if len(name) > 180:

            flash(
                "Sponsor name is too long.",
                "warning"
            )

            return redirect(
                url_for("admin_sponsors")
            )

        try:

            contribution = float(
                contribution_raw
            )

        except ValueError:

            flash(
                "Contribution must be a valid number.",
                "warning"
            )

            return redirect(
                url_for("admin_sponsors")
            )

        if contribution < 0:

            flash(
                "Contribution cannot be negative.",
                "warning"
            )

            return redirect(
                url_for("admin_sponsors")
            )

        allowed_statuses = [
            "Prospective",
            "Contacted",
            "Confirmed",
            "Declined"
        ]

        if status not in allowed_statuses:

            status = "Prospective"

        # ---------------------------------------------
        # CREATE SPONSOR
        # ---------------------------------------------

        sponsor = Sponsor(
            event_id=event.id,
            name=name,
            contribution=contribution,
            contact=contact,
            promised_benefits=promised_benefits,
            status=status
        )

        db.session.add(
            sponsor
        )

        log_action(
            f"Added sponsor {name} for {event.title}",
            event
        )

        db.session.commit()

        flash(
            f"Sponsor '{name}' added successfully.",
            "success"
        )

        return redirect(
            url_for("admin_sponsors")
        )

    # ---------------------------------------------
    # GET
    # ---------------------------------------------

    events_list = (
        Event.query
        .order_by(Event.start_datetime.desc())
        .all()
    )

    sponsors = (
        Sponsor.query
        .order_by(Sponsor.created_at.desc())
        .all()
    )

    return render_template(
        "admin/sponsors.html",
        events=events_list,
        sponsors=sponsors
    )
@app.post("/admin/sponsors/<int:sponsor_id>/delete")
@role_required("admin")
def delete_sponsor(sponsor_id):

    sponsor = db.get_or_404(
        Sponsor,
        sponsor_id
    )

    event = sponsor.event
    sponsor_name = sponsor.name

    db.session.delete(
        sponsor
    )

    if event:

        log_action(
            f"Deleted sponsor {sponsor_name} from {event.title}",
            event
        )

    db.session.commit()

    flash(
        "Sponsor deleted.",
        "info"
    )

    return redirect(
        url_for("admin_sponsors")
    )
# -------------------- API --------------------
@app.get("/api/events")
def api_events():
    items = Event.query.filter(Event.status.in_(["published", "approved", "live"])).order_by(Event.start_datetime).all()
    return jsonify([event_to_dict(e) for e in items])


def event_to_dict(e):
    return {
        "id": e.id, "title": e.title, "description": e.description, "category": e.category,
        "start": e.start_datetime.isoformat(), "end": e.end_datetime.isoformat(),
        "venue": e.venue.name, "location": e.venue.location,
        "registrations": e.active_registrations, "capacity": e.max_participants,
        "status": e.status,
        "url": url_for("event_detail", event_id=e.id, _external=True),
        "banner": url_for("static", filename=e.banner) if e.banner else "",
    }


@app.post("/api/attendance/check-in")
@role_required("organizer", "admin")
def api_checkin():

    data = request.get_json(silent=True) or {}

    registration_number = (
        data.get("registration_number", "")
        .strip()
    )

    session_label = (
        data.get("session_label", "Main Session")
        .strip()
    )

    if not session_label:
        session_label = "Main Session"

    session_label = session_label[:100]


    reg = Registration.query.filter_by(
        registration_number=registration_number
    ).first()


    if not reg:
        return jsonify({
            "ok": False,
            "message": "Registration not found."
        }), 404


    if reg.status != "registered":
        return jsonify({
            "ok": False,
            "message": "Registration is not active."
        }), 400


    event = reg.event


    if (
        current_user.role == "organizer"
        and event.organizer_id != current_user.id
    ):
        return jsonify({
            "ok": False,
            "message": "You do not manage this event."
        }), 403


    existing_attendance = Attendance.query.filter_by(
        registration_id=reg.id,
        session_label=session_label
    ).first()


    if existing_attendance:
        return jsonify({
            "ok": True,
            "already": True,
            "message": (
                f"Already checked in for {session_label}: "
                f"{reg.student.name}"
            ),
            "student": reg.student.name,
            "session_label": session_label
        })


    attendance = Attendance(
        registration_id=reg.id,
        session_label=session_label,
        status="present"
    )

    db.session.add(attendance)


    log_action(
        f"Checked in {reg.student.name} for "
        f"{event.title} ({session_label})",
        event
    )


    db.session.commit()


    return jsonify({
        "ok": True,
        "already": False,
        "message": (
            f"Attendance marked for {reg.student.name}"
        ),
        "student": reg.student.name,
        "roll_number": reg.student.roll_number,
        "session_label": session_label,
        "time": datetime.utcnow().strftime("%I:%M %p")
    })
@app.get("/api/calendar")
@login_required
def api_calendar():

    if current_user.role == "student":

        event_ids = [
            r.event_id
            for r in Registration.query.filter_by(
                student_id=current_user.id,
                status="registered"
            ).all()
        ]

        items = (
            Event.query.filter(Event.id.in_(event_ids)).all()
            if event_ids
            else []
        )

    elif current_user.role == "organizer":

        items = Event.query.filter_by(
            organizer_id=current_user.id
        ).all()

    else:

        items = Event.query.all()


    calendar_events = []

    for e in items:

        calendar_end = e.end_datetime

        # FullCalendar treats an event ending at exactly midnight
        # as continuing into the following calendar date.
        # For calendar display, keep midnight-ending events
        # visually on their starting day.
        if (
            e.end_datetime.time().hour == 0
            and e.end_datetime.time().minute == 0
            and e.end_datetime.time().second == 0
            and e.end_datetime.date() > e.start_datetime.date()
        ):
            calendar_end = e.end_datetime - timedelta(seconds=1)


        calendar_events.append({
            "id": e.id,
            "title": e.title,
            "start": e.start_datetime.isoformat(),
            "end": calendar_end.isoformat(),
            "url": url_for(
                "event_detail",
                event_id=e.id
            )
        })


    return jsonify(calendar_events)

@app.get("/api/notifications")
@login_required
def api_notifications():
    items = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(25).all()
    return jsonify([{"id": n.id, "title": n.title, "message": n.message, "is_read": n.is_read, "created_at": n.created_at.isoformat()} for n in items])


@app.post("/api/notifications/read")
@login_required
def api_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"ok": True})


@app.post("/api/events/<int:event_id>/certificates")
@role_required("organizer", "admin")
def api_generate_certificates(event_id):
    event = db.get_or_404(Event, event_id)
    if current_user.role == "organizer" and event.organizer_id != current_user.id:
        abort(403)
    count = 0
    for reg in event.registrations:
        if reg.status == "registered" and reg.attendance and not reg.certificate:
            cert = Certificate(event_id=event.id, student_id=reg.student_id, registration_id=reg.id)
            db.session.add(cert)
            db.session.flush()
            count += 1
            notify(reg.student_id, "Certificate ready", f"Your certificate for {event.title} is ready.")
    db.session.commit()
    return jsonify({"ok": True, "generated": count})


@app.route("/certificate/<int:certificate_id>/download")
@login_required
def certificate_download(certificate_id):
    cert = db.get_or_404(Certificate, certificate_id)
    if current_user.id != cert.student_id and current_user.role not in ["organizer", "admin"]:
        abort(403)
    filename = f"{cert.certificate_number}.pdf"
    if cert.file_path and os.path.exists(cert.file_path):
        return send_from_directory(os.path.dirname(cert.file_path), os.path.basename(cert.file_path), as_attachment=True, download_name=filename)
    buf = BytesIO()
    page = landscape(A4)
    c = canvas.Canvas(buf, pagesize=page)
    width, height = page
    c.setLineWidth(2)
    c.roundRect(30, 30, width - 60, height - 60, 20)
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(width / 2, height - 110, "CERTIFICATE OF PARTICIPATION")
    c.setFont("Helvetica", 14)
    c.drawCentredString(width / 2, height - 155, "This certificate is proudly presented to")
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(width / 2, height - 200, cert.student.name)
    c.setFont("Helvetica", 15)
    c.drawCentredString(width / 2, height - 245, f"for participating in {cert.event.title}")
    c.drawCentredString(width / 2, height - 275, f"{cert.event.start_datetime:%d %B %Y} • {cert.event.venue.name}")
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(width / 2, 90, cert.certificate_number)
    c.showPage()
    c.save()
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=filename)


@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Database tables created.")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
