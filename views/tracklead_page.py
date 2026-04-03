"""
Track Management and Planning Dashboard.

This module provides a Streamlit-based user interface for Track Leads to:
1. Plan new tracks (projects) by allocating files, setting targets, and estimating completion times.
2. Select and assign employees to different roles (Annotator, Stage 1 Reviewer, Stage 2 Reviewer).
3. Calculate complex Estimated Times of Arrival (ETAs) taking employee availability and weekends into account.
4. View, edit, and update ongoing tracks and employee availabilities.
5. Change user passwords.
"""

# Standard library imports for handling byte streams, evaluating literal structures, time delays, and math
import io
import ast
import time
import math

# Imports for date and time manipulations
from datetime import timedelta, date

# Third-party imports for data manipulation and creating the web interface
import pandas as pd
import streamlit as st

# Local module imports for database connections and Object Relational Mapping (ORM) models
from database.database import SessionLocal
from database.models import User, Employee, TeamMapping, Availability, Track

# Initialize the database session to interact with the SQL database
session = SessionLocal()


def is_weekday(d: date) -> bool:
    """
    Determine if a given date falls on a weekday (Monday through Friday).

    Args:
        d (date): The date to check.

    Returns:
        bool: True if the day is Monday (0) to Friday (4), False if Saturday (5) or Sunday (6).
    """
    return d.weekday() < 5


def next_weekday(d: date) -> date:
    """
    Find the next available weekday, starting from a given date.
    If the current date is already a weekday, it returns the current date.

    Args:
        d (date): The starting date.

    Returns:
        date: The first date on or after `d` that is a weekday.
    """
    while not is_weekday(d):
        d += timedelta(days=1)
    return d


def add_one_workday(d: date) -> date:
    """
    Add exactly one workday to a given date, skipping weekends.

    Args:
        d (date): The starting date.

    Returns:
        date: The next valid working day (Monday-Friday).
    """
    d += timedelta(days=1)
    while not is_weekday(d):
        d += timedelta(days=1)
    return d


def generate_group(row) -> str:
    """
    Generate a standardized group/team name string based on an employee's role and set.
    Used primarily for Excel exports.

    Args:
        row (dict or pd.Series): A data row containing 'Role' and 'Set' keys.

    Returns:
        str: A formatted string identifying the specific group (e.g., 'TCS-SET1-ANNOTATOR-GROUP').
    """
    if row["Role"] == "A":
        return f"TCS-SET{row['Set']}-ANNOTATOR-GROUP"
    elif row["Role"] == "S1":
        return f"TCS-SET{row['Set']}-STAGE1-GROUP"
    elif row["Role"] == "S2":
        return f"TCS-SET{row['Set']}-STAGE2-GROUP"
    return ""


def to_excel(df: pd.DataFrame) -> bytes:
    """
    Convert a pandas DataFrame into an Excel file stored in an in-memory byte buffer.
    This is necessary for Streamlit to provide a downloadable Excel file without saving to the disk.

    Args:
        df (pd.DataFrame): The DataFrame to convert.

    Returns:
        bytes: The binary data of the generated Excel file.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()


def calculate_eta(
    session,
    total_files,
    start_date,
    end_date,
    target,
    avg_time,
    emp_dict,
    selected_employees,
    stage,
    assigned_set,
):
    """
    Calculate the Estimated Time of Arrival (ETA) for completing a specific stage of work.

    This function simulates the work process day by day, taking into account:
    - The number of files to process.
    - Employee daily capacity (target).
    - Weekends and specific employee availability (Full day, Half day).
    - Dependencies between stages (e.g., S1 cannot finish before Annotation finishes).

    The results are saved directly into Streamlit's `st.session_state` and rendered to the UI.

    Args:
        session: The active database session.
        total_files (int): Number of files to process in this stage.
        start_date (date): The target start date for the track.
        end_date (date): The absolute deadline for the track.
        target (int): Daily file completion target per full-time person.
        avg_time (float): Average minutes to process one file.
        emp_dict (dict): Dictionary mapping employee identifiers.
        selected_employees (list): List of employee dictionaries assigned to this stage.
        stage (str): The name of the stage ("Annotation", "S1", "S2").
        assigned_set (str): The identifier for the current dataset (e.g., "SET1").
    """
    remaining_files = total_files

    # Stage 2 (S2) is dependent on Stage 1 (S1).
    # S2 calculation starts from the day AFTER S1 completes.
    if stage == "S2":
        if f"{assigned_set}_S1_ETA" not in st.session_state:
            st.error(
                f"Calculate {assigned_set} S1 ETA before calculating {assigned_set} S2 ETA"
            )
            return
        current_date = add_one_workday(st.session_state[f"{assigned_set}_S1_ETA"])
    else:
        current_date = start_date

    total_days = 0
    remaining_hours = 0

    # safety_cap prevents the while-loop from running infinitely if daily capacity is 0
    safety_cap = 365
    steps = 0

    # Simulate work progression day by day until all files are processed
    while remaining_files > 0:
        steps += 1

        # Abort if the simulation exceeds a year or passes the user-defined end_date
        if steps > safety_cap or current_date > end_date:
            if f"{assigned_set}_{stage}_ETA" in st.session_state:
                del st.session_state[f"{assigned_set}_{stage}_ETA"]
                del st.session_state[f"{assigned_set}_{stage}_Duration"]
            st.error(
                f"Could not compute ETA for {assigned_set} {stage} — No available capacity / No selected resources"
            )
            return

        # Skip weekends during the calculation
        if not is_weekday(current_date):
            current_date = next_weekday(current_date)

        daily_capacity = 0
        headcount = 0

        # Check the database for each employee's specific availability on this exact 'current_date'
        for emp in selected_employees:
            record = (
                session.query(Availability)
                .filter(
                    Availability.employee_email == emp_dict[emp],
                    Availability.date == current_date,
                )
                .first()
            )

            # Full availability adds a full daily target to the team's capacity
            if record and record.status == "Available":
                daily_capacity += target
                headcount += 1
            # Half-day availability adds half a daily target
            if record and record.status == "Half Day Leave":
                daily_capacity += target // 2
                headcount += 0.5

        files_done = 0
        if daily_capacity > 0:
            # The team can only process up to the 'daily_capacity', or whatever files remain (whichever is smaller)
            files_done = min(daily_capacity, remaining_files)
            remaining_files -= files_done

            # If the team finishes the remaining files without using their full daily capacity,
            # distribute the actual files done across the headcount to calculate precise hours later
            if files_done < daily_capacity:
                if headcount != 0:
                    files_done = math.ceil(files_done / headcount)

        # Track the time spent
        if remaining_files > 0:
            # It took a full day, and work is still pending
            total_days += 1
        elif remaining_files == 0:
            # All work is finished today. Was it a full day or a partial day?
            if daily_capacity == files_done:
                total_days += 1
            else:
                # Calculate the exact fractional hours spent on the final day based on the avg_time
                remaining_hours = (files_done * avg_time) / 60

        # Move forward to the next day
        current_date = add_one_workday(current_date)

    # Formatting the completion date: The while-loop exits on the day AFTER work finishes.
    # We step back by one day, and ensure it lands on a weekday to find the true completion date.
    completion_date = add_one_workday(current_date) - timedelta(days=1)
    d = current_date - timedelta(days=1)
    while not is_weekday(d):
        d -= timedelta(days=1)
    completion_date = d

    # Standardize remaining hours based on an 8-hour workday
    working_hours_per_day = 8
    remaining_hours = int(math.ceil(remaining_hours % working_hours_per_day))

    # If the remaining hours equal a full 8-hour shift, convert it into an additional day
    if remaining_hours == 8:
        total_days += 1
        remaining_hours = 0

    # Dependency Logic: Stage 1 (S1) review cannot finish BEFORE the underlying Annotations finish.
    # If the math says S1 finishes earlier, pad the total days to match the Annotation ETA.
    if stage == "S1":
        if f"{assigned_set}_Annotation_ETA" not in st.session_state:
            st.error(
                f"Calculate {assigned_set} Annotation ETA before calculating {assigned_set} S1 ETA"
            )
            return
        if completion_date < st.session_state[f"{assigned_set}_Annotation_ETA"]:
            extra_days = 0
            start = completion_date
            end = st.session_state[f"{assigned_set}_Annotation_ETA"]
            # Count the weekdays between the premature completion and the actual valid completion
            while start < end:
                if start.weekday() < 5:
                    extra_days += 1
                start += timedelta(days=1)
            total_days += extra_days
            completion_date = st.session_state[f"{assigned_set}_Annotation_ETA"]

    # Format and display the final calculated result on the Streamlit interface
    total_work = ""
    if remaining_hours == 0:
        total_work = f"{total_days} day(s)"
        st.markdown(
            f"##### 🕓 **{assigned_set} {stage} ETA** ➡️ {completion_date} ⏳ {total_work}"
        )
    elif total_days == 0:
        total_work = f"{remaining_hours} hour(s)"
        st.markdown(
            f"##### 🕓 **{assigned_set} {stage} ETA** ➡️ {completion_date} ⏳ {total_work}"
        )
    else:
        total_work = f"{total_days} day(s) + {remaining_hours} hour(s)"
        st.markdown(
            f"##### 🕓 **{assigned_set} {stage} ETA** ➡️ {completion_date} ⏳ {total_work}"
        )

    # Store the results in the session state so they can be saved to the database later
    st.session_state[f"{assigned_set}_{stage}_ETA"] = completion_date
    st.session_state[f"{assigned_set}_{stage}_Duration"] = total_work


def change_availability_status(
    selected_employees, start_date, completion_date, track_name
):
    """
    Update the database to reflect that selected employees are busy with a specific track.

    It searches for 'Available' records between the start and end dates and
    changes their status to the name of the track, effectively blocking out their calendar.

    Args:
        selected_employees (list): List of employee email addresses.
        start_date (date): The start date of the track.
        completion_date (date): The calculated end date of the track.
        track_name (str): The name of the track to serve as the new status.
    """
    for emp_email in selected_employees:
        record = (
            session.query(Availability)
            .filter(
                Availability.employee_email == emp_email,
                Availability.date >= start_date,
                Availability.date <= completion_date,
            )
            .all()
        )
        for r in record:
            if r.status == "Available":
                r.status = f"{track_name}"


def _on_track_change():
    """Streamlit callback: Resets the start date and load status when a user selects a different track in the View/Edit tab."""
    st.session_state.ved_start_date = None
    st.session_state.ved_loaded = False


def _on_start_change():
    """Streamlit callback: Resets the load status when a user selects a different start date in the View/Edit tab."""
    st.session_state.ved_loaded = False


def tracklead_dashboard(user):
    """
    Main application interface for the Track Lead.

    Renders a multi-tab dashboard allowing the user to:
    - Plan new tracks and calculate ETAs.
    - View and edit existing tracks and team availability.
    - Change their account password.

    Args:
        user (User): The ORM object representing the currently logged-in user.
    """
    st.header("📝 Track Lead Dashboard")

    # Top navigation menu using Streamlit 'pills'
    menu = st.pills(
        "Dashboard Menu",
        ["Track Planning", "View/Edit Dashboard", "Change Password"],
        default="Track Planning",
    )

    # ==========================================
    # TAB 1: TRACK PLANNING
    # ==========================================
    if menu == "Track Planning":
        st.subheader("Track Planning")

        # --- INPUT SECTION: Core Track Information ---
        col1, col2 = st.columns(2)
        with col1:
            track_name = st.text_input("Track name")
        with col2:
            number_of_sets = st.number_input("Number of sets", min_value=1)

        col3, col4, col5 = st.columns(3)
        with col3:
            total_files = st.number_input("Files for annotation per set", min_value=1)
        with col4:
            productivity_hours = st.number_input(
                "Required productivity hours", min_value=1
            )
        with col5:
            annotation_avg_time = st.number_input(
                "Average annotation time (minutes)", min_value=1.0
            )

        # Automatically calculate daily target based on hours available and time per file
        col6, col7, col8 = st.columns(3)
        with col6:
            annotation_target = int((productivity_hours * 60) // annotation_avg_time)
            st.text_input(
                "Annotation target per person per day",
                value=str(annotation_target),
                disabled=True,
            )
        with col7:
            s1_percentage = st.number_input("S1 review percentage", min_value=1)
        with col8:
            # Determine how many files require Stage 1 Review based on the percentage provided
            s1_total_files = math.ceil((s1_percentage * total_files) / 100)
            st.text_input(
                "Files for S1 review per set", value=str(s1_total_files), disabled=True
            )

        # Target calculations for Stage 1 Review
        col9, col10, col11 = st.columns(3)
        with col9:
            s1_avg_time = st.number_input(
                "Average S1 review time (minutes)", min_value=1.0
            )
        with col10:
            s1_target = int((productivity_hours * 60) // s1_avg_time)
            st.text_input(
                "S1 review target per person per day",
                value=str(s1_target),
                disabled=True,
            )
        with col11:
            s2_percentage = st.number_input("S2 review percentage", min_value=1)
            s2_total_files = math.ceil((s2_percentage * total_files) / 100)

        # Target calculations for Stage 2 Review
        col12, col13, col14 = st.columns(3)
        with col12:
            st.text_input(
                "Files for S2 review per set", value=str(s2_total_files), disabled=True
            )
        with col13:
            s2_avg_time = st.number_input(
                "Average S2 review time (minutes)", min_value=1.0
            )
        with col14:
            s2_target = int((productivity_hours * 60) // s2_avg_time)
            st.text_input(
                "S2 review target per person per day",
                value=str(s2_target),
                disabled=True,
            )

        # --- INPUT SECTION: Timelines ---
        col15, col16 = st.columns(2)
        with col15:
            start_date = st.date_input("Start Date")
        with col16:
            end_date = st.date_input("End Date")

        # Ensure the track starts on a weekday
        start_date = next_weekday(start_date)

        # Build a continuous list of all working days between start and end date
        days = []
        d = start_date
        while d <= end_date:
            if is_weekday(d):
                days.append(d)
            d += timedelta(days=1)

        # --- TEAM SELECTION MATRIX ---
        # Fetch all employees and map them to their specific Team Leads
        employees = session.query(Employee).all()
        mappings = session.query(TeamMapping).all()
        data = []
        mapping_dict = {m.employee_email: m.teamlead_email for m in mappings}

        # Build the table data row-by-row mapping employees to their daily availability
        for emp in employees:
            row = {
                "Select": False,
                "Name": emp.name,
                "Email": emp.email,
                "Role": emp.role,
                "Set": emp.set_,
                "Lead": mapping_dict.get(emp.email, "Not Mapped"),
            }
            # Look up this employee's status for every single weekday in the timeline
            for d in days:
                record = (
                    session.query(Availability)
                    .filter(
                        Availability.employee_email == emp.email, Availability.date == d
                    )
                    .first()
                )
                row[str(d)] = record.status if record else " "
            data.append(row)

        df = pd.DataFrame(data)
        role_options = ["A", "S1", "S2"]
        set_options = ["1", "2", "3"]

        # Configure how the dataframe columns render in Streamlit's data editor
        column_config = {
            "Select": st.column_config.CheckboxColumn(
                "Select", help="Tick to include this employee"
            ),
            "Name": st.column_config.TextColumn("Name"),
            "Email": st.column_config.TextColumn("Email"),
            "Role": st.column_config.SelectboxColumn("Role", options=role_options),
            "Set": st.column_config.SelectboxColumn("Set", options=set_options),
            "Lead": st.column_config.TextColumn("Lead"),
        }
        # Add dynamic column configurations for every date mapped
        for d in days:
            column_config[str(d)] = st.column_config.TextColumn(str(d))

        # Create a container with a border to act as your 'block'
        with st.container(border=True):
            st.caption("**Choose role/set and select employees by ticking the rows**")
            st.caption(
                "Tip: First edit role/set (if needed) and click **Save Changes**. Start to **Select** employees only after saving changes."
            )

            # Information guides depending on the number of sets selected
            if number_of_sets == 1:
                st.info(
                    "Only SET1 associates will be considered from the selected list"
                )
            elif number_of_sets == 2:
                st.info(
                    "Only SET1 and SET2 associates will be considered from the selected list"
                )

            # Display the editable dataframe table. Lock columns that shouldn't be edited directly here.
            disabled_cols = [
                c for c in df.columns if c not in ("Select", "Role", "Set")
            ]
            edited_df = st.data_editor(
                df,
                hide_index=True,
                column_config=column_config,
                disabled=disabled_cols,
                width="content",
            )

            # Extract rows where the "Select" checkbox was ticked
            if "Select" in edited_df.columns:
                selects = edited_df["Select"].fillna(False).astype(bool)
            else:
                selects = pd.Series(False, index=edited_df.index)

            selected_rows = edited_df[selects]
            cols_needed = ["Email", "Name", "Role", "Set"]
            selected_employees = (
                selected_rows[cols_needed]
                .rename(
                    columns={
                        "Email": "email",
                        "Name": "name",
                        "Role": "role",
                        "Set": "set_",
                    }
                )
                .to_dict(orient="records")
            )

            # Inject custom CSS to remove borders around the form to make it look cleaner
            st.markdown(
                """
                <style>
                div[data-testid="stForm"] {
                    border: none !important;
                    box-shadow: none !important;
                    margin-top: -20px !important;
                    padding: 0 !important;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

            # Form submission to permanently update an employee's Default Role and Set in the database
            with st.form("tp_roleset_form", clear_on_submit=False):
                save_rolesets = st.form_submit_button("Save Changes", type="primary")

        if save_rolesets:
            try:
                # Group by email to avoid processing duplicates
                edit_by_email = (
                    edited_df.dropna(subset=["Email"])
                    .drop_duplicates(subset=["Email"])
                    .set_index("Email")
                )
                role_options = ["A", "S1", "S2"]
                set_options = ["1", "2", "3"]

                # Update database records
                for email, row in edit_by_email.iterrows():
                    role_val = (row.get("Role") or "").strip()
                    set_val = (row.get("Set") or "").strip()
                    emp_rec = (
                        session.query(Employee).filter(Employee.email == email).first()
                    )
                    if not emp_rec:
                        continue
                    emp_rec.role = role_val
                    emp_rec.set_ = set_val
                session.commit()
                st.rerun()  # Refresh page to show updated states
            except Exception as e:
                session.rollback()
                st.error(f"Failed to update Role/Set: {e}")

        # Inject custom CSS to resize Streamlit metrics
        st.markdown(
            """
            <style>
            div[data-testid="stMetricValue"] {
                font-size: 14px !important;
            }
            div[data-testid="stMetricLabel"] {
                font-size: 10px !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        # --- CLASSIFYING EMPLOYEES ---
        # Initialize lists to categorize selected employees by Role and by Set
        selected_annotators = []
        selected_S1s = []
        selected_S2s = []
        set1_selected_annotators = []
        set2_selected_annotators = []
        set3_selected_annotators = []
        set1_selected_s1s = []
        set2_selected_s1s = []
        set3_selected_s1s = []
        set1_selected_s2s = []
        set2_selected_s2s = []
        set3_selected_s2s = []

        # Filter out employees whose 'Set' falls outside the scope of the user's `number_of_sets` config
        if number_of_sets == 1:
            selected_employees = [
                emp for emp in selected_employees if emp.get("set_") == "1"
            ]
        elif number_of_sets == 2:
            selected_employees = [
                emp for emp in selected_employees if emp.get("set_") != "3"
            ]

        # Populate the global Role lists
        for emp in selected_employees:
            if emp["role"] == "A":
                selected_annotators.append(emp["email"])
            elif emp["role"] == "S1":
                selected_S1s.append(emp["email"])
            elif emp["role"] == "S2":
                selected_S2s.append(emp["email"])

        # Populate the granular Set/Role lists
        for emp in selected_employees:
            if emp["role"] == "A" and emp["set_"] == "1":
                set1_selected_annotators.append(emp["email"])
            elif emp["role"] == "A" and emp["set_"] == "2":
                set2_selected_annotators.append(emp["email"])
            elif emp["role"] == "A" and emp["set_"] == "3":
                set3_selected_annotators.append(emp["email"])
            elif emp["role"] == "S1" and emp["set_"] == "1":
                set1_selected_s1s.append(emp["email"])
            elif emp["role"] == "S1" and emp["set_"] == "2":
                set2_selected_s1s.append(emp["email"])
            elif emp["role"] == "S1" and emp["set_"] == "3":
                set3_selected_s1s.append(emp["email"])
            elif emp["role"] == "S2" and emp["set_"] == "1":
                set1_selected_s2s.append(emp["email"])
            elif emp["role"] == "S2" and emp["set_"] == "2":
                set2_selected_s2s.append(emp["email"])
            elif emp["role"] == "S2" and emp["set_"] == "3":
                set3_selected_s2s.append(emp["email"])

        # --- HEADCOUNT METRICS UI ---
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total headcount", len(selected_employees))
        with col2:
            st.metric("Annotators headcount", len(selected_annotators))
        with col3:
            st.metric("S1s headcount", len(selected_S1s))
        with col4:
            st.metric("S2s headcount", len(selected_S2s))

        col4, col5, col6 = st.columns(3)
        with col4:
            st.metric("Set 1 annotators headcount", len(set1_selected_annotators))
        with col5:
            st.metric("Set 1 S1s headcount", len(set1_selected_s1s))
        with col6:
            st.metric("Set 1 S2s headcount", len(set1_selected_s2s))

        col7, col8, col9 = st.columns(3)
        with col7:
            st.metric("Set 2 annotators headcount", len(set2_selected_annotators))
        with col8:
            st.metric("Set 2 S1s headcount", len(set2_selected_s1s))
        with col9:
            st.metric("Set 2 S2s headcount", len(set2_selected_s2s))

        col10, col11, col12 = st.columns(3)
        with col10:
            st.metric("Set 3 annotators headcount", len(set3_selected_annotators))
        with col11:
            st.metric("Set 3 S1s headcount", len(set3_selected_s1s))
        with col12:
            st.metric("Set 3 S2s headcount", len(set3_selected_s2s))

        # Provide an expandable section containing a DataFrame and Excel Download of final selections
        with st.expander("Selected employees"):
            download_df = pd.DataFrame(
                selected_employees, columns=["name", "email", "role", "set_"]
            )
            download_df = download_df.rename(
                columns={
                    "name": "Name",
                    "email": "Email",
                    "role": "Role",
                    "set_": "Set",
                }
            )
            st.write(download_df)

            # Use `generate_group` to format for external tracking files
            download_df["SET/ROLE"] = download_df.apply(generate_group, axis=1)
            download_df = download_df.drop(columns=["Role", "Set"])
            download_df = download_df.rename(columns={"Name": "NAME", "Email": "EMAIL"})

            excel_data = to_excel(download_df)
            st.download_button(
                label="Export As Excel",
                data=excel_data,
                file_name="set_and_role_details.xlsx",
                type="primary",
            )

        # --- ETA CALCULATOR LOGIC ---
        if st.button("Calculate ETA", type="primary"):
            # Validation 1: Check for a valid Track Name
            # .strip() removes leading/trailing spaces to ensure the user didn't just type spaces.
            if track_name.strip() == "":
                # Display an error if the name is missing and halt execution using 'return'
                st.error("Enter the track name")
                return

            # Validation 2: Chronological Date Check
            # Ensures that the selected start date logically precedes or equals the end date.
            # Python can compare datetime/date objects directly using standard mathematical operators.
            if start_date > end_date:
                # Display an error if the timeline is backwards and halt execution
                st.error("Start date cannot be after end date")
                return

            # Validation 3: Headcount / Assignment Check
            # 'if not selected_employees' checks if the list (likely from a multiselect widget) is empty.
            # We cannot calculate an Estimated Time of Arrival if no workforce is assigned to do the work.
            if not selected_employees:
                # Display an error if the roster is empty and halt execution
                st.error("Select at least one employee before calculating ETA")
                return

            # ... (If the code reaches this point, all validations have passed,
            # and the actual ETA calculation logic would proceed below)

            emp_dict = {e.email: e.email for e in employees}

            # The system calculates cascading ETAs depending on how many datasets the user declared.
            # Stage 1 needs to wait for Annotations, Stage 2 needs to wait for Stage 1.
            if number_of_sets == 1:
                # Set 1 Calculations
                calculate_eta(
                    session,
                    total_files,
                    start_date,
                    end_date,
                    annotation_target,
                    annotation_avg_time,
                    emp_dict,
                    set1_selected_annotators,
                    "Annotation",
                    "SET1",
                )
                if len(set1_selected_s1s) != 0:
                    calculate_eta(
                        session,
                        s1_total_files,
                        start_date,
                        end_date,
                        s1_target,
                        s1_avg_time,
                        emp_dict,
                        set1_selected_s1s,
                        "S1",
                        "SET1",
                    )
                if len(set1_selected_s2s) != 0:
                    calculate_eta(
                        session,
                        s2_total_files,
                        start_date,
                        end_date,
                        s2_target,
                        s2_avg_time,
                        emp_dict,
                        set1_selected_s2s,
                        "S2",
                        "SET1",
                    )

            elif number_of_sets == 2:
                # Set 1 and 2 Annotations
                calculate_eta(
                    session,
                    total_files,
                    start_date,
                    end_date,
                    annotation_target,
                    annotation_avg_time,
                    emp_dict,
                    set1_selected_annotators,
                    "Annotation",
                    "SET1",
                )
                calculate_eta(
                    session,
                    total_files,
                    start_date,
                    end_date,
                    annotation_target,
                    annotation_avg_time,
                    emp_dict,
                    set2_selected_annotators,
                    "Annotation",
                    "SET2",
                )

                # Set 1 and 2 Stage 1 Reviews
                if len(set1_selected_s1s) != 0:
                    calculate_eta(
                        session,
                        s1_total_files,
                        start_date,
                        end_date,
                        s1_target,
                        s1_avg_time,
                        emp_dict,
                        set1_selected_s1s,
                        "S1",
                        "SET1",
                    )
                    calculate_eta(
                        session,
                        s1_total_files,
                        start_date,
                        end_date,
                        s1_target,
                        s1_avg_time,
                        emp_dict,
                        set2_selected_s1s,
                        "S1",
                        "SET2",
                    )

                # Set 1 and 2 Stage 2 Reviews
                if len(set1_selected_s2s) != 0:
                    calculate_eta(
                        session,
                        s2_total_files,
                        start_date,
                        end_date,
                        s2_target,
                        s2_avg_time,
                        emp_dict,
                        set1_selected_s2s,
                        "S2",
                        "SET1",
                    )
                    calculate_eta(
                        session,
                        s2_total_files,
                        start_date,
                        end_date,
                        s2_target,
                        s2_avg_time,
                        emp_dict,
                        set2_selected_s2s,
                        "S2",
                        "SET2",
                    )

            elif number_of_sets == 3:
                # Sets 1, 2, and 3 Annotations
                calculate_eta(
                    session,
                    total_files,
                    start_date,
                    end_date,
                    annotation_target,
                    annotation_avg_time,
                    emp_dict,
                    set1_selected_annotators,
                    "Annotation",
                    "SET1",
                )
                calculate_eta(
                    session,
                    total_files,
                    start_date,
                    end_date,
                    annotation_target,
                    annotation_avg_time,
                    emp_dict,
                    set2_selected_annotators,
                    "Annotation",
                    "SET2",
                )
                calculate_eta(
                    session,
                    total_files,
                    start_date,
                    end_date,
                    annotation_target,
                    annotation_avg_time,
                    emp_dict,
                    set3_selected_annotators,
                    "Annotation",
                    "SET3",
                )

                # Sets 1, 2, and 3 Stage 1 Reviews
                if len(set1_selected_s1s) != 0:
                    calculate_eta(
                        session,
                        s1_total_files,
                        start_date,
                        end_date,
                        s1_target,
                        s1_avg_time,
                        emp_dict,
                        set1_selected_s1s,
                        "S1",
                        "SET1",
                    )
                    calculate_eta(
                        session,
                        s1_total_files,
                        start_date,
                        end_date,
                        s1_target,
                        s1_avg_time,
                        emp_dict,
                        set2_selected_s1s,
                        "S1",
                        "SET2",
                    )
                    calculate_eta(
                        session,
                        s1_total_files,
                        start_date,
                        end_date,
                        s1_target,
                        s1_avg_time,
                        emp_dict,
                        set3_selected_s1s,
                        "S1",
                        "SET3",
                    )

                # Sets 1, 2, and 3 Stage 2 Reviews
                if len(set1_selected_s2s) != 0:
                    calculate_eta(
                        session,
                        s2_total_files,
                        start_date,
                        end_date,
                        s2_target,
                        s2_avg_time,
                        emp_dict,
                        set1_selected_s2s,
                        "S2",
                        "SET1",
                    )
                    calculate_eta(
                        session,
                        s2_total_files,
                        start_date,
                        end_date,
                        s2_target,
                        s2_avg_time,
                        emp_dict,
                        set2_selected_s2s,
                        "S2",
                        "SET2",
                    )
                    calculate_eta(
                        session,
                        s2_total_files,
                        start_date,
                        end_date,
                        s2_target,
                        s2_avg_time,
                        emp_dict,
                        set3_selected_s2s,
                        "S2",
                        "SET3",
                    )

        # Verify if a track configuration with this Name & Start Date combination already exists.
        existing_track = (
            session.query(Track)
            .filter(Track.track_name == track_name, Track.start_date == start_date)
            .first()
        )
        if existing_track:
            st.warning(
                "A track with the same **Track Name** and **Start Date** already exists. "
                "If you click **Save Details**, it will **overwrite** that existing track's details.",
                icon="⚠️",
            )

        st.divider()

        # --- SAVE & COMMIT LOGIC ---
        if st.button("Save Details", type="primary"):
            # Enforce that ETAs were actually calculated.
            # Then use the ETA dates to block out employee calendars in the database using `change_availability_status`
            if number_of_sets == 1:
                if "SET1_Annotation_ETA" not in st.session_state:
                    st.error("Please calculate annotation ETA for required sets")
                    st.stop()
                change_availability_status(
                    set1_selected_annotators,
                    start_date,
                    st.session_state["SET1_Annotation_ETA"],
                    track_name,
                )
                if "SET1_S1_ETA" in st.session_state:
                    change_availability_status(
                        set1_selected_s1s,
                        start_date,
                        st.session_state["SET1_S1_ETA"],
                        track_name,
                    )
                if "SET1_S2_ETA" in st.session_state:
                    change_availability_status(
                        set1_selected_s2s,
                        start_date,
                        st.session_state["SET1_S2_ETA"],
                        track_name,
                    )

            elif number_of_sets == 2:
                if (
                    "SET1_Annotation_ETA" not in st.session_state
                    or "SET2_Annotation_ETA" not in st.session_state
                ):
                    st.error("Please calculate annotation ETA for required sets")
                    st.stop()
                change_availability_status(
                    set1_selected_annotators,
                    start_date,
                    st.session_state["SET1_Annotation_ETA"],
                    track_name,
                )
                change_availability_status(
                    set2_selected_annotators,
                    start_date,
                    st.session_state["SET2_Annotation_ETA"],
                    track_name,
                )
                if (
                    "SET1_S1_ETA" in st.session_state
                    and "SET2_S1_ETA" in st.session_state
                ):
                    change_availability_status(
                        set1_selected_s1s,
                        start_date,
                        st.session_state["SET1_S1_ETA"],
                        track_name,
                    )
                    change_availability_status(
                        set2_selected_s1s,
                        start_date,
                        st.session_state["SET2_S1_ETA"],
                        track_name,
                    )
                if (
                    "SET1_S2_ETA" in st.session_state
                    and "SET2_S2_ETA" in st.session_state
                ):
                    change_availability_status(
                        set1_selected_s2s,
                        start_date,
                        st.session_state["SET1_S2_ETA"],
                        track_name,
                    )
                    change_availability_status(
                        set2_selected_s2s,
                        start_date,
                        st.session_state["SET2_S2_ETA"],
                        track_name,
                    )

            elif number_of_sets == 3:
                if (
                    "SET1_Annotation_ETA" not in st.session_state
                    or "SET2_Annotation_ETA" not in st.session_state
                    or "SET3_Annotation_ETA" not in st.session_state
                ):
                    st.error("Please calculate annotation ETA for required sets")
                    st.stop()
                change_availability_status(
                    set1_selected_annotators,
                    start_date,
                    st.session_state["SET1_Annotation_ETA"],
                    track_name,
                )
                change_availability_status(
                    set2_selected_annotators,
                    start_date,
                    st.session_state["SET2_Annotation_ETA"],
                    track_name,
                )
                change_availability_status(
                    set3_selected_annotators,
                    start_date,
                    st.session_state["SET3_Annotation_ETA"],
                    track_name,
                )
                if (
                    "SET1_S1_ETA" in st.session_state
                    and "SET2_S1_ETA" in st.session_state
                    and "SET3_S1_ETA" in st.session_state
                ):
                    change_availability_status(
                        set1_selected_s1s,
                        start_date,
                        st.session_state["SET1_S1_ETA"],
                        track_name,
                    )
                    change_availability_status(
                        set2_selected_s1s,
                        start_date,
                        st.session_state["SET2_S1_ETA"],
                        track_name,
                    )
                    change_availability_status(
                        set3_selected_s1s,
                        start_date,
                        st.session_state["SET3_S1_ETA"],
                        track_name,
                    )
                if (
                    "SET1_S2_ETA" in st.session_state
                    and "SET2_S2_ETA" in st.session_state
                    and "SET3_S2_ETA" in st.session_state
                ):
                    change_availability_status(
                        set1_selected_s2s,
                        start_date,
                        st.session_state["SET1_S2_ETA"],
                        track_name,
                    )
                    change_availability_status(
                        set2_selected_s2s,
                        start_date,
                        st.session_state["SET2_S2_ETA"],
                        track_name,
                    )
                    change_availability_status(
                        set3_selected_s2s,
                        start_date,
                        st.session_state["SET3_S2_ETA"],
                        track_name,
                    )

            # Safely fetch all dates from session state and construct display strings
            # Set 1 Annotations
            set1_annotation_completion_date = st.session_state.get(
                "SET1_Annotation_ETA", None
            )
            set1_annotation_duration = st.session_state.get(
                "SET1_Annotation_Duration", None
            )
            set1_annotation_eta = (
                f"{set1_annotation_completion_date} [{set1_annotation_duration}]"
                if (
                    set1_annotation_completion_date is not None
                    and set1_annotation_duration is not None
                )
                else None
            )

            # Set 2 Annotations
            set2_annotation_completion_date = st.session_state.get(
                "SET2_Annotation_ETA", None
            )
            set2_annotation_duration = st.session_state.get(
                "SET2_Annotation_Duration", None
            )
            set2_annotation_eta = (
                f"{set2_annotation_completion_date} [{set2_annotation_duration}]"
                if (
                    set2_annotation_completion_date is not None
                    and set2_annotation_duration is not None
                )
                else None
            )

            # Set 3 Annotations
            set3_annotation_completion_date = st.session_state.get(
                "SET3_Annotation_ETA", None
            )
            set3_annotation_duration = st.session_state.get(
                "SET3_Annotation_Duration", None
            )
            set3_annotation_eta = (
                f"{set3_annotation_completion_date} [{set3_annotation_duration}]"
                if (
                    set3_annotation_completion_date is not None
                    and set3_annotation_duration is not None
                )
                else None
            )

            # Set 1 S1 Reviews
            set1_s1_completion_date = st.session_state.get("SET1_S1_ETA", None)
            set1_s1_duration = st.session_state.get("SET1_S1_Duration", None)
            set1_s1_eta = (
                f"{set1_s1_completion_date} [{set1_s1_duration}]"
                if (
                    set1_s1_completion_date is not None and set1_s1_duration is not None
                )
                else None
            )

            # Set 2 S1 Reviews
            set2_s1_completion_date = st.session_state.get("SET2_S1_ETA", None)
            set2_s1_duration = st.session_state.get("SET2_S1_Duration", None)
            set2_s1_eta = (
                f"{set2_s1_completion_date} [{set2_s1_duration}]"
                if (
                    set2_s1_completion_date is not None and set2_s1_duration is not None
                )
                else None
            )

            # Set 3 S1 Reviews
            set3_s1_completion_date = st.session_state.get("SET3_S1_ETA", None)
            set3_s1_duration = st.session_state.get("SET3_S1_Duration", None)
            set3_s1_eta = (
                f"{set3_s1_completion_date} [{set3_s1_duration}]"
                if (
                    set3_s1_completion_date is not None and set3_s1_duration is not None
                )
                else None
            )

            # Set 1 S2 Reviews
            set1_s2_completion_date = st.session_state.get("SET1_S2_ETA", None)
            set1_s2_duration = st.session_state.get("SET1_S2_Duration", None)
            set1_s2_eta = (
                f"{set1_s2_completion_date} [{set1_s2_duration}]"
                if (
                    set1_s2_completion_date is not None and set1_s2_duration is not None
                )
                else None
            )

            # Set 2 S2 Reviews
            set2_s2_completion_date = st.session_state.get("SET2_S2_ETA", None)
            set2_s2_duration = st.session_state.get("SET2_S2_Duration", None)
            set2_s2_eta = (
                f"{set2_s2_completion_date} [{set2_s2_duration}]"
                if (
                    set2_s2_completion_date is not None and set2_s2_duration is not None
                )
                else None
            )

            # Set 3 S2 Reviews
            set3_s2_completion_date = st.session_state.get("SET3_S2_ETA", None)
            set3_s2_duration = st.session_state.get("SET3_S2_Duration", None)
            set3_s2_eta = (
                f"{set3_s2_completion_date} [{set3_s2_duration}]"
                if (
                    set3_s2_completion_date is not None and set3_s2_duration is not None
                )
                else None
            )

            # The Final track completion ETA is the latest possible date among all activated stages
            if (
                set1_s2_completion_date is not None
                or set2_s2_completion_date is not None
                or set3_s2_completion_date is not None
            ):
                completion_eta = max(
                    [
                        d
                        for d in [
                            set1_s2_completion_date,
                            set2_s2_completion_date,
                            set3_s2_completion_date,
                        ]
                        if d is not None
                    ],
                    default=None,
                )
            elif (
                set1_s1_completion_date is not None
                or set2_s1_completion_date is not None
                or set3_s1_completion_date is not None
            ):
                completion_eta = max(
                    [
                        d
                        for d in [
                            set1_s1_completion_date,
                            set2_s1_completion_date,
                            set3_s1_completion_date,
                        ]
                        if d is not None
                    ],
                    default=None,
                )
            else:
                completion_eta = max(
                    [
                        d
                        for d in [
                            set1_annotation_completion_date,
                            set2_annotation_completion_date,
                            set3_annotation_completion_date,
                        ]
                        if d is not None
                    ],
                    default=None,
                )

            # Bundle all the calculated data into a dictionary payload matching the ORM Model
            payload = dict(
                track_lead=str(user.email),
                number_of_sets=number_of_sets,
                annotation_total_files=f"{total_files} * {number_of_sets} = {total_files * number_of_sets}",
                annotation_avg_time=annotation_avg_time,
                s1_total_files=f"{s1_total_files} * {number_of_sets} = {s1_total_files * number_of_sets}",
                s1_avg_time=s1_avg_time,
                s2_total_files=f"{s2_total_files} * {number_of_sets} = {s2_total_files * number_of_sets}",
                s2_avg_time=s2_avg_time,
                total_headcount=len(selected_employees),
                employees=repr(
                    selected_employees
                ),  # Represents the dictionary safely as a literal Python string
                set1_annotators_headcount=len(set1_selected_annotators),
                set2_annotators_headcount=len(set2_selected_annotators),
                set3_annotators_headcount=len(set3_selected_annotators),
                set1_s1_headcount=len(set1_selected_s1s),
                set2_s1_headcount=len(set2_selected_s1s),
                set3_s1_headcount=len(set3_selected_s1s),
                set1_s2_headcount=len(set1_selected_s2s),
                set2_s2_headcount=len(set2_selected_s2s),
                set3_s2_headcount=len(set3_selected_s2s),
                set1_annotation_eta=set1_annotation_eta,
                set2_annotation_eta=set2_annotation_eta,
                set3_annotation_eta=set3_annotation_eta,
                set1_s1_eta=set1_s1_eta,
                set2_s1_eta=set2_s1_eta,
                set3_s1_eta=set3_s1_eta,
                set1_s2_eta=set1_s2_eta,
                set2_s2_eta=set2_s2_eta,
                set3_s2_eta=set3_s2_eta,
                completion_eta=completion_eta,
            )

            # Save to Database: Update if exists, or insert new
            if existing_track:
                for k, v in payload.items():
                    setattr(existing_track, k, v)
                session.commit()
            else:
                track = Track(start_date=start_date, track_name=track_name, **payload)
                session.add(track)
                session.commit()
            st.success("Track details saved successfully")

    # ==========================================
    # TAB 2: VIEW/EDIT DASHBOARD
    # ==========================================
    elif menu == "View/Edit Dashboard":
        st.subheader("View/Edit Dashboard")

        # Initialize internal state to track user's current search/selection
        if "ved_track_name" not in st.session_state:
            st.session_state.ved_track_name = None
        if "ved_start_date" not in st.session_state:
            st.session_state.ved_start_date = None
        if "ved_loaded" not in st.session_state:
            st.session_state.ved_loaded = False

        # Fetch a list of unique track names from the DB to populate the search dropdown
        track_names = [
            r[0]
            for r in session.query(Track.track_name)
            .distinct()
            .order_by(Track.track_name)
            .all()
        ]

        initial_track_index = 0
        if st.session_state.ved_track_name in track_names:
            initial_track_index = track_names.index(st.session_state.ved_track_name)

        st.selectbox(
            "Track Name",
            options=track_names,
            index=initial_track_index,
            key="ved_track_name",
            on_change=_on_track_change,  # Resets loading state if changed
        )

        # A single track name might be used across multiple start dates. Find all associated start dates.
        start_dates_for_track = []
        if st.session_state.ved_track_name:
            start_dates_for_track = [
                r[0]
                for r in session.query(Track.start_date)
                .filter(Track.track_name == st.session_state.ved_track_name)
                .order_by(Track.start_date.desc())
                .all()
            ]

        if start_dates_for_track:
            initial_date_index = 0
            if st.session_state.ved_start_date in start_dates_for_track:
                initial_date_index = start_dates_for_track.index(
                    st.session_state.ved_start_date
                )
            st.selectbox(
                "Start Date",
                options=start_dates_for_track,
                index=initial_date_index,
                format_func=lambda d: d.isoformat(),
                key="ved_start_date",
                on_change=_on_start_change,
            )
        else:
            st.session_state.ved_start_date = None

        # UI rendering for search button
        colL, colR = st.columns([1, 1])
        with colL:
            load_clicked = st.button(
                "Search",
                disabled=not (
                    st.session_state.ved_track_name and st.session_state.ved_start_date
                ),
                key="ved_load_btn",
                type="primary",
            )

        if load_clicked:
            st.session_state.ved_loaded = True

        # Only proceed to render the full track details if user successfully searched
        if not st.session_state.ved_loaded:
            st.stop()

        # Retrieve the selected track's data row from the database
        track = (
            session.query(Track)
            .filter(
                Track.track_name == st.session_state.ved_track_name,
                Track.start_date == st.session_state.ved_start_date,
            )
            .first()
        )
        if not track:
            st.info("Select the track name")
            st.stop()

        st.markdown(
            """
            <style>
            div[data-testid="stMetricValue"] {
                font-size: 14px !important;
            }
            div[data-testid="stMetricLabel"] {
                font-size: 10px !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        # --- RENDER SAVED METRICS ---
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Track lead", track.track_lead.replace("@", "@\u200B"))
        with c2:
            st.metric("Number of sets", track.number_of_sets)
        with c3:
            st.metric("Total files for annotation", track.annotation_total_files)

        c4, c5, c6 = st.columns(3)
        with c4:
            st.metric("Average annotation time", f"{track.annotation_avg_time} minutes")
        with c5:
            st.metric("Total files for S1 review", track.s1_total_files)
        with c6:
            st.metric("Average S1 review time", f"{track.s1_avg_time} minutes")

        c7, c8, c9 = st.columns(3)
        with c7:
            st.metric("Total files for S2 review", track.s2_total_files)
        with c8:
            st.metric("Average S2 review time", f"{track.s2_avg_time} minutes")
        with c9:
            st.metric("Track completion ETA", track.completion_eta.isoformat())

        c10, c11, c12 = st.columns(3)
        with c10:
            st.metric("SET1 annotation ETA", track.set1_annotation_eta)
        with c11:
            st.metric("SET2 annotation ETA", track.set2_annotation_eta)
        with c12:
            st.metric("SET3 annotation ETA", track.set3_annotation_eta)

        c13, c14, c15 = st.columns(3)
        with c13:
            st.metric("SET1 S1 review ETA", track.set1_s1_eta)
        with c14:
            st.metric("SET2 S1 review ETA", track.set2_s1_eta)
        with c15:
            st.metric("SET3 S1 review ETA", track.set3_s1_eta)

        c16, c17, c18 = st.columns(3)
        with c16:
            st.metric("SET1 S2 review ETA", track.set1_s2_eta)
        with c17:
            st.metric("SET2 S2 review ETA", track.set2_s2_eta)
        with c18:
            st.metric("SET3 S2 review ETA", track.set3_s2_eta)

        st.divider()

        # Safely evaluate the stored Python literal string `track.employees` back into a List of Dicts
        employee_details = track.employees
        employee_details = ast.literal_eval(employee_details)
        employee_emails = []
        for emp in employee_details:
            employee_emails.append(emp["email"])

        emp_rows = (
            session.query(Employee).filter(Employee.email.in_(employee_emails)).all()
        )

        # Calculate exactly which days fall between the track's Start Date and Completion Date
        days = []
        d = track.start_date
        while d <= track.completion_eta:
            if is_weekday(d):
                days.append(d)
            d += timedelta(days=1)

        if not days:
            st.info("No weekdays between the selected start and completion dates")
            st.stop()

        # Fetch historical availability matching these exact employees and dates from the database
        av_rows = (
            session.query(Availability)
            .filter(
                Availability.employee_email.in_(employee_emails),
                Availability.date >= days[0],
                Availability.date <= days[-1],
            )
            .all()
        )
        # Create a fast lookup dictionary using a tuple of (email, date) as the key
        avail_map = {(a.employee_email, a.date): a.status for a in av_rows}

        # Reconstruct the Dataframe to display it in the Data Editor
        data = []
        for email in employee_emails:
            name = ""
            role = ""
            sets = ""
            for emp in employee_details:
                if emp["email"] == email:
                    name = emp["name"]
                    role = emp["role"]
                    sets = emp["set_"]
                    break
            row = {"Name": name, "Email": email, "Role": role, "Set": sets}

            # Use lookup dict to map daily availability statuses
            for d in days:
                row[str(d)] = avail_map.get((email, d), " ")
            data.append(row)

        df = pd.DataFrame(data)

        # Set up dynamic Column Configurations to lock text fields
        db_status_values = set()
        for d in days:
            db_status_values.update(df[str(d)].unique())

        column_config = {
            "Name": st.column_config.TextColumn("Name", disabled=True),
            "Email": st.column_config.TextColumn("Email", disabled=True),
            "Role": st.column_config.TextColumn("Role", disabled=True),
            "Set": st.column_config.TextColumn("Set", disabled=True),
        }
        for d in days:
            column_config[str(d)] = st.column_config.TextColumn(
                str(d), width="content", disabled=True
            )

        st.caption(
            f"Showing employees availability status for **{track.track_name}** track "
            f"from **{track.start_date}** to **{track.completion_eta}** "
        )

        # Display as uneditable data frame
        edited_df = st.data_editor(
            df,
            hide_index=True,
            column_config=column_config,
            width="content",
        )
        st.divider()

        # --- EDIT AVAILABILITY STATUS BLOCK ---
        with st.expander("Change Availability Status"):
            # Enforce authorization: only the user who created the track can edit it
            if user.email != track.track_lead:
                st.error("You do not have permission to perform this operation")
                return

            st.caption("Change availability status of the mapped employees")
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start Date")
            with col2:
                end_date = st.date_input("End Date")

            # Date limit checking against track's lifetime constraints
            if end_date > track.completion_eta:
                st.error("End date cannot be after the track completion ETA")
                return
            if start_date > end_date:
                st.error("Start date cannot be after end date")
                return
            if start_date.weekday() >= 5 or end_date.weekday() >= 5:
                st.error("Start date and End date should be weekdays")
                return

            # Multi-select allows updating several employees at once
            selected_emails = st.multiselect("Select Employees", employee_emails)
            availability_options = [
                "Available",
                "Planned Leave",
                "Half Day Leave",
                "Sick Leave",
                "Emergency Leave",
                "Comp Off",
                f"{track.track_name}",
            ]
            selected_status = st.selectbox("Availability Status", availability_options)
            update_clicked = st.button("Save Changes", type="primary")

            if update_clicked:
                if not selected_emails:
                    st.error("Please select at least one employee")
                    st.stop()
                    return
                # Iterate through all selected employees and date ranges to modify the Availability Table
                for emp_email in selected_emails:
                    delta = end_date - start_date
                    for i in range(delta.days + 1):
                        d = start_date + timedelta(days=i)

                        # Never book status changes onto weekends
                        if d.weekday() >= 5:
                            continue

                        record = (
                            session.query(Availability)
                            .filter(
                                Availability.employee_email == emp_email,
                                Availability.date == d,
                            )
                            .first()
                        )
                        # Overwrite existing record, or insert new if user wasn't tracked
                        if record:
                            record.status = selected_status
                        else:
                            new_record = Availability(
                                employee_email=emp_email, date=d, status=selected_status
                            )
                            session.add(new_record)
                session.commit()
                st.success(f"Updated successfully")
                time.sleep(0.5)
                st.rerun()  # Refresh app to update UI tables visually

    # ==========================================
    # TAB 3: CHANGE PASSWORD
    # ==========================================
    elif menu == "Change Password":
        st.subheader("Change Password")
        old_password = st.text_input("Enter old password", type="password")
        new_password = st.text_input("Enter new password", type="password")
        confirm_password = st.text_input("Confirm new password", type="password")

        if st.button("Update Password", type="primary"):
            # Check for standard typos
            if new_password != confirm_password:
                st.error("New password & Confirm password do not match")
            else:
                usr = (
                    session.query(User)
                    .filter(User.email == user.email, User.role == "tracklead")
                    .first()
                )
                if not usr:
                    st.error("User not found in database")
                elif usr.password != old_password:
                    st.error("Old password is incorrect")
                elif usr.password == new_password:
                    st.error("New password cannot be same as old password")
                else:
                    # Overwrite and save new password (in production this should be hashed)
                    usr.password = new_password
                    session.commit()
                    st.success("Password updated successfully")
