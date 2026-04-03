"""
Technical Project Manager (TPM) Dashboard Module.

This module provides a Streamlit-based interface specifically tailored for TPMs.
It enables them to:
1. Update their own daily availability status.
2. Update the availability status for the Language Team Leads mapped directly under them.
3. View and bulk-edit the availability of their entire management team over a selected date range using an interactive grid.
4. Manage their own login password securely.
"""

# Third-party imports for data manipulation and rendering the web interface
import pandas as pd
import streamlit as st

# Import for handling date ranges and arithmetic
from datetime import timedelta

# Local imports for database connection and ORM models
from database.database import SessionLocal
from database.models import User, TeamMapping, Employee, Availability

# Initialize a local database session
session = SessionLocal()


def tpm_dashboard(user):
    """
    Renders the main dashboard interface for a logged-in Technical Project Manager (TPM).

    This function handles the routing between different dashboard tabs (Availability Updates,
    Bulk Editing, Password Management) and executes the corresponding database queries
    and updates based on user interaction.

    Args:
        user (User): The ORM object representing the currently authenticated TPM.
    """
    st.header("👩🏻‍💻 TPM Dashboard")

    # Top-level navigation menu using Streamlit pills
    menu = st.pills(
        "Dashboard Menu",
        ["Update Availability", "View/Edit Dashboard", "Change Password"],
        default="Update Availability",
    )

    # ==========================================
    # TAB 1: UPDATE AVAILABILITY
    # ==========================================
    if menu == "Update Availability":
        st.subheader("Update Availability Status")

        # Sub-menu to toggle between updating their own calendar or a subordinate Team Lead's calendar
        submenu = st.pills(
            "Choose Update Option", ["Self", "Team Leads"], default="Self"
        )

        # --- Option A: Update Own Availability ---
        if submenu == "Self":
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start Date")
            with col2:
                end_date = st.date_input("End Date")

            # Date validation checks
            if start_date > end_date:
                st.error("Start date cannot be after end date")
                return
            if start_date.weekday() >= 5 or end_date.weekday() >= 5:
                st.error("Start date and end date should be weekdays")
                return

            # Standard options for tracking availability
            status_options = [
                "Available",
                "Planned Leave",
                "Half Day Leave",
                "Sick Leave",
                "Emergency Leave",
                "Comp Off",
            ]
            selected_status = st.selectbox("Select Status", status_options)

            if st.button("Save Details", type="primary"):
                # Calculate the total number of days in the selected range
                delta = end_date - start_date

                # Loop through each day in the range
                for i in range(delta.days + 1):
                    d = start_date + timedelta(days=i)

                    # Automatically skip weekends (Saturday=5, Sunday=6)
                    if d.weekday() >= 5:
                        continue

                    # Check if an availability record already exists for this date
                    record = (
                        session.query(Availability)
                        .filter(
                            Availability.employee_email == user.email,
                            Availability.date == d,
                        )
                        .first()
                    )

                    # Overwrite the status if it exists, otherwise create a new record
                    if record:
                        record.status = selected_status
                    else:
                        session.add(
                            Availability(
                                employee_email=user.email,
                                date=d,
                                status=selected_status,
                            )
                        )
                session.commit()
                st.success(
                    f"Status '{selected_status}' updated from {start_date} to {end_date}"
                )

        # --- Option B: Update Subordinate Team Leads' Availability ---
        elif submenu == "Team Leads":
            # Fetch all mapping records where this TPM is the designated leader
            mappings = (
                session.query(TeamMapping)
                .filter(TeamMapping.teamlead_email == user.email)
                .all()
            )
            teamlead_emails = [m.employee_email for m in mappings]

            # Retrieve the actual Employee records for those mapped Team Leads
            team_leads = (
                session.query(Employee)
                .filter(Employee.email.in_(teamlead_emails))
                .all()
            )

            if not team_leads:
                st.warning("No team leads mapped to you yet")
                return

            # Create a dictionary to map Team Lead names to their emails for the dropdown UI
            tl_dict = {tl.name: tl.email for tl in team_leads}
            selected_tl = st.selectbox("Select Team Lead", list(tl_dict.keys()))

            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start Date")
            with col2:
                end_date = st.date_input("End Date")

            # Date validation checks
            if start_date > end_date:
                st.error("Start date cannot be after end date")
                return
            if start_date.weekday() >= 5 or end_date.weekday() >= 5:
                st.error("Start date and end date should be weekdays")
                return

            status_options = [
                "Available",
                "Planned Leave",
                "Half Day Leave",
                "Sick Leave",
                "Emergency Leave",
                "Comp Off",
            ]
            selected_status = st.selectbox("Select Status", status_options)

            if st.button("Save Details", type="primary"):
                # Look up the selected Team Lead's email using the dictionary
                tl_email = tl_dict[selected_tl]
                delta = end_date - start_date

                # Loop through dates and apply the status, skipping weekends
                for i in range(delta.days + 1):
                    d = start_date + timedelta(days=i)
                    if d.weekday() >= 5:
                        continue

                    record = (
                        session.query(Availability)
                        .filter(
                            Availability.employee_email == tl_email,
                            Availability.date == d,
                        )
                        .first()
                    )

                    if record:
                        record.status = selected_status
                    else:
                        session.add(
                            Availability(
                                employee_email=tl_email, date=d, status=selected_status
                            )
                        )
                session.commit()
                st.success(
                    f"Status '{selected_status}' applied for {selected_tl} from {start_date} to {end_date}"
                )

    # ==========================================
    # TAB 2: VIEW / EDIT DASHBOARD (Bulk Edits)
    # ==========================================
    elif menu == "View/Edit Dashboard":
        st.subheader("View/Edit Dashboard")

        # Determine the scope of people to display (Subordinate Team Leads + the TPM themselves)
        mappings = (
            session.query(TeamMapping)
            .filter(TeamMapping.teamlead_email == user.email)
            .all()
        )
        emp_emails = [m.employee_email for m in mappings]
        emp_emails.append(user.email)  # Append the TPM to the list

        # Fetch Employee records for everyone in scope
        employees = session.query(Employee).filter(Employee.email.in_(emp_emails)).all()

        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date")
        with col2:
            end_date = st.date_input("End Date")

        if start_date > end_date:
            st.error("Start date cannot be after end date")
            return
        if start_date.weekday() >= 5 or end_date.weekday() >= 5:
            st.error("Start date and End date should be weekdays")
            return

        # Build a list of valid weekdays to act as columns in our data table
        days = []
        d = start_date
        while d <= end_date:
            if d.weekday() < 5:
                days.append(d)
            d += timedelta(days=1)

        # Build the table data row-by-row mapping employees to their daily availability
        data = []
        for emp in employees:
            row = {"Employee Name": emp.name, "Employee Email": emp.email}
            for d in days:
                record = (
                    session.query(Availability)
                    .filter(
                        Availability.employee_email == emp.email, Availability.date == d
                    )
                    .first()
                )
                # Map the status if it exists, otherwise leave a blank space
                row[str(d)] = record.status if record else " "
            data.append(row)

        df = pd.DataFrame(data)

        # Compile a list of all possible statuses. This includes standard predefined ones,
        # plus any custom statuses (like specific Track names) already saved in the database
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

        # Configure the Streamlit data editor columns dynamically based on the date range
        column_config = {}
        for d in days:
            column_config[str(d)] = st.column_config.SelectboxColumn(
                str(d), options=availability_options, width="content"
            )

        # Display the interactive grid. Names and Emails are locked; dates are editable dropdowns.
        edited_df = st.data_editor(
            df,
            disabled=["Employee Name", "Employee Email"],
            column_config=column_config,
            width="content",
        )

        if st.button("Save Changes", type="primary"):
            # To save efficiently, diff the edited dataframe against the original
            for i, row in edited_df.iterrows():
                original_row = df.iloc[i]
                emp_email = row["Employee Email"]

                for d in days:
                    col = str(d)
                    new_status = row[col]
                    old_status = original_row[col]

                    # Only hit the database if the user actually changed the dropdown value
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
            st.success("Database updated successfully")

    # ==========================================
    # TAB 3: CHANGE PASSWORD
    # ==========================================
    elif menu == "Change Password":
        st.subheader("Change Password")
        old_password = st.text_input("Enter old password", type="password")
        new_password = st.text_input("Enter new password", type="password")
        confirm_password = st.text_input("Confirm new password", type="password")

        if st.button("Update Password", type="primary"):
            # Check for typos in the new password confirmation
            if new_password != confirm_password:
                st.error("New password & Confirm password do not match")
            else:
                usr = (
                    session.query(User)
                    .filter(User.email == user.email, User.role == "tpm")
                    .first()
                )
                if not usr:
                    st.error("User not found in database")
                elif usr.password != old_password:
                    st.error("Old password is incorrect")
                elif usr.password == new_password:
                    st.error("New password cannot be same as old password")
                else:
                    # Update password and commit to DB
                    usr.password = new_password
                    session.commit()
                    st.success("Password updated successfully")
