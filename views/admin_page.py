"""
Admin Portal Dashboard.

This module provides a Streamlit-based graphical interface for system administrators to:
1. Create and manage administrative users (Technical Project Managers, Team Leads, Track Leads).
2. Add and manage standard associates (Annotators, Stage 1/2 Reviewers).
3. Map hierarchies between TPMs, Team Leads, and Associates.
4. View, edit, and delete records across various database tables (Users, Employees, Mappings, Availabilities, Tracks).
5. Search for specific team member availabilities.
6. Manage their own passwords.
"""

# Standard library imports for byte stream handling, regular expressions, and time delays
import io
import re
import time

# Third-party imports for data manipulation and web interface rendering
import pandas as pd
import streamlit as st

# Time manipulation
from datetime import timedelta

# Local module imports for database connection and ORM schemas
from database.database import SessionLocal
from database.models import User, Employee, TeamMapping, Availability, Track

# Initialize the SQLAlchemy database session
session = SessionLocal()


def is_valid_email(email: str) -> bool:
    """
    Validate an email address to ensure it belongs to the official TCS domain.

    Args:
        email (str): The email string to validate.

    Returns:
        bool: True if it matches the specific @tcs.com pattern, False otherwise.
    """
    # Reject empty or whitespace-only strings immediately
    if email.strip() == "":
        return False

    # Regex pattern expecting alphanumeric/special characters followed strictly by @tcs.com
    pattern = r"^[A-Za-z0-9._%+-]+@tcs\.com$"
    if re.match(pattern, email):
        return True
    return False


def generate_group(row) -> str:
    """
    Generate a standardized tracking group name based on an employee's role and set.
    Primarily used when exporting data to external Excel sheets.

    Args:
        row (dict or pd.Series): A data row containing 'role' and 'set_' keys.

    Returns:
        str: A formatted group identifier string.
    """
    if row["role"] == "A":
        return f"TCS-SET{row['set_']}-ANNOTATOR-GROUP"
    elif row["role"] == "S1":
        return f"TCS-SET{row['set_']}-STAGE1-GROUP"
    elif row["role"] == "S2":
        return f"TCS-SET{row['set_']}-STAGE2-GROUP"
    return ""


def to_excel(df: pd.DataFrame) -> bytes:
    """
    Convert a pandas DataFrame into a downloadable Excel file using an in-memory buffer.

    Args:
        df (pd.DataFrame): The DataFrame to export.

    Returns:
        bytes: The binary data of the generated Excel file.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()


def get_status(email: str, role: str) -> str:
    """
    Retrieve the availability status of an employee/user on a specifically selected date.

    Note: This function relies on a globally defined `selected_date` variable
    originating from the 'Search Availability Details' tab in the admin dashboard.

    Args:
        email (str): The email of the person to look up.
        role (str): The role of the person to determine which database table to verify against.

    Returns:
        str or None: The availability status string (e.g., "Available", "Planned Leave"),
                     "Not Updated" if no record exists for that day,
                     or None if the user themselves cannot be found in the database.
    """
    # Verify higher-level management users against the 'User' table
    if role == "tpm" or role == "teamlead":
        user_details = (
            session.query(User).filter(User.email == email, User.role == role).first()
        )
        if not user_details:
            return None

    # Verify standard team members against the 'Employee' table
    if role == "associate":
        emp_details = (
            session.query(Employee)
            .filter(Employee.email == email, Employee.tag == "associate")
            .first()
        )
        if not emp_details:
            return None

    # Lookup the specific availability record for the global 'selected_date'
    rec = (
        session.query(Availability)
        .filter(
            Availability.employee_email == email, Availability.date == selected_date
        )
        .first()
    )
    return rec.status if rec else "Not Updated"


def admin_dashboard(user):
    """
    Main interface application for System Administrators.

    Renders a multi-tab dashboard allowing the admin to create users, map teams,
    view/edit/delete records across the database, and monitor team availability.

    Args:
        user (User): The ORM object representing the currently logged-in admin user.
    """
    st.header("🛡️ Admin Portal")

    # Top navigation menu using Streamlit 'pills' widget
    menu = st.pills(
        "Admin Menu",
        [
            "Create User",
            "Add Associate",
            "Map Associates",
            "View/Edit Dashboard",
            "Change Password",
        ],
        default="Create User",
    )

    # ==========================================
    # TAB 1: CREATE USER (Managers & Leads)
    # ==========================================
    if menu == "Create User":
        st.subheader("Create User")
        st.caption("Important: Try to avoid browser autofill")

        # UI mapping for display labels vs database role values
        role_map = {
            "Technical Project Manager": "tpm",
            "Language Team Lead": "teamlead",
            "Track Lead": "tracklead",
        }
        role_keys = list(role_map.keys())

        # User input fields
        selected_role = st.selectbox("Role", role_keys)
        role = role_map.get(selected_role)
        name = st.text_input("Name")
        email = st.text_input("Email", placeholder="@tcs.com")
        password = st.text_input("Password")

        if st.button("Create User", type="primary"):
            # Input Validation: Check if either of the fields are empty.
            # to ensure users don't accidentally pass whitespace-only strings.
            if email.strip() == "" or name.strip() == "" or password.strip() == "":
                # Display a highly visible error banner to the user prompting them to fix the input.
                st.error("Name, Email and Password are required")
                return

            # Input Validation: Check if the entered email is in valid format.
            if not is_valid_email(email):
                st.error("Enter a valid email")
                return

            # Check for existing records to prevent duplicates and logical conflicts
            existing_users = session.query(User).filter(User.email == email).all()
            conflict = False
            message = ""

            for u in existing_users:
                # A single email cannot act as both TPM and Team Lead
                if (u.role == "tpm" and role == "teamlead") or (
                    u.role == "teamlead" and role == "tpm"
                ):
                    conflict = True
                    message = "Same email cannot be used for both TPM and Team Lead"
                    break
                # An exact role duplicate check
                elif (
                    (u.role == "tpm" and role == "tpm")
                    or (u.role == "teamlead" and role == "teamlead")
                    or (u.role == "tracklead" and role == "tracklead")
                ):
                    conflict = True
                    message = "User already exists"
                    break

            if conflict:
                st.error(message)
            else:
                # 1. Add them to the primary login 'User' table
                user = User(name=name, email=email, password=password, role=role)
                session.add(user)

                # 2. Automatically mirror them in the 'Employee' table (used for tracking assignments)
                # Gives them default dummy values for role ("S2") and set ("1") and tags them as 'login_user'
                existing = (
                    session.query(Employee).filter(Employee.email == email).first()
                )
                if not existing:
                    emp = Employee(
                        name=name, email=email, role="S2", set_="1", tag="login_user"
                    )
                    session.add(emp)

                session.commit()
                st.success("User Created")
                time.sleep(0.5)
                st.rerun()

    # ==========================================
    # TAB 2: ADD ASSOCIATE (Standard Workforce)
    # ==========================================
    elif menu == "Add Associate":
        st.subheader("Add Associate")
        st.caption("Important: Try to avoid browser autofill")

        name = st.text_input("Name")
        email = st.text_input("Email", placeholder="@tcs.com")

        # Standard configuration options for working associates
        role_options = ["A", "S1", "S2"]
        role = st.selectbox("Select Role", role_options)
        set_options = ["1", "2", "3"]
        sets = st.selectbox("Select Set", set_options)

        if st.button("Add Associate", type="primary"):
            # Input Validation: Check if either of the fields are empty.
            # to ensure users don't accidentally pass whitespace-only strings.
            if email.strip() == "" or name.strip() == "":
                # Display a highly visible error banner to the user prompting them to fix the input.
                st.error("Name and Email are required")
                return

            # Input Validation: Check if the entered email is in valid format.
            if not is_valid_email(email):
                st.error("Enter a valid email")
                return

            # Check for duplication in the Employee table
            existing = session.query(Employee).filter(Employee.email == email).first()
            if existing:
                st.error("Same email already exists")
            else:
                # Create the Employee record and flag them as an "associate"
                emp = Employee(
                    name=name, email=email, role=role, set_=sets, tag="associate"
                )
                session.add(emp)
                session.commit()
                st.success("Associate Added")
                time.sleep(0.5)
                st.rerun()

    # ==========================================
    # TAB 3: MAP ASSOCIATES (Hierarchy Management)
    # ==========================================
    elif menu == "Map Associates":
        st.subheader("Map Associates")

        # Sub-menu to choose which level of the hierarchy is being linked
        submenu = st.pills(
            "Choose Mapping Option",
            ["TPM ⇄ Language Team Lead", "Language Team Lead ⇄ Associates"],
            default="TPM ⇄ Language Team Lead",
        )

        # Option A: Map a Technical Project Manager to their Team Leads
        if submenu == "TPM ⇄ Language Team Lead":
            # Fetch all TPMs
            leads = session.query(User).filter(User.role == "tpm").all()
            lead_emails = [l.email for l in leads]

            # Fetch everyone who is already mapped to prevent double-mapping
            mapped_emails = session.query(TeamMapping.employee_email).all()
            mapped_emails = [m[0] for m in mapped_emails]

            # Team Leads cannot be regular 'associates'
            exclude_tags = ["associate"]

            # Exclude people who are already mapped or are TPMs themselves
            all_excluded_emails = set(mapped_emails + lead_emails)

            # Get the remaining valid Team Leads available to be mapped
            employees = (
                session.query(Employee)
                .filter(~Employee.email.in_(all_excluded_emails))
                .filter(~Employee.tag.in_(exclude_tags))
                .all()
            )

            # Create dictionaries for Streamlit selectbox rendering
            lead_dict = {l.email: l.email for l in leads}
            emp_dict = {e.email: e.email for e in employees}

            # UI Mapping inputs
            selected_lead = st.selectbox(
                "Technical Project Manager", list(lead_dict.keys())
            )
            selected_emps = st.multiselect("Language Team Leads", list(emp_dict.keys()))

        # Option B: Map a Team Lead to their Associates
        elif submenu == "Language Team Lead ⇄ Associates":
            # Fetch all Team Leads
            leads = session.query(User).filter(User.role == "teamlead").all()

            # Fetch already mapped individuals
            mapped_emails = session.query(TeamMapping.employee_email).all()
            mapped_emails = [m[0] for m in mapped_emails]

            # Associates should not be managers ('login_user' tag means they are managers)
            exclude_tags = ["login_user"]

            # Find remaining associates available for mapping
            employees = (
                session.query(Employee)
                .filter(~Employee.email.in_(mapped_emails))
                .filter(~Employee.tag.in_(exclude_tags))
                .all()
            )

            lead_dict = {l.email: l.email for l in leads}
            emp_dict = {e.email: e.email for e in employees}

            selected_lead = st.selectbox("Language Team Lead", list(lead_dict.keys()))
            selected_emps = st.multiselect("Associates", list(emp_dict.keys()))

        if st.button("Save Mapping", type="primary"):
            show_warning = False
            if not selected_emps:
                st.error("Select at least one person to map")
                show_warning = True

            # Iterate through the multiple selected employees and link them to the chosen lead
            for emp in selected_emps:
                # Final database check to prevent race-condition mappings
                existing = (
                    session.query(TeamMapping).filter_by(employee_email=emp).first()
                )
                if existing:
                    st.warning(f"{emp} is already mapped to a team lead")
                    show_warning = True
                    continue

                # Create the relationship link
                mapping = TeamMapping(teamlead_email=selected_lead, employee_email=emp)
                session.add(mapping)

            session.commit()
            if not show_warning:
                st.success("Team Mapped")

    # ==========================================
    # TAB 4: VIEW / EDIT DASHBOARD (Data Management)
    # ==========================================
    elif menu == "View/Edit Dashboard":
        st.subheader("View/Edit Dashboard")

        # Dropdown to select which database table to interact with
        table_option = st.selectbox(
            "Select Table",
            [
                "User Details",
                "Employee Details",
                "Team Mapping Details",
                "Team Availability Details",
                "Search Availability Details",
                "Track Details",
            ],
        )

        # --- SUB-TAB: USER DETAILS ---
        if table_option == "User Details":
            st.markdown("##### User Details")
            data = session.query(User).all()

            # Safely fetch properties handling slight variations in ID naming (id vs id_)
            df = pd.DataFrame(
                [
                    {
                        "id_": getattr(row, "id_", getattr(row, "id", None)),
                        "email": getattr(row, "email", None),
                        "name": getattr(row, "name", None),
                        "role": getattr(row, "role", None),
                    }
                    for row in data
                ]
            )
            df["delete"] = False  # Injecting a UI-only column to track checkboxes

            # Render interactive data grid
            edited_df = st.data_editor(
                df,
                column_config={
                    "id_": st.column_config.TextColumn(label="ID"),
                    "email": st.column_config.TextColumn(label="Email"),
                    "name": st.column_config.TextColumn(label="Name"),
                    "role": st.column_config.TextColumn(label="Role"),
                    "delete": st.column_config.CheckboxColumn(label="Delete?"),
                },
                disabled=[
                    "id_",
                    "email",
                    "name",
                    "role",
                ],  # Lock everything except delete checkboxes
                width="content",
                num_rows="fixed",
                hide_index=True,
            )

            # Cascading Delete Logic
            if st.button("Delete User", type="primary"):
                edited_df["delete"] = edited_df["delete"].fillna(False).astype(bool)
                to_delete = edited_df[edited_df["delete"]]

                # Iterate through each row in the 'to_delete' DataFrame.
                # and the actual row data (which we capture in 'row').
                for _, row in to_delete.iterrows():
                    # Extract the specific details of the user slated for deletion from the current row
                    email = row["email"]
                    user_id = row["id_"]
                    role = row["role"]

                    # Security/Validation Check: Prevent the deletion of any administrator accounts.
                    # This is a critical safeguard to ensure the system always retains at least
                    # one root user, preventing accidental total system lockouts.
                    if role == "admin":
                        st.error("Cannot delete Admin")
                        return

                    # 1. Delete the core User login record
                    user_obj = session.query(User).get(user_id)
                    if user_obj:
                        session.delete(user_obj)

                    # 2. Check if this email is still needed by other roles (like TPM & Team Lead on same email)
                    remaining_users = (
                        session.query(User).filter(User.email == email).all()
                    )

                    # 3. If no login records are left, wipe their existence entirely from the system
                    if len(remaining_users) == 0:
                        # Wipe from Employee table
                        emp_obj = session.query(Employee).filter_by(email=email).first()
                        if emp_obj:
                            session.delete(emp_obj)

                        # Wipe from TeamMapping table (where they are the follower)
                        team_rows = (
                            session.query(TeamMapping)
                            .filter_by(employee_email=email)
                            .all()
                        )
                        if team_rows:
                            for t in team_rows:
                                session.delete(t)

                        # Wipe from TeamMapping table (where they are the leader)
                        team_rows = (
                            session.query(TeamMapping)
                            .filter_by(teamlead_email=email)
                            .all()
                        )
                        if team_rows:
                            for t in team_rows:
                                session.delete(t)

                        # Wipe all associated Availability history
                        avail_rows = (
                            session.query(Availability)
                            .filter_by(employee_email=email)
                            .all()
                        )
                        if avail_rows:
                            for a in avail_rows:
                                session.delete(a)

                session.commit()
                st.success(f"{len(to_delete)} row(s) deleted successfully")
                time.sleep(0.5)
                st.rerun()

        # --- SUB-TAB: EMPLOYEE DETAILS ---
        elif table_option == "Employee Details":
            st.markdown("##### Employee Details")
            data = session.query(Employee).all()

            # Return empty DataFrame if 'Employee' table is empty
            if not data:
                return st.write(pd.DataFrame())

            role_options = ["A", "S1", "S2"]
            set_options = ["1", "2", "3"]

            df = pd.DataFrame(
                [
                    {
                        "id_": getattr(row, "id_", getattr(row, "id", None)),
                        "name": getattr(row, "name", None),
                        "email": getattr(row, "email", None),
                        "role": getattr(row, "role", None),
                        "set_": getattr(row, "set_", None),
                        "tag": getattr(row, "tag", None),
                    }
                    for row in data
                ]
            )
            df["delete"] = False  # Inject checkbox state column

            # Interactive editor that allows changing Role/Set, or marking for deletion
            edited_df = st.data_editor(
                df,
                column_config={
                    "id_": st.column_config.TextColumn(label="ID"),
                    "name": st.column_config.TextColumn(label="Name"),
                    "email": st.column_config.TextColumn(label="Email"),
                    "role": st.column_config.SelectboxColumn(
                        label="Role", options=role_options
                    ),
                    "set_": st.column_config.SelectboxColumn(
                        label="Set", options=set_options
                    ),
                    "tag": st.column_config.TextColumn(label="Tag"),
                    "delete": st.column_config.CheckboxColumn(label="Delete?"),
                },
                disabled=[
                    "id_",
                    "name",
                    "email",
                    "tag",
                ],  # Lock identity and metadata fields
                width="content",
                num_rows="fixed",
                hide_index=True,
            )

            col1, col2, col3 = st.columns(3)
            with col1:
                save_clicked = st.button("Edit/Delete Record", type="primary")

            if save_clicked:
                edited_df["delete"] = edited_df["delete"].fillna(False).astype(bool)
                rows_to_delete = edited_df[edited_df["delete"]]

                # Prevent admins from deleting Manager identities ('login_user') through the associate view
                invalid = rows_to_delete[rows_to_delete["tag"] == "login_user"]
                if not invalid.empty:
                    st.error("Cannot delete the login user")
                else:
                    for _, row in edited_df.iterrows():
                        record = session.query(Employee).get(row["id_"])
                        if not record:
                            continue

                        email = row["email"]
                        if row["delete"]:
                            # Delete associate from database
                            session.delete(record)

                            # Clean up their dependencies (mappings and availability)
                            team_rows = (
                                session.query(TeamMapping)
                                .filter_by(employee_email=email)
                                .all()
                            )
                            if team_rows:
                                for t in team_rows:
                                    session.delete(t)

                            avail_rows = (
                                session.query(Availability)
                                .filter_by(employee_email=email)
                                .all()
                            )
                            if avail_rows:
                                for a in avail_rows:
                                    session.delete(a)
                        else:
                            # Apply inline edits back to the database
                            record.role = row["role"]
                            record.set_ = row["set_"]

                    session.commit()
                    st.success("Row(s) modified/deleted successfully")
                    time.sleep(0.5)
                    st.rerun()

            # Export functionality
            download_df = edited_df.copy()
            download_df["SET/ROLE"] = download_df.apply(generate_group, axis=1)
            download_df = download_df.drop(
                columns=["id_", "role", "set_", "tag", "delete"]
            )
            download_df = download_df.rename(columns={"name": "NAME", "email": "EMAIL"})
            excel_data = to_excel(download_df)

            with col3:
                st.download_button(
                    label="Export As Excel",
                    data=excel_data,
                    file_name="set_and_role_details.xlsx",
                    type="primary",
                )

        # --- SUB-TAB: TEAM MAPPING DETAILS ---
        elif table_option == "Team Mapping Details":
            st.markdown("##### Team Mapping Details")
            data = session.query(TeamMapping).all()

            # Return empty DataFrame if 'TeamMapping' table is empty
            if not data:
                return st.write(pd.DataFrame())

            columns = ["id_", "employee_email", "teamlead_email"]

            df = pd.DataFrame([vars(row) for row in data])
            df = df[columns]  # Filter out SQLAlchemy internal properties

            edited_df = st.data_editor(
                df,
                column_config={
                    "id_": st.column_config.TextColumn(label="ID"),
                    "employee_email": st.column_config.TextColumn(
                        label="Employee Email"
                    ),
                    "teamlead_email": st.column_config.TextColumn(
                        label="Reporting Lead Email"
                    ),
                },
                disabled=[
                    "id_",
                    "employee_email",
                ],  # Can only change WHO they report to, not who THEY are
                width="content",
                num_rows="fixed",
                hide_index=True,
            )
            if st.button("Save Changes", type="primary"):
                for index, row in edited_df.iterrows():
                    record = session.query(TeamMapping).get(row["id_"])
                    if record:
                        # Dynamically update the row properties
                        for col in columns:
                            if col != "id_":
                                setattr(record, col, row[col])
                session.commit()
                st.success("Updated successfully")
                time.sleep(0.5)
                st.rerun()

        # --- SUB-TAB: TEAM AVAILABILITY DETAILS ---
        elif table_option == "Team Availability Details":
            st.markdown("##### Team Availability Details")
            employees = session.query(Employee).all()

            # Return empty DataFrame if 'Employee' table is empty
            if not employees:
                st.write(pd.DataFrame())
                return

            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start Date")
            with col2:
                end_date = st.date_input("End Date")

            if start_date > end_date:
                st.error("Start date cannot be after end date")
                return

            # Build list of weekdays to render dynamic columns
            days = []
            d = start_date
            while d <= end_date:
                if d.weekday() < 5:
                    days.append(d)
                d += timedelta(days=1)

            # Construct a massive pivot table showing each employee's status per day
            data = []
            for emp in employees:
                row = {"Employee Name": emp.name, "Employee Email": emp.email}
                for d in days:
                    record = (
                        session.query(Availability)
                        .filter(
                            Availability.employee_email == emp.email,
                            Availability.date == d,
                        )
                        .first()
                    )
                    row[str(d)] = record.status if record else " "
                data.append(row)
            df = pd.DataFrame(data)

            # Combine standard tracking options with custom ones stored in DB (like specific Track names)
            predefined_options = [
                "Available",
                "Planned Leave",
                "Half Day Leave",
                "Sick Leave",
                "Emergency Leave",
                "Comp Off",
            ]
            db_status_values = set()
            for d in days:
                db_status_values.update(df[str(d)].unique())
            availability_options = list(set(predefined_options).union(db_status_values))

            # Apply dynamic selectboxes to all date columns
            column_config = {}
            for d in days:
                column_config[str(d)] = st.column_config.SelectboxColumn(
                    str(d), options=availability_options, width="content"
                )

            edited_df = st.data_editor(
                df,
                disabled=["Employee Name", "Employee Email"],
                column_config=column_config,
                width="content",
                hide_index=True,
            )

            if st.button("Save Changes", type="primary"):
                # Diff the edited dataframe against the original to find exactly what changed
                for i, row in edited_df.iterrows():
                    original_row = df.iloc[i]
                    emp_email = row["Employee Email"]
                    for d in days:
                        col = str(d)
                        new_status = row[col]
                        old_status = original_row[col]

                        # Only hit the DB if the cell was modified
                        if new_status != old_status:
                            record = (
                                session.query(Availability)
                                .filter(
                                    Availability.employee_email == emp_email,
                                    Availability.date == d,
                                )
                                .first()
                            )
                            if record:
                                record.status = new_status
                            else:
                                new_record = Availability(
                                    employee_email=emp_email, date=d, status=new_status
                                )
                                session.add(new_record)
                            session.commit()
                st.success("Updated successfully")
                time.sleep(0.5)
                st.rerun()

        # --- SUB-TAB: SEARCH AVAILABILITY DETAILS ---
        elif table_option == "Search Availability Details":
            st.markdown("##### Search Availability Details")
            search_type = st.pills(
                "Search By", ["TPM", "Team Lead", "Team Member"], default="TPM"
            )

            # Note: This variable 'selected_date' is implicitly global and read by the `get_status` function above
            global selected_date
            selected_date = st.date_input("Select Date")
            email_input = st.text_input(f"Enter {search_type} Email")
            search_btn = st.button("Search", type="primary")

            # Handle the search flow specifically when the user wants to look up a TPM (Technical Program Manager)
            if search_type == "TPM":
                # Check if the user has clicked the search button
                if search_btn:
                    # Validation 1: Ensure the email input field is not empty or just whitespace
                    if not email_input.strip():
                        st.error("Enter email to search")
                        return  # Early exit to prevent invalid queries

                    # Fetch the current working availability/status of the requested TPM
                    tpm_status = get_status(email_input, "tpm")

                    # Validation 2: Ensure a valid status was returned (meaning the TPM exists)
                    if tpm_status == None:
                        st.error("TPM Not Found")
                        return  # Early exit if the user doesn't exist in the system

                    # Display the searched TPM's personal status in a highlighted blue info box
                    st.info(f"Status: **{tpm_status}**")

                    # Fetch and display the Team Leads reporting to this TPM
                    # Query the TeamMapping table where the TPM acts as the 'teamlead_email' (manager)
                    mappings = (
                        session.query(TeamMapping)
                        .filter(TeamMapping.teamlead_email == email_input)
                        .all()  # Retrieve all matching records as a list
                    )

                    # Validation 3: Check if this TPM actually has any Team Leads mapped under them
                    if not mappings:
                        # Use a warning (yellow) instead of an error (red) because finding no
                        # subordinates is a valid state, just one that requires no further action.
                        st.warning("No team leads mapped to this TPM")
                        return

                    # Render a subtle header for the upcoming data table
                    st.caption("Mapped Language Team Leads Availability")

                    # Extract just the subordinate email addresses from the mapped ORM objects using list comprehension
                    under_tls = [m.employee_email for m in mappings]

                    # Initialize an empty list to collect data rows for our upcoming Pandas DataFrame
                    leads_status = []

                    # Iterate through each Team Lead's email to gather their specific details
                    for tl in under_tls:
                        # Query the Employee table to fetch the human-readable name associated with the email
                        tl_name = (
                            session.query(Employee).filter(Employee.email == tl).first()
                        ).name

                        # Fetch the current working status for this specific Team Lead
                        status = get_status(tl, "teamlead")

                        # Append the gathered data as a dictionary (which translates perfectly to a DataFrame row)
                        leads_status.append(
                            {"Name": tl_name, "Email": tl, "Status": status}
                        )

                    # Convert the list of dictionaries into a structured Pandas DataFrame
                    df = pd.DataFrame(leads_status)

                    # Display the DataFrame in the Streamlit UI as an interactive table.
                    # 'hide_index=True' removes the default 0, 1, 2 row numbers for a cleaner look.
                    st.dataframe(df, hide_index=True)

                    # Halt the execution of the rest of the Streamlit script.
                    # Since we have successfully found and displayed the targeted search results,
                    # there is no need to render any other default elements below this point.
                    st.stop()

            # Handle the search flow specifically when the user wants to look up a Team Lead
            elif search_type == "Team Lead":
                # Check if the user has clicked the search button
                if search_btn:
                    # Validation 1: Ensure the email input field is not just empty whitespace
                    if not email_input.strip():
                        st.error("Enter email to search")
                        return  # Early exit to prevent querying an empty string

                    # Fetch the current working availability/status of the requested Team Lead
                    tl_status = get_status(email_input, "teamlead")

                    # Validation 2: Ensure a valid status was returned (meaning the Team Lead exists)
                    if tl_status == None:
                        st.error("Team Lead Not Found")
                        return  # Early exit if the user doesn't exist in the database

                    # Display the searched Team Lead's personal status in a highlighted blue info box
                    st.info(f"Status: **{tl_status}**")

                    # 1. Fetch and display the TPM commanding this Team Lead (Upward mapping)
                    # Query the TeamMapping table where the searched Team Lead is the 'employee_email' (subordinate)
                    mapped_tpm = (
                        session.query(TeamMapping)
                        .filter(TeamMapping.employee_email == email_input)
                        .first()  # We use .first() because a Team Lead should only have one direct TPM
                    )

                    # Validation 3: Check if this Team Lead actually reports to a TPM
                    if not mapped_tpm:
                        st.warning("No TPM mapped to this team lead")
                        return  # Note: Returning here halts the script, skipping the associate check below

                    # Render a subtle UI header for the TPM data
                    st.caption("Mapped TPM Availability")

                    # Extract the TPM's email from the mapping record
                    tpm_email = mapped_tpm.teamlead_email

                    # Query the Employee table to fetch the human-readable name of the TPM
                    tpm_name = (
                        session.query(Employee)
                        .filter(Employee.email == tpm_email)
                        .first()
                    ).name

                    # Create a Pandas DataFrame to display the single TPM's details cleanly.
                    # We wrap the dictionary in a list [] because DataFrames expect iterable rows.
                    tpm_df = pd.DataFrame(
                        [
                            {
                                "Name": tpm_name,
                                "Email": tpm_email,
                                "Status": get_status(tpm_email, "tpm"),
                            }
                        ]
                    )
                    # Display the TPM DataFrame in the Streamlit UI, hiding the default index numbers
                    st.dataframe(tpm_df, hide_index=True)

                    # 2. Fetch and display the Associates commanded by this Team Lead (Downward mapping)
                    # Query the TeamMapping table again, but this time where the searched Team Lead is the 'teamlead_email' (manager)
                    mapped_members = (
                        session.query(TeamMapping)
                        .filter(TeamMapping.teamlead_email == email_input)
                        .all()  # We use .all() because a Team Lead usually manages multiple associates
                    )

                    # Validation 4: Check if this Team Lead actually has any team members under them
                    if not mapped_members:
                        st.warning("No team members mapped to this team lead")
                        return

                    # Render a subtle UI header for the Associate data table
                    st.caption("Mapped Team Members Availability")

                    # Extract just the subordinate email addresses from the mapped ORM objects using list comprehension
                    member_emails = [m.employee_email for m in mapped_members]

                    # Initialize an empty list to collect data rows for our upcoming Pandas DataFrame
                    members_status = []

                    # Iterate through each associate's email to gather their specific details
                    for ml in member_emails:
                        # Query the Employee table to fetch the human-readable name of the associate
                        mem_name = (
                            session.query(Employee).filter(Employee.email == ml).first()
                        ).name

                        # Fetch the current working status for this specific associate
                        status = get_status(ml, "associate")

                        # Append the gathered data as a dictionary representing one row in the table
                        members_status.append(
                            {"Name": mem_name, "Email": ml, "Status": status}
                        )

                    # Convert the list of associate dictionaries into a structured Pandas DataFrame
                    df = pd.DataFrame(members_status)

                    # Display the associate DataFrame in the Streamlit UI, hiding the default index numbers
                    st.dataframe(df, hide_index=True)

                    # Halt the execution of the rest of the Streamlit script.
                    # This prevents the app from rendering any default UI elements that might exist further down.
                    st.stop()

            # Handle the search flow specifically when the user wants to look up a standard Team Member (Associate)
            elif search_type == "Team Member":
                # Check if the user has clicked the search button
                if search_btn:
                    # Validation 1: Ensure the user actually typed an email before searching
                    # .strip() prevents accidental searches consisting only of space characters
                    if not email_input.strip():
                        st.error("Enter email to search")
                        return  # Stop execution if the input is invalid

                    # Fetch the current working availability/status of the requested Team Member
                    mem_status = get_status(email_input, "associate")

                    # Validation 2: Ensure a valid status was returned (verifying the associate exists in the DB)
                    if mem_status == None:
                        st.error("Team Member Not Found")
                        return  # Early exit if the email doesn't match any records

                    # Display the searched Team Member's personal status in a highlighted blue info box
                    st.info(f"Status: **{mem_status}**")

                    # Fetch and display the Team Lead overseeing this Associate (Upward mapping)
                    # Query the TeamMapping table where the searched Associate is the 'employee_email' (subordinate).
                    # We use .first() because an associate resides at the bottom of the hierarchy
                    # and should only report to exactly one Team Lead.
                    mappings = (
                        session.query(TeamMapping)
                        .filter(TeamMapping.employee_email == email_input)
                        .first()
                    )

                    # Validation 3: Check if this associate is actually assigned to a Team Lead
                    if not mappings:
                        st.warning("No team lead mapped to this associate")
                        return  # Halts execution since there's no upward reporting structure to show

                    # Render a subtle UI header for the Manager/Team Lead data
                    st.caption("Mapped Team Lead Availability")

                    # Extract the Team Lead's email from the mapping record
                    tl_email = mappings.teamlead_email

                    # Query the Employee table to fetch the human-readable name of the Team Lead
                    tl_name = (
                        session.query(Employee)
                        .filter(Employee.email == tl_email)
                        .first()
                    ).name

                    # Create a Pandas DataFrame to display the Team Lead's details cleanly.
                    # Because there is only one manager, we wrap a single dictionary inside a list [].
                    tl_df = pd.DataFrame(
                        [
                            {
                                "Name": tl_name,  # The extracted human-readable name
                                "Email": tl_email,  # The manager's email
                                "Status": get_status(
                                    tl_email, "teamlead"
                                ),  # Dynamically fetch the manager's current status
                            }
                        ]
                    )

                    # Display the Team Lead DataFrame in the Streamlit UI as an interactive table.
                    # 'hide_index=True' removes the default 0 row number for a cleaner appearance.
                    st.dataframe(tl_df, hide_index=True)

                    # Halt the execution of the rest of the Streamlit script.
                    # Since Team Members have no subordinates, this is the end of their relevant data tree.
                    st.stop()

        # --- SUB-TAB: TRACK DETAILS ---
        elif table_option == "Track Details":
            st.markdown("##### Track Details")
            data = session.query(Track).all()

            # Return empty DataFrame if 'Track' table is empty
            if not data:
                return st.write(pd.DataFrame())

            # Ensure proper rendering of columns in the Streamlit dataframe
            columns = [
                "start_date",
                "track_name",
                "track_lead",
                "number_of_sets",
                "annotation_total_files",
                "annotation_avg_time",
                "s1_total_files",
                "s1_avg_time",
                "s2_total_files",
                "s2_avg_time",
                "total_headcount",
                "employees",
                "set1_annotators_headcount",
                "set2_annotators_headcount",
                "set3_annotators_headcount",
                "set1_s1_headcount",
                "set2_s1_headcount",
                "set3_s1_headcount",
                "set1_s2_headcount",
                "set2_s2_headcount",
                "set3_s2_headcount",
                "set1_annotation_eta",
                "set2_annotation_eta",
                "set3_annotation_eta",
                "set1_s1_eta",
                "set2_s1_eta",
                "set3_s1_eta",
                "set1_s2_eta",
                "set2_s2_eta",
                "set3_s2_eta",
                "completion_eta",
            ]
            df = pd.DataFrame([vars(row) for row in data])

            # Displays the track history (Read Only mode for Admins in this view)
            df = df[columns]
            edited_df = st.data_editor(
                df,
                disabled=columns,  # Completely locked from editing here
                width="content",
                num_rows="fixed",
                hide_index=True,
            )

    # ==========================================
    # TAB 5: CHANGE PASSWORD
    # ==========================================
    elif menu == "Change Password":
        st.subheader("Change Password")
        old_password = st.text_input("Enter old password", type="password")
        new_password = st.text_input("Enter new password", type="password")
        confirm_password = st.text_input("Confirm new password", type="password")

        if st.button("Update Password", type="primary"):
            # Simple field validations
            if (
                old_password.strip() == ""
                or new_password.strip() == ""
                or confirm_password.strip() == ""
            ):
                st.error("No field should be empty")
                return
            if new_password != confirm_password:
                st.error("New password & Confirm password do not match")
            else:
                usr = (
                    session.query(User)
                    .filter(User.email == user.email, User.role == "admin")
                    .first()
                )
                if not usr:
                    st.error("User not found in database")
                elif usr.password != old_password:
                    st.error("Old password is incorrect")
                elif usr.password == new_password:
                    st.error("New password cannot be same as old password")
                else:
                    # Update and commit new plain-text password to the database
                    usr.password = new_password
                    session.commit()
                    st.success("Password updated successfully")
