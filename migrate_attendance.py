from app import app
from models import db


with app.app_context():

    if db.engine.dialect.name != "sqlite":
        raise RuntimeError(
            "This migration script is intended for the SQLite EventX database."
        )

    with db.engine.begin() as conn:

        print("Starting attendance migration...")

        # Temporarily disable foreign-key enforcement
        # while rebuilding the SQLite table.
        conn.exec_driver_sql(
            "PRAGMA foreign_keys=OFF"
        )

        # Create replacement table without the old
        # unique(registration_id) constraint.
        conn.exec_driver_sql("""
            CREATE TABLE attendance_new (
                id INTEGER PRIMARY KEY,
                registration_id INTEGER NOT NULL,
                check_in_time DATETIME,
                session_label VARCHAR(100),
                status VARCHAR(30),
                CONSTRAINT fk_attendance_registration
                    FOREIGN KEY (registration_id)
                    REFERENCES registration (id),
                CONSTRAINT uq_attendance_registration_session
                    UNIQUE (registration_id, session_label)
            )
        """)

        # Preserve all existing attendance records.
        conn.exec_driver_sql("""
            INSERT INTO attendance_new (
                id,
                registration_id,
                check_in_time,
                session_label,
                status
            )
            SELECT
                id,
                registration_id,
                check_in_time,
                COALESCE(session_label, 'Main Session'),
                COALESCE(status, 'present')
            FROM attendance
        """)

        # Replace the old table.
        conn.exec_driver_sql(
            "DROP TABLE attendance"
        )

        conn.exec_driver_sql("""
            ALTER TABLE attendance_new
            RENAME TO attendance
        """)

        conn.exec_driver_sql("""
            CREATE INDEX ix_attendance_registration_id
            ON attendance (registration_id)
        """)

        conn.exec_driver_sql(
            "PRAGMA foreign_keys=ON"
        )

        print(
            "Attendance migration completed successfully."
        )