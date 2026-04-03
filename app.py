"""
Main Entry Point for the Workforce Management System.

This script acts as the central router and authentication gateway for the Streamlit application.
It tracks user login status across application reruns using session state, displays
role-based login screens, authenticates users against the database, and routes them
to their specific role-based dashboards.
"""

# Third-party import for creating the web application UI and handling interactivity
import streamlit as st

# Import models and database configuration
from database.models import User, Base, SystemConfig
from database.database import SessionLocal, engine
from streamlit_cookies_manager import EncryptedCookieManager

# Import dashboard views (modularized Streamlit components) for different user roles.
# This keeps the main file clean and delegates UI rendering to respective modules.
from views.admin_page import admin_dashboard
from views.tpm_page import tpm_dashboard
from views.teamlead_page import teamlead_dashboard
from views.tracklead_page import tracklead_dashboard

# ==========================================
# PAGE CONFIGURATION & DATABASE SETUP
# ==========================================

# Configure the main Streamlit page layout and browser tab metadata.
# CRITICAL: `st.set_page_config` MUST be the very first Streamlit command executed.
st.set_page_config(page_title="Workforce Management System", page_icon="📚")

# Initialize a local database session for this script's execution.
session = SessionLocal()

# Trigger the table creation process safely.
# SQLAlchemy will look at the Base.metadata registry and automatically create
# any missing tables defined in models.py without overwriting existing data.
Base.metadata.create_all(engine)


# =========================
# COOKIE SETUP
# =========================
# Initialize the EncryptedCookieManager with a secure password to encrypt and decrypt cookie payloads
cookies = EncryptedCookieManager(password="super_secret_key")

# The cookie manager requires a render cycle to fetch existing cookies from the browser.
# If it is not ready, we halt the script execution here to prevent premature logic execution.
if not cookies.ready():
    st.stop()

# =========================
# ONE-TIME ADMIN CREATION
# =========================


def create_default_admin():
    """
    Database Seeder: Checks for a default administrator account and creates one
    if it does not exist. This ensures initial system access after a fresh deployment.
    """
    # Query the SystemConfig table to check if the 'admin_created' flag has already been set
    flag = (
        session.query(SystemConfig).filter(SystemConfig.key == "admin_created").first()
    )

    # If the flag exists, the default admin is already in the database, so we exit the function
    if flag:
        return

    # Initialize a new User object with hardcoded admin credentials
    admin = User(
        name="Admin",
        email="admin@tcs.com",
        password="admin",  # NOTE: Passwords MUST be hashed in a production environment
        role="admin",
    )
    # Add the new User to the session and commit it to the database.
    session.add(admin)

    # Create a configuration flag to record that the initial admin setup is complete
    config = SystemConfig(key="admin_created", value="true")
    session.add(config)

    # Commit the transaction to permanently save the new user and config to the database
    session.commit()


# Execute the seeding function immediately as the script loads.
create_default_admin()


def login_user(email: str, password: str, role: str):
    """
    Queries the database to authenticate a user based on their credentials.

    Args:
        email (str): The email address entered by the user.
        password (str): The plain-text password entered by the user.
        role (str): The system role the user is attempting to log in as.

    Returns:
        User or None: Returns the matched ORM User object if credentials and role
                      are correct, otherwise returns None.
    """
    # Filter by exact matches for email, password, AND role.
    # The role check prevents users from accessing portals meant for other roles.
    user = (
        session.query(User)
        .filter(User.email == email, User.password == password, User.role == role)
        .first()  # Retrieve the first matched record, since emails should be unique
    )
    return user


# ==========================================
# MAIN UI RENDERING
# ==========================================

# Display main title and subtitle on the page for all users.
st.title("Workforce Management System")
st.caption("Real-Time Workforce Availability & ETA Planning Made Simple")


# ==========================================
# SESSION STATE INITIALIZATION
# ==========================================
# Streamlit reruns the script from top to bottom on EVERY user interaction.
# We use `st.session_state` to persist variables (like login status) across these reruns.

# Initialize the 'user' state. This will hold the ORM User object once authenticated.
if "user" not in st.session_state:
    st.session_state.user = None

# Initialize 'selected_portal' to track which login screen the user is currently viewing.
if "selected_portal" not in st.session_state:
    st.session_state.selected_portal = None

# =========================
# AUTO LOGIN FROM COOKIE
# =========================
# Check if the user is currently unauthenticated in this specific session.

# If 'st.session_state.user' is already populated, they are currently active, so we skip this.
if st.session_state.user is None:
    # Verify if the 'user_email' key exists within the decrypted browser cookies
    # and ensure it actually contains a value (not an empty string left over from a previous logout).
    if "user_email" in cookies and cookies["user_email"]:
        # Query the database to ensure the user tied to this cookie still exists in the system
        # and to fetch their complete User ORM object (which includes their current role and name).
        user = (
            session.query(User)
            .filter(User.email == cookies["user_email"], User.role == cookies["role"])
            .first()
        )

        # If the database query successfully returns a matching user record:
        if user:
            # 1. Repopulate the active session state with the verified User object,
            # effectively authenticating them for this current Streamlit application run.
            st.session_state.user = user

            # Restore portal also
            # 2. Create a dictionary mapping the backend database roles to their corresponding
            # front-end UI portal titles. This is necessary to sync the sidebar dropdown state.
            role_to_portal = {
                "admin": "Admin Login",
                "tpm": "TPM Login",
                "teamlead": "Team Lead Login",
                "tracklead": "Track Lead Login",
            }

            # Update the 'selected_portal' in the session state using the dictionary mapping.
            # The `.get()` method safely attempts to find the user's role. If the role is
            # missing or somehow unrecognized, it gracefully defaults to "Admin Login"
            # to prevent application KeyError crashes during the UI rendering phase.
            st.session_state.selected_portal = role_to_portal.get(
                user.role, "Admin Login"
            )

# ==========================================
# ROUTING: LOGIN FLOW VS DASHBOARD FLOW
# ==========================================

# ----------------- LOGIN FLOW -----------------
# Triggered if 'user' is None (i.e., the user is NOT authenticated).
if st.session_state.user is None:
    # Render the sidebar header for the login section
    st.sidebar.markdown("# 🎯 Login Menu")

    # Define the available login portals for the sidebar dropdown menu.
    portal_options = ["Admin Login", "TPM Login", "Team Lead Login", "Track Lead Login"]

    # Set a sensible default. On the very first page load, default to "Admin Login".
    if (
        "selected_portal" not in st.session_state
        or st.session_state.selected_portal is None
    ):
        st.session_state.selected_portal = "Admin Login"

    # Display a selectbox in the sidebar to allow users to switch portals.
    new_portal = st.sidebar.selectbox(
        "👉 Select Portal",
        portal_options,
        index=portal_options.index(st.session_state.selected_portal),
    )

    # If the user selects a different portal, update the session state and trigger a rerun.
    # This forces the script to update the UI headers and logic based on the new selection.
    if new_portal != st.session_state.selected_portal:
        st.session_state.selected_portal = new_portal
        st.rerun()

    # Default placeholder text for the email input field.
    email_placeholder = "@tcs.com"

    # Configure the main area UI elements and set the expected database 'role' variable
    # based strictly on the portal the user currently has selected.
    if st.session_state.selected_portal == "Admin Login":
        st.header("🛡️ Admin Login")
        email_placeholder = "admin@tcs.com"
        role = "admin"
    elif st.session_state.selected_portal == "TPM Login":
        st.header("👩🏻‍💻 TPM Login")
        role = "tpm"
    elif st.session_state.selected_portal == "Team Lead Login":
        st.header("👨‍👨 Team Lead Login")
        role = "teamlead"
    elif st.session_state.selected_portal == "Track Lead Login":
        st.header("📝 Track Lead Login")
        role = "tracklead"

    # Render the input fields and collect user credentials.
    email = st.text_input("Email", placeholder=email_placeholder)
    password = st.text_input("Password", type="password")  # Obscured text for security

    # Handle the login attempt when the "Login" button is clicked.
    if st.button("🗝️ Login", type="primary"):
        # Input Validation: Check if either the email or password fields are empty.
        # to ensure users don't accidentally pass whitespace-only strings.
        if email.strip() == "" or password.strip() == "":
            # Display a highly visible error banner to the user prompting them to fix the input.
            st.error("Enter both your email and password to log in")

            # Halt further execution of the login process immediately.
            # This early exit prevents unnecessary (and potentially failing) database queries.
            st.stop()

        # Execute the database query to verify credentials
        user = login_user(email, password, role)

        if not user:
            # Authentication failed: Show an error message.
            st.error("❌ Invalid Credentials")
        else:
            # Authentication succeeded: Save the verified User to the session state.
            st.session_state.user = user

            # SAVE COOKIE
            # Store the user's email and role in encrypted cookies for future auto-login
            cookies["user_email"] = user.email
            cookies["role"] = user.role
            cookies.save()  # Push the updated cookies to the user's browser

            # Display a temporary success banner
            st.success("🎉 Login Successful")

            # Force a rerun. Because 'user' is now populated, the script will bypass
            # this Login Flow block and enter the Dashboard Flow below.
            st.rerun()

# ----------------- DASHBOARD FLOW -----------------
# Triggered if the user IS authenticated.
else:
    # Retrieve the logged-in user details and their login portal from session state.
    user = st.session_state.user
    portal = st.session_state.selected_portal

    # Display a persistent greeting in the sidebar.
    st.sidebar.markdown(f"𖦹 **Welcome: {user.name}**")

    # Provide a logout mechanism. Clearing session state and rerunning kicks them to the login screen.
    if st.sidebar.button("⏻ Logout", type="primary"):
        # CLEAR COOKIE
        # Overwrite the cookie values with empty strings to wipe persistent login data
        cookies["user_email"] = ""
        cookies["role"] = ""
        cookies.save()  # Save the cleared cookies to the browser

        # Reset the active session state variables back to unauthenticated status
        st.session_state.user = None
        st.session_state.selected_portal = None

        # Trigger a script rerun to send the user back to the login screen
        st.rerun()

    # Dashboard routing with strict security verification.
    # We verify BOTH the portal they used AND their actual database role.
    if portal == "Admin Login" and user.role == "admin":
        admin_dashboard(user)
    elif portal == "TPM Login" and user.role == "tpm":
        tpm_dashboard(user)
    elif portal == "Team Lead Login" and user.role == "teamlead":
        teamlead_dashboard(user)
    elif portal == "Track Lead Login" and user.role == "tracklead":
        tracklead_dashboard(user)
    else:
        # Fallback security check for mismatched portals and roles.
        st.error("❌ Access Denied")
