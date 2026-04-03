"""
Database Configuration and Connection Module.

This module sets up the SQLAlchemy ORM (Object Relational Mapper) environment for the application.
It establishes the connection string, creates the core database engine, configures the session
factory for executing transactions, and defines the declarative base class that all database
models will inherit from.

Additionally, it handles environment-specific configurations:
- Falling back to a local SQLite database if no external database URL is provided.
- Patching legacy 'postgres://' URIs (often provided by cloud hosts like Render or Heroku)
  to 'postgresql://' to maintain compatibility with modern SQLAlchemy versions.
"""

import os

# Import the 'create_engine' function. This is the starting point for any SQLAlchemy application.
# The engine is a factory that can create new database connections for us, and it serves as the
# core interface to the database, translating Python calls into SQL.
from sqlalchemy import create_engine

# Import 'sessionmaker' to create a factory for generating new database Session objects.
# Import 'declarative_base' to construct a base class for our database models.
from sqlalchemy.orm import sessionmaker, declarative_base


# Example connection string for a PostgreSQL database
# DATABASE_URL = "postgresql://username:password@host:5432/dbname"

# 1. Dynamically find the absolute path to your root project folder
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 2. Define the path to the 'data' directory
DATA_DIR = os.path.join(BASE_DIR, "data")

# Create the 'data' folder if it doesn't exist!
# exist_ok=True ensures it won't crash if the folder is already there.
os.makedirs(DATA_DIR, exist_ok=True)

# 3. Safely construct the exact path to the database file
DB_PATH = os.path.join(DATA_DIR, "data.db")
DB_PATH = DB_PATH.replace("\\", "/")

# Attempt to fetch the database connection string from the environment variables.
# This is a security and deployment best practice, allowing you to use different databases
# for development, testing, and production without hardcoding credentials into the source code.
DATABASE_URL = os.getenv("DATABASE_URL")

# Check if an environment variable for the database URL was found.
if not DATABASE_URL:
    # FALLBACK: If no URL is found in the environment, default to a local SQLite database.
    # The 'sqlite:///' prefix indicates a relative path to the current working directory,
    # and 'data.db' will be the file created to store the data.
    DATABASE_URL = f"sqlite:///{DB_PATH}"

    # Create the SQLAlchemy engine for SQLite.
    # The 'check_same_thread': False argument is specifically required for SQLite when
    # used in multi-threaded environments (like Streamlit, FastAPI, or Flask).
    # SQLite by default restricts a connection to the thread that created it to prevent data corruption.
    # Disabling this check allows different threads to share the same database connection safely.
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # EXTERNAL DATABASE: If a DATABASE_URL was found, we prepare it here.

    # Fix Render / Heroku postgres URL issue.
    # Older cloud providers sometimes use the 'postgres://' dialect in their environment variables.
    # However, newer versions of SQLAlchemy (1.4+) strictly require the 'postgresql://' dialect name.
    # This block intercepts and safely updates the URI string to prevent a 'NoSuchModuleError'.
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")

    # Create the SQLAlchemy engine for the external database (e.g., PostgreSQL, MySQL).
    # We do not need the 'connect_args={"check_same_thread": False}' argument here
    # because external databases natively handle concurrent multi-threaded connections.
    engine = create_engine(DATABASE_URL)

# Create a configured "Session" factory class named 'SessionLocal'.
# We use 'sessionmaker' and bind it to our newly created engine.
# Instances of this class will be the actual database sessions used to query, add, modify, and commit data.
# The name 'SessionLocal' is a common convention to distinguish it from the 'Session' class imported directly from SQLAlchemy.
SessionLocal = sessionmaker(bind=engine)

# Create a base class for our declarative models.
# All ORM models (like User, Employee, Track, etc.) will inherit from this 'Base' class.
# SQLAlchemy's declarative system uses this base class to maintain a catalog of classes
# and tables, automatically mapping your Python classes to their respective database tables.
Base = declarative_base()

# Instantiate an active, working database session to be used immediately.
# (Note: In larger or asynchronous web applications, it is often better practice to create sessions
# on a per-request basis using dependency injection, rather than keeping a single global session open.
# However, for simple scripts or smaller monolithic apps, this global session provides a convenient interface.)
session = SessionLocal()
