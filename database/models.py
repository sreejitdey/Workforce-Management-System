"""
Database Models Module.

This module defines the SQLAlchemy Object Relational Mapper (ORM) classes
that represent the database tables for the Workforce Management System.
Each class inherits from the declarative Base and maps to a specific table
in the underlying SQL database, defining its columns, data types, and constraints.
"""

# Import the base factory function to create the foundational class for our ORM models.
from sqlalchemy.orm import declarative_base

# Import specific column types, constraints, and structural elements from SQLAlchemy
# needed to construct the schema of our database tables.
from sqlalchemy import Column, Integer, Float, String, Date, UniqueConstraint


# Base class for our declarative class definitions.
# All ORM models inherit from this to register themselves as part of the database metadata.
# When Base.metadata.create_all() is called, it looks at all classes inheriting from this Base.
Base = declarative_base()


class SystemConfig(Base):
    """
    Represents key-value pairs for global system configuration settings.
    This is typically used to track one-time setup flags (like whether the initial
    default administrator account has been created) to prevent redundant operations
    on application restarts.
    """

    # The explicit name of the table as it will appear in the SQL database.
    __tablename__ = "system_config"

    # The string identifier for the configuration setting (e.g., 'admin_created').
    # Set as the primary key, meaning each configuration key must be entirely unique.
    key = Column(String, primary_key=True)

    # The string value associated with the configuration key (e.g., 'true', 'false', '1.0').
    value = Column(String)


class User(Base):
    """
    Represents a system user capable of logging into the application (e.g., Admin, TPM, Team Lead).
    This table manages authentication and high-level role-based access control.
    """

    __tablename__ = "users"

    # Unique identifier for the user record.
    # Note: We use `id_` instead of `id` to avoid shadowing Python's built-in `id()` function.
    id_ = Column(Integer, primary_key=True)
    # Full name of the user. `nullable=False` ensures this field cannot be left empty in the DB.
    name = Column(String, nullable=False)
    # Email address (used for login). Must be provided.
    email = Column(String, nullable=False)
    # Login password (stored as plain text based on this implementation). Must be provided.
    password = Column(String, nullable=False)
    # The access level/role of the user (e.g., 'admin', 'tpm', 'teamlead', 'tracklead').
    role = Column(String, nullable=False)

    # Composite unique constraint to ensure that an email cannot have the exact same role twice.
    # However, one email *can* hold multiple different roles.
    # This prevents duplicate duplicate permission entries in the database.
    __table_args__ = (UniqueConstraint("email", "role", name="uq_user_email_role"),)


class Employee(Base):
    """
    Represents a workforce associate or employee tracked in the system.
    This table stores their specific operational role and dataset assignment.
    Unlike 'Users' who manage the system, 'Employees' are the workforce being managed.
    """

    __tablename__ = "employees"

    # Unique identifier for the employee record
    id_ = Column(Integer, primary_key=True)
    # Full name of the employee
    name = Column(String, nullable=False)
    # Email address; enforced as globally unique in this specific table
    # `unique=True` ensures no two employees can be registered with the exact same email.
    email = Column(String, nullable=False, unique=True)
    # Operational role (e.g., "A" for Annotator, "S1" for Stage 1, "S2" for Stage 2)
    role = Column(String, nullable=False)
    # The dataset or set number assigned to the employee (e.g., "1", "2", "3")
    set_ = Column(String, nullable=False)
    # Internal tag indicating if they are a standard "associate" or a "login_user" (manager)
    tag = Column(String, nullable=False)


class TeamMapping(Base):
    """
    Represents the hierarchical mapping between team members and their designated leaders.
    Used to link TPMs to Team Leads, and Team Leads to Associates.
    This creates the reporting structure necessary for role-based dashboards to filter data.
    """

    __tablename__ = "team_mapping"

    # Auto-incrementing primary key for the mapping record.
    # `autoincrement=True` explicitly tells the DB to generate the next integer automatically.
    id_ = Column(Integer, primary_key=True, autoincrement=True)
    # The email of the leader (TPM or Team Lead). Acts as a pseudo-foreign key reference.
    teamlead_email = Column(String, nullable=False)
    # The email of the subordinate. Enforced as unique so an employee can only have ONE direct manager.
    # This enforces a strict top-down tree hierarchy rather than a matrix reporting structure.
    employee_email = Column(String, nullable=False, unique=True)


class Availability(Base):
    """
    Represents the daily availability or leave status for an individual employee.
    This is a transactional table where records are added continuously over time.
    """

    __tablename__ = "availability"

    # Auto-incrementing primary key for the availability record
    id_ = Column(Integer, primary_key=True, autoincrement=True)
    # The email of the employee whose availability is being recorded
    employee_email = Column(String, nullable=False)
    # The specific calendar date for this availability status.
    # Uses SQLAlchemy's Date type to ensure valid date formatting in the SQL backend.
    date = Column(Date, nullable=False)
    # The status code (e.g., 'Available', 'Planned Leave', or a specific custom Track Name)
    status = Column(String, nullable=False)

    # Composite unique constraint to ensure an employee only has one recorded status per single day.
    # If a new status is submitted for the same date, the old one must be overwritten.
    # This prevents the system from calculating an employee's hours multiple times for a single day.
    __table_args__ = (
        UniqueConstraint("employee_email", "date", name="uq_emp_email_date"),
    )


class Track(Base):
    """
    Represents a planned project track, containing targets, required headcounts,
    and calculated Estimated Times of Arrival (ETAs) across multiple datasets and stages.
    This table stores the aggregate mathematical blueprint for a specific project.
    """

    __tablename__ = "tracks"

    # Unique identifier for the track record
    id_ = Column(Integer, primary_key=True)
    # The official start date of the track. Used as the anchor point for ETA calculations.
    start_date = Column(Date, nullable=False)
    # The string name identifier of the track
    track_name = Column(String, nullable=False)
    # The email of the Track Lead responsible for this project
    track_lead = Column(String, nullable=False)
    # The total number of datasets included in this track (1, 2, or 3)
    number_of_sets = Column(Integer, nullable=False)

    # Formula/String representation of total files allocated for the Annotation stage
    annotation_total_files = Column(String, nullable=False)
    # Expected average time in minutes to annotate a single file.
    # Stored as a Float to accommodate precise decimal values (e.g., 2.5 minutes).
    annotation_avg_time = Column(Float, nullable=False)

    # Formula/String representation of total files allocated for Stage 1 Review
    s1_total_files = Column(String, nullable=False)
    # Expected average time in minutes for Stage 1 Review
    s1_avg_time = Column(Float, nullable=False)

    # Formula/String representation of total files allocated for Stage 2 Review
    s2_total_files = Column(String, nullable=False)
    # Expected average time in minutes for Stage 2 Review
    s2_avg_time = Column(Float, nullable=False)

    # The overall total number of employees assigned to this track
    total_headcount = Column(Integer, nullable=False)
    # Stringified list of dictionaries containing detailed employee assignment data.
    # JSON arrays are stored as Strings here to maintain compatibility with simpler SQL engines like SQLite.
    employees = Column(String, nullable=False)

    # Headcount breakdowns segregated by Set and Role
    set1_annotators_headcount = Column(Integer, nullable=False)
    set2_annotators_headcount = Column(Integer, nullable=False)
    set3_annotators_headcount = Column(Integer, nullable=False)
    set1_s1_headcount = Column(Integer, nullable=False)
    set2_s1_headcount = Column(Integer, nullable=False)
    set3_s1_headcount = Column(Integer, nullable=False)
    set1_s2_headcount = Column(Integer, nullable=False)
    set2_s2_headcount = Column(Integer, nullable=False)
    set3_s2_headcount = Column(Integer, nullable=False)

    # Calculated ETA date/duration strings for each Set and Stage.
    # These are nullable because depending on the 'number_of_sets', some may not be active.
    # `nullable=True` means these columns are allowed to contain NULL values in the database.
    set1_annotation_eta = Column(String, nullable=True)
    set2_annotation_eta = Column(String, nullable=True)
    set3_annotation_eta = Column(String, nullable=True)
    set1_s1_eta = Column(String, nullable=True)
    set2_s1_eta = Column(String, nullable=True)
    set3_s1_eta = Column(String, nullable=True)
    set1_s2_eta = Column(String, nullable=True)
    set2_s2_eta = Column(String, nullable=True)
    set3_s2_eta = Column(String, nullable=True)

    # The absolute final completion date for the entire track across all sets and stages
    completion_eta = Column(Date, nullable=False)
