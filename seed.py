from datetime import datetime, timezone, timedelta

from app import app
from models import db, User, Club, Venue, Event, Registration, Attendance, BudgetItem, Risk, Resource, Feedback


def seed():
    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(name="System Admin", email="admin@eventx.local", role="admin", department="Administration")
        admin.set_password("Admin@123")
        organizer = User(name="Rahul Sharma", email="organizer@eventx.local", role="organizer", department="CSE", interests="Technical,Competition")
        organizer.set_password("Organizer@123")
        students = []
        for name, email, roll, dept in [
            ("Akshat Garg", "akshat@eventx.local", "22CS128", "CSE"),
            ("Aman Verma", "aman@eventx.local", "22IT042", "IT"),
            ("Riya Patel", "riya@eventx.local", "22EC087", "ECE"),
            ("Neha Singh", "neha@eventx.local", "22ME031", "ME"),
        ]:
            u = User(name=name, email=email, role="student", department=dept, roll_number=roll, interests="Technical,Workshop")
            u.set_password("Student@123")
            students.append(u)
            db.session.add(u)
        db.session.add_all([admin, organizer])

        coding = Club(name="Coding Club", description="Software, AI and competitive programming community.")
        cultural = Club(name="Cultural Club", description="Music, dance and performing arts community.")
        venue1 = Venue(name="Main Auditorium", capacity=500, location="Block A", equipment="Projector, Stage, Microphone")
        venue2 = Venue(name="Computer Lab 3", capacity=120, location="Block C", equipment="120 PCs, Projector")
        venue3 = Venue(name="Seminar Hall", capacity=250, location="Block B", equipment="Projector, Microphone")
        venue4 = Venue(name="College Sports Ground", capacity=500, location="Sports Complex", equipment="Scoreboard, Sound System, Seating")
        db.session.add_all([coding, cultural, venue1, venue2, venue3, venue4])
        resources = [Resource(name="Projector", quantity=5, description="HD projector"), Resource(name="Microphone", quantity=10, description="Wireless mic"), Resource(name="Laptop", quantity=30, description="Event laptop")]
        db.session.add_all(resources)
        db.session.flush()

        base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        events = [
            Event(title="Python & AI Workshop", description="A hands-on workshop covering Python, APIs and practical AI workflows.", category="Technical", banner="images/EventX_posters/python_ai_workshop.png", event_type="Workshop", eligibility="All students", start_datetime=base + timedelta(days=2, hours=2), end_datetime=base + timedelta(days=2, hours=6), registration_deadline=base + timedelta(days=1, hours=6), max_participants=120, status="published", featured=True, organizer_id=organizer.id, club_id=coding.id, venue_id=venue2.id),
            Event(title="Campus Hackathon 2026", description="Build a useful campus solution in one day. Teams compete across multiple judging rounds.", category="Competition",  banner="images/EventX_posters/hackathon.png", event_type="Hackathon", eligibility="All engineering students", start_datetime=base + timedelta(days=8), end_datetime=base + timedelta(days=8, hours=11), registration_deadline=base + timedelta(days=6), max_participants=300, status="published", featured=True, organizer_id=organizer.id, club_id=coding.id, venue_id=venue1.id),
            Event(title="Open Mic Evening", description="Music, poetry and stand-up evening hosted by the Cultural Club.", category="Cultural", banner="images/EventX_posters/cultural_fest.png", event_type="Open Mic", eligibility="All students", start_datetime=base + timedelta(days=11, hours=3), end_datetime=base + timedelta(days=11, hours=6), registration_deadline=base + timedelta(days=10), max_participants=180, status="published", featured=True, organizer_id=organizer.id, club_id=cultural.id, venue_id=venue1.id),
            Event(title="Future Tech Talk", description="An interactive talk on software careers, product engineering and emerging technologies.", category="Seminar", banner="images/EventX_posters/tech_talk.png", event_type="Talk", eligibility="All students", start_datetime=base + timedelta(days=15), end_datetime=base + timedelta(days=15, hours=2), registration_deadline=base + timedelta(days=14), max_participants=250, status="submitted", organizer_id=organizer.id, club_id=coding.id, venue_id=venue3.id),
            Event(title="Annual Sports meet", description="A campus-wide sports event featuring athletics, football, cricket, basketball and other competitions.", category="Sports", banner="images/EventX_posters/sports_meet.png", event_type="Sports Meet", eligibility="All students", start_datetime=base + timedelta(days=18), end_datetime=base + timedelta(days=19), registration_deadline=base + timedelta(days=16), max_participants=500, status="published", featured=True, organizer_id=organizer.id, club_id=cultural.id, venue_id=venue4.id),
        ]
        db.session.add_all(events)
        db.session.flush()

        reg1 = Registration(event_id=events[0].id, student_id=students[0].id, status="registered")
        reg2 = Registration(event_id=events[0].id, student_id=students[1].id, status="registered")
        reg3 = Registration(event_id=events[1].id, student_id=students[0].id, status="registered")
        db.session.add_all([reg1, reg2, reg3])
        db.session.flush()
        db.session.add(Attendance(registration_id=reg1.id, check_in_time=base - timedelta(hours=1)))
        db.session.add(Feedback(event_id=events[0].id, student_id=students[0].id, rating=5, speaker_rating=5, organization_rating=4, venue_rating=4, comment="Great practical session."))
        db.session.add_all([
            BudgetItem(event_id=events[1].id, description="Prizes", category="Prizes", amount=8000),
            BudgetItem(event_id=events[1].id, description="Refreshments", category="Food", amount=3200),
            BudgetItem(event_id=events[1].id, description="Printing", category="Marketing", amount=1250),
            Risk(event_id=events[1].id, title="Low registration", probability="Medium", impact="Medium", mitigation="Promote through class groups."),
            Risk(event_id=events[1].id, title="Venue availability", probability="Low", impact="High", mitigation="Keep Seminar Hall as backup."),
        ])
        db.session.commit()
        print("Seed complete.")
        print("Student: akshat@eventx.local / Student@123")
        print("Organizer: organizer@eventx.local / Organizer@123")
        print("Admin: admin@eventx.local / Admin@123")


if __name__ == "__main__":
    seed()
