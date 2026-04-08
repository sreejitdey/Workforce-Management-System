# **📚 Workforce Management System**

## **1. Executive Summary**

The Workforce Management System is a comprehensive, multi-tenant web application designed to streamline resource allocation, track daily workforce availability, and mathematically forecast project Estimated Times of Arrival (ETAs). Built with a role-based architecture, the system enforces strict data privacy across four management tiers (Administrators, Technical Program Managers, Team Leads, and Track Leads), ensuring a secure and efficient operational lifecycle.

## **2. Project Architecture & Directory Structure**

The Workforce Management System follows a modular, scalable architecture designed to separate concerns between the user interface, routing, and data management. This ensures secure handling of role-based access and seamless integration with the PostgreSQL backend.

The repository is organized as follows:

**WORKFORCE-MANAGEMENT-SYSTEM/**

**│**
**├── .streamlit/**
**│ └── config.toml** *\#Application-level configuration*
**│**
**├── data/**
**│ └── data.db** *\#Local SQLite database for localhost*
**│**
**├── database/**
**│ ├── \_\_init\_\_.py**
**│ ├── database.py** *\#Database connection engine and session management*
**│ └── models.py** *\#ORM models defining the database schema and relationships*
**│**
**├── views/**
**│ ├── \_\_init\_\_.py**
**│ ├── admin_page.py** *\#Interface and logic for System Administrators*
**│ ├── teamlead_page.py** *\#Interface for Language Team Leads*
**│ ├── tpm_page.py** *\#Interface for Technical Program Managers*
**│ └── tracklead_page.py** *\#Interface for Track Lead for ETA planning*
**│**
**├── app.py** *\#Main application entry point and routing handler*
**└── requirements.txt** *\#Project dependencies and library versions*

## **3. Environment & Core Dependencies**

The application relies on a robust stack of Python libraries, specified in the requirements.txt file, to handle everything from frontend rendering to database connectivity and data processing.

- **Frontend Framework:** streamlit is the core framework used to build the interactive web application interfaces.

- **Authentication & State:** streamlit_cookies_manager is utilized to handle secure session management and authentication cookies across the role-based views.

- **Database Management:**

  - **sqlalchemy:** Serves as the Object Relational Mapper (ORM), allowing the application to interact with the database using Python objects rather than raw SQL strings.

  - **psycopg2-binary:** The PostgreSQL database adapter for Python, ensuring high-performance communication between the application and the production backend.

- **Data Processing:** pandas and openpyxl are included for complex data manipulation, aggregation, and likely the importing/exporting of Excel-based workforce reports.

## **4. Data Architecture & Schema (models.py)**

The system relies on a relational database structured via SQLAlchemy. The schema is normalized to separate system access control (User) from operational workforce tracking (Employee), while maintaining strict hierarchical and transactional integrity.

### **4.1. System Configuration & Access**

Tables dedicated to application setup and user access control.

| **Table Name**   | **Purpose**                                                                                                | **Key Constraints & Rules**                                                                                                                       |
|------------------|------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------|
| **SystemConfig** | Stores global, key-value configuration flags (e.g., verifying if the initial admin setup is complete).     | key serves as the primary key.                                                                                                                    |
| **User**         | Manages system access, authentication, and Role-Based Access Control (RBAC) (e.g., Admin, TPM, Team Lead). | A composite unique constraint (email + role) ensures an email cannot hold the same role twice, though one user may hold multiple different roles. |

### **4.2. Workforce & Hierarchy**

Tables defining the structural organization of the staff.

| **Table Name**  | **Purpose**                                                                                                                 | **Key Constraints & Rules**                                                                                            |
|-----------------|-----------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| **Employee**    | Tracks the actual workforce associates. Stores operational roles (e.g., Annotator, Stage 1, Stage 2) and assigned datasets. | email is strictly unique; no two employees can share an email.                                                         |
| **TeamMapping** | Defines the reporting hierarchy linking TPMs to Team Leads, and Team Leads to Associates.                                   | employee_email is unique, enforcing a strict top-down structure where an associate can only have *one* direct manager. |

### **4.3. Operations & Project Tracking**

Tables handling dynamic daily inputs and complex mathematical project blueprints.

| **Table Name**   | **Purpose**                                                                                                                                     | **Key Constraints & Rules**                                                                                                                                              |
|------------------|-------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Availability** | A transactional table tracking daily employee statuses (e.g., Available, Planned Leave, or working on a specific Track).                        | A composite unique constraint (employee_email + date) ensures only one status can exist per employee per day, preventing duplicate hour calculations.                    |
| **Track**        | The central blueprint for project management. Stores expected file totals, average processing times, headcount breakdowns, and calculated ETAs. | Highly detailed structure storing headcounts partitioned by Set (1, 2, 3) and Stage (Annotation, S1, S2). Calculates a definitive completion_eta for the entire project. |

## **5. Database Configuration & Engine (database.py)**

The application employs an environment-aware database configuration strategy. This ensures seamless transitions between local development environments and production cloud servers (such as Render or Heroku) without requiring code modifications.

### **5.1. Dynamic Connection Routing**

- **Production Environment:** The system first attempts to locate a DATABASE_URL environment variable. If found, it establishes a high-performance connection to an external SQL database (e.g., PostgreSQL).

- **Cloud Compatibility Patch:** To maintain compatibility with older cloud hosting environments (which often provide legacy postgres:// URIs), the module automatically intercepts and translates the dialect to postgresql://, satisfying modern SQLAlchemy 1.4+ requirements.

- **Local Development Fallback:** If no environment variable is present, the system defaults to a local SQLite database (data.db). It automatically configures check_same_thread: False to allow Streamlit\'s multi-threaded environment to interact safely with the SQLite file.

### **5.2. Session Management**

The module exports a configured SessionLocal factory. This allows the application to generate isolated database sessions for querying, adding, modifying, and committing data transactions securely.

## **6. Application Entry Point & Security Gateway (app.py)**

The app.py script serves as the central nervous system and primary security gateway for the Workforce Management System. It is the first file executed when the application boots up. It is responsible for initializing the system, rendering the multi-tenant login interface, managing encrypted browser sessions, and strictly routing authenticated users to their designated operational dashboards.

### **6.1. System Initialization & Database Seeding**

Before rendering any UI elements, the script performs critical background operations to ensure the application environment is secure and ready for use:

- **Schema Generation:** It executes Base.metadata.create_all(engine). This safely inspects the connected SQL database and automatically builds any missing tables defined in models.py without dropping or overwriting existing operational data.

- **Administrator Seeding:** To prevent system lockouts on a fresh deployment, the create_default_admin function runs immediately. It checks the system_config table for a specific initialization flag. If this is the very first time the app is running, it automatically generates a default \"Root Admin\" account (admin@tcs.com), logs the action, and permanently sets the initialization flag to prevent redundant creations in the future.

### **6.2. Session State & Cookie Persistence**

To provide a modern user experience, the system utilizes both Streamlit\'s native session state and an encrypted cookie manager.

- **Streamlit Session State:** Variables such as the active user object and the selected_portal are stored in memory to prevent the user from being logged out during normal UI interactions and page reruns.

- **Encrypted Cookies:** The streamlit_cookies_manager securely encrypts and stores the user\'s email and role in their browser cache. Upon revisiting the application, the system automatically decrypts the payload, verifies the user in the database, and bypasses the login screen entirely.

### **6.3. Dashboard Routing & The Logout Mechanism**

Once a user is successfully authenticated (either via manual login or cookie retrieval), the script completely hides the Login Flow and engages the Dashboard Flow.

**Persistent Sidebar & Welcome UI:** Regardless of which role the user holds, the application generates a persistent sidebar containing a personalized \"Welcome\" message (fetching their human-readable name from the database) and a prominent Logout button.

**The Logout Execution:** When a user clicks the \"⏻ Logout\" button, the system performs a complete session purge to secure the application:

1.  **Cookie Clearing:** It forcefully overwrites the encrypted browser cookies with empty strings, permanently wiping the persistent auto-login data from the user\'s local machine.

2.  **State Purging:** It resets st.session_state.user to None, destroying the active session context in the server memory.

3.  **Forced Reroute:** It triggers an immediate st.rerun(), which forces the application to execute from the top. Because the session state is now empty, the script automatically routes the user back to the primary, unauthenticated Login Menu.

**Strict Dashboard Routing:** After rendering the persistent sidebar, the main application body acts as a secure traffic controller. It checks the user\'s validated role and routes them directly to the corresponding module view (e.g., executing admin_dashboard(user) or tracklead_dashboard(user)). If, by some unexpected error, a user reaches this stage without a valid role matching their portal, the system throws a final \"Access Denied\" error and halts execution.

## **7. Authentication & Role-Based Access Control (app.py)**

The system enforces strict security protocols during the login phase to ensure data privacy and hierarchical integrity.

### **7.1. The Login Flow**

1.  **Portal Selection:** Unauthenticated users are presented with a sidebar menu to select their specific role portal (Admin, TPM, Team Lead, Track Lead).

2.  **Credential Verification:** The login_user function executes a strict, three-factor database query. It verifies not only the user\'s email and password but also confirms that their assigned database role matches the specific portal they are attempting to access.

3.  **Access Denial:** If a user attempts to log into a portal not assigned to them (e.g., a Team Lead trying to access the TPM portal), the system will reject the login, even if their password is correct.

### **7.2. Dashboard Routing**

Once successfully authenticated, the main application loop routes the user to their designated view module (e.g., admin_dashboard(), tpm_dashboard()). A secure logout mechanism is provided, which actively clears the session state and purges the encrypted browser cookies.

### **7.3. User Portals & Access Gateways**

The application utilizes a multi-tenant login interface. To ensure users are directed strictly to the tools relevant to their operational duties, they must select their designated role portal from the sidebar menu before entering their credentials. Each portal serves as a secure gateway to a dedicated, role-specific dashboard:

- **🛡️ Admin Login (admin):** The gateway for System Administrators. This portal authenticates the user and routes them to the admin_dashboard. It is reserved for top-level system management, such as provisioning new user accounts, configuring access controls, and overseeing the overarching application infrastructure.

- **👩🏻‍💻 TPM Login (tpm):** The gateway for Technical Program Managers. This portal routes to the tpm_dashboard. It provides access to high-level project management tools, allowing TPMs to handle complex ETA planning, oversee track blueprints, and define the hierarchical mappings between managers and the workforce.

- **👨‍👨 Team Lead Login (teamlead):** The gateway for Team Leads. Accessing this portal routes the user to the teamlead_dashboard. This interface is designed for day-to-day operational management, enabling Team Leads to monitor their direct reports, log and review daily associate availability, and track active shift resources.

- **📝 Track Lead Login (tracklead):** The gateway for Track Leads. This portal routes to the tracklead_dashboard. It provides specialized tools for overseeing specific project tracks, managing file allocations, balancing headcounts across different datasets/stages, and monitoring calculated stage-by-stage completion ETAs.

## **8. Admin Portal Dashboard (admin_page.py)**

The Admin Portal serves as the central command center for the Workforce Management System. It provides system administrators with specialized tools to provision access, structure the organizational hierarchy, and manage all core data tables.

The dashboard is divided into five primary functional tabs:

### **8.1. Create User (Access Provisioning)**

This tab is designed to provision application access for management personnel.

- **Supported Roles:** Technical Project Manager (TPM), Language Team Lead, and Track Lead.

- **Dual-Entry System:** When a user is created here, the system performs a dual-entry operation.

  1.  It creates the login credentials in the "User" table.

  2.  It automatically generates a mirrored profile in the "Employee" table to ensure they can be mapped in the system hierarchy. These profiles are assigned default operational values (Role: S2, Set: 1) and a system tag of "login_user" to differentiate them from standard workforce associates.

- **Role-Conflict Security:** The system enforces strict business logic regarding role assignment. While a single email address can hold multiple roles, it **cannot** act as both a TPM and a Team Lead simultaneously. An individual can, however, be a TPM + Track Lead, or a Team Lead + Track Lead.

### **8.2. Add Associate (Workforce Provisioning)**

This tab handles the onboarding of the standard production workforce (who do not require system login access).

- **Input Data:** Administrators input the associate\'s Name, Email, Role (A for Annotator, S1, S2), and Dataset assignment (Set 1, 2, or 3).

- **Database Tagging:** Associates are added strictly to the "Employee" table with an internal tag set to "associate".

- **Data Integrity:** The system ensures that every email address entered in the employee table is absolutely unique to prevent data corruption during mapping and hours tracking.

### **8.3. Map Associates (Hierarchy Management)**

This module builds the operational reporting structure, enabling the filtering logic used in the downstream dashboards. It uses a strict top-down linking approach preventing double-mapping (an associate or lead can only report to one manager). All established relationships and hierarchical links generated in this module are permanently saved to the "TeamMapping" database table.

- **TPM ⇄ Language Team Lead:** Administrators select a single TPM from a dropdown and map multiple Team Leads to them. The system filters the options so that regular "associates" and already-mapped leads cannot be selected.

- **Language Team Lead ⇄ Associates:** Administrators select a single Team Lead and map multiple workforce associates to them. The system filters out "login_users" (managers) to ensure only valid operational workers are placed at the bottom of the hierarchy.

### **8.4. View/Edit Dashboard (Data Management)**

A comprehensive suite of interactive data grids allowing the administrator to perform CRUD (Create, Read, Update, Delete) operations directly on the database.

Following are the core functionalities & business logic:

- **User Details:** Displays all login accounts. Admins can permanently delete users. Deletion triggers a cascading wipe, removing the user from the "Employee" table, erasing their hierarchical mappings, and clearing their availability history. **Security Lock:** The default "admin" account cannot be deleted.

- **Employee Details:** Displays all workforce members. Admins can inline-edit an associate\'s operational Role or Set, or delete them. Features a one-click Excel Export tool that dynamically generates standardized tracking group names based on role and set. **Security Lock:** Admins cannot delete "login_user" managers from this view.

- **Team Mapping Details**: Allows admins to view the entire hierarchy tree and reassign an employee to a different reporting lead.

- **Team Availability:** An interactive pivot table generating a day-by-day matrix of the entire workforce\'s status over a custom date range. Admins can bulk-edit statuses (e.g., Planned Leave, Comp Off). The system only commits changes to the database if a specific cell is modified.

- **Search Availability**: A bidirectional search tool:

  - **TPM Search:** Shows the TPM\'s status plus the statuses of all Team Leads under them.

  - **Team Lead Search:** Shows the Team Lead\'s status, their managing TPM (upward), and their reporting associates (downward).

  - **Associate Search:** Shows the associate\'s status and their managing Team Lead (upward).

- **Track Details:** Provides a read-only, high-level overview of the mathematical blueprints and ETAs for all planned project tracks.

### **8.5. Change Password**

A secure utility for the active administrator to update their own system password. It requires the validation of the old password and ensures the new password is confirmed twice before committing the change to the database.

## **9. TPM Portal Dashboard (tpm_page.py)**

The Technical Project Manager (TPM) Dashboard provides specialized, mid-level management tools designed for high-level operational visibility and schedule management. This interface allows TPMs to oversee their direct reports (Language Team Leads) and maintain accurate, day-by-day workforce availability data to assist in project ETA planning.

The dashboard consists of three primary functional tabs:

### **9.1. Update Availability & Status Tracking**

This tab serves as the primary data entry point for future scheduling and leave management. The system enforces a standardized list of operational statuses to ensure consistent tracking across the entire workforce.

**Standardized Availability Statuses:**

When updating schedules, TPMs must select from the following core definitions:

- **Available:** Actively working their standard shift.

- **Planned Leave:** Pre-approved, scheduled time off.

- **Half Day Leave:** Partial day absence.

- **Sick Leave:** Unplanned medical absence.

- **Emergency Leave:** Unplanned urgent absence.

- **Comp Off:** Compensatory time off taken in lieu of previous overtime.

*(Note: The system also dynamically supports custom track names if an employee is assigned to a specific project phase).*

**Updating Workflows:**

The TPM can apply these statuses across custom date ranges using two distinct workflows:

1.  **Self-Updating:** The TPM logs their own upcoming availability (e.g., submitting Planned Leave for themselves for an upcoming week).

2.  **Team Lead Updating:** The TPM logs the schedules for the Language Team Leads explicitly mapped under them. The system dynamically queries the "TeamMapping" table to generate a dropdown list restricted *strictly* to their direct subordinates, ensuring they cannot alter the schedules of parallel teams.

3.  **Smart Date Processing:** For both workflows, when a date range is submitted, the backend logic automatically loops through the calendar and filters out weekends. It queries the "Availability" table, intelligently overwriting existing statuses or inserting new records exclusively for valid workdays (Monday--Friday).

### **9.2. View/Edit Dashboard (Bulk Schedule Matrix)**

This tab generates an interactive, pivot-style data grid designed for rapid schedule audits and bulk modifications across the TPM\'s entire reporting tree.

- **Strict Visibility Scope:** To maintain data privacy and hierarchical integrity, the data grid is strictly scoped. A TPM will only see their own personal schedule combined with the schedules of their mapped Language Team Leads. Standard associates and other TPMs are hidden from this view.

- **Dynamic Grid Rendering:** The TPM selects a start and end date. The application computes all valid weekdays within that range and dynamically renders them as editable columns. The \"Employee Name\" and \"Employee Email\" columns are locked to prevent accidental identity modification.

- **Inline Editing & Differential Commits:** TPMs can alter the status of any subordinate on any specific day using interactive dropdowns inside the grid. To optimize database performance and prevent system lag, the \"Save Changes\" function performs a differential check, comparing the newly edited grid against the original dataset. It generates SQL COMMIT commands *only* for the specific cells that were modified.

### **9.3. Change Password**

A self-service security utility for the TPM to manage their account credentials.

**Validation Logic:** Requires the user to correctly input their current password before allowing a change. The system validates that the new password and the confirmation password match exactly, and ensures the new password is distinct from the old one before committing the secure update to the "User" table.

## **10. Team Lead Portal Dashboard (teamlead_page.py)**

The Team Lead Dashboard provides targeted, ground-level management tools. This interface is specifically designed for the day-to-day operational tracking of the core production workforce. It allows Language Team Leads to manage their own schedules and meticulously track the daily availability of their direct reports (Associates) to ensure accurate shift and resource management.

The dashboard consists of three primary functional tabs:

### **10.1. Update Availability & Status Tracking**

This tab serves as the primary data entry point for associate scheduling and leave management. To maintain data consistency across the entire organization, the system enforces a standardized list of operational statuses.

**Standardized Availability Statuses:**

When updating schedules, Team Leads must select from the following core definitions:

- **Available:** The associate is actively working their standard shift.

- **Planned Leave:** Pre-approved, scheduled time off.

- **Half Day Leave:** Partial day absence.

- **Sick Leave:** Unplanned medical absence.

- **Emergency Leave:** Unplanned urgent absence.

- **Comp Off:** Compensatory time off taken in lieu of previous overtime worked.

**Updating Workflows:**

The Team Lead can apply these statuses across custom date ranges using two strictly partitioned workflows:

1.  **Self-Updating:** The Team Lead logs their own upcoming availability (e.g., logging their own Sick Leave or Comp Off).

2.  **Team Member Updating:** The Team Lead logs the schedules for the specific Associates explicitly mapped under them. The system actively queries the "TeamMapping" table to generate a secure dropdown list restricted *only* to their assigned team members, preventing cross-team data manipulation.

3.  **Smart Calendar Processing:** For both workflows, when a date range is submitted, the backend logic automatically iterates through the calendar and completely skips weekends (Saturdays and Sundays). It intelligently updates the "Availability" table by overwriting existing records or inserting new ones exclusively for valid operational workdays.

### **10.2. View/Edit Dashboard (Bulk Schedule Matrix)**

This tab generates an interactive, pivot-style data grid designed for rapid schedule audits, weekly resource planning, and bulk modifications at the team level.

- **Strict Visibility Scope:** To maintain hierarchical privacy and a focused UI, the data grid is tightly scoped. A Team Lead will only see their own personal schedule combined with the schedules of their mapped Associates. Other teams, parallel Team Leads, and higher-level managers are securely hidden from this view.

- **Dynamic Grid Rendering:** The Team Lead selects a start and end date. The application computes all valid weekdays within that range and dynamically renders them as editable dropdown columns. The dropdowns compile both the standard statuses and any custom statuses (like specific Track assignments) already saved in the database. Identifying metadata (Employee Name and Email) is locked to prevent accidental modifications.

- **Inline Editing & Differential Commits:** Team Leads can quickly adjust the status of any associate on any specific day directly within the grid. The \"Save Changes\" function employs a highly efficient differential database commit strategy. It compares the newly edited grid against the original dataset in memory, executing SQL updates *only* for the specific cells that were altered. This drastically reduces database load.

### **10.3. Change Password**

A self-service security utility for the Team Lead to manage their system credentials.

**Validation Logic:** To execute a password change, the user must correctly input their current password to verify their identity. The system then validates that the new password matches the confirmation field exactly, ensures no fields are left blank, and verifies that the new password is distinct from the previous one before securely committing the update to the "User" table.

## **11. Track Lead Portal Dashboard (tracklead_page.py)**

The Track Lead interface is the most functionally complex module in the application. It acts as a project planning engine that handles resource allocation, algorithmic simulations for completion dates, and dynamic calendar blocking.

The dashboard operates across three distinct tabs:

### **11.1. Track Planning (The ETA Engine)**

This tab allows Track Leads to build a project from scratch and simulate its timeline.

**Phase A: Configuration & Input Fields**

The Track Lead must define the exact parameters of the project. The application uses these inputs to automatically calculate the required daily workload.

- **Core Inputs:** Track Name, Number of Sets (1 to 3), and Files for annotation per set.

- **Productivity Inputs:** The lead inputs the Required productivity hours per day and the Average annotation time (minutes) per file.

  - **Code Logic:** The system calculates the **Annotation Target** automatically using the formula: (Productivity Hours \* 60) // Average Time.

- **Review Phase Inputs:** The lead inputs a percentage for Stage 1 (S1) and Stage 2 (S2) reviews.

  - **Code Logic:** The system calculates the exact number of files requiring S1/S2 using math.ceil((percentage \* total_files) / 100). It then calculates the daily targets for these stages based on their respective average processing times.

- **Timeline Inputs:** The user selects a Start Date and End Date. The code utilizes a helper function (next_weekday) to strictly enforce that projects can only begin on a Monday-Friday.

**Phase B: The Team Selection Matrix**

The application generates a master data grid showing every employee in the system and their availability for every weekday within the selected date range.

- **Inline Role/Set Editing:** Before selecting their team, the Track Lead can edit an employee\'s default Role (A, S1, S2) and Set (1, 2, 3) directly in the grid. Clicking \"Save Changes\" commits these updates directly to the "Employee" database table.

- **Resource Selection & Strict Filtering:** The lead ticks a \"Select\" checkbox for the associates they want. However, the code enforces a strict filtering mechanism based on the Number of Sets defined earlier:

  - If Sets = 1: The code strips out any selected employees whose Set is not \'1\'.

  - If Sets = 2: The code strips out any selected employees whose Set is \'3\'.

- **CEAT Export:** The finalized list of categorized employees (broken down into exact metrics for Annotators, S1s, and S2s per set) can be downloaded as an Excel file. The code uses a generate_group function to automatically reformat their roles into client-ready tracking strings (e.g., TCS-SET1-ANNOTATOR-GROUP).

**Phase C: Algorithmic ETA Calculation**

When the user clicks \"Calculate ETA\", the system runs a highly complex background simulation using the calculate_eta function. It calculates Set 1 first, then Set 2, etc.

- **Daily Simulation:** The code uses a while loop to simulate progress day-by-day. It completely skips weekends (is_weekday check).

- **Dynamic Capacity Checking:** For every simulated day, it queries the database to check the exact status of the assigned employees.

  - If status is Available, it adds 100% of their daily target to the team\'s capacity.

  - If status is Half Day Leave, it adds 50% of their target.

  - Other statuses add 0 capacity.

- **Precise Math:** If the team finishes the total files partially through a workday, the system calculates the exact fractional hours spent on that final day to generate ETAs formatted as X day(s) + Y hour(s).

- **Cascading Dependencies:** The code enforces operational logic: S1 calculations force their completion date to be *after* the Annotation completion date. S2 calculations only begin simulating from the day after S1 finishes.

**Phase D: Database Commit & Resource Locking**

- **Validation:** Annotation ETAs are mandatory. S1 and S2 are optional.

- **Resource Locking:** When \"Save Details\" is clicked, the system calls change_availability_status(). This iterates through every assigned employee and overwrites any \"Available\" days on their calendar with the new Track Name from the start date up to their specific calculated ETA date. This ensures no other Track Lead can claim them.

- **Overwrite Logic:** If a track with the exact same Name and Start Date already exists in the database, the code automatically updates the existing record rather than creating a duplicate.

### **11.2. View/Edit Dashboard (Track Management)**

This tab provides a secure management console for ongoing tracks.

- **Cascading Lookups:** Users select a Track Name from a dropdown, which dynamically populates a second dropdown with the available Start Dates associated with that track.

- **Read-Only Dashboard:** The system renders all saved metrics, total headcounts, and calculated ETAs. It also uses the saved employee JSON string to reconstruct and display a locked data grid showing the day-to-day calendar statuses of the assigned team.

- **Authorized Status Overrides:** An expandable section allows for mid-project calendar adjustments.

  - **Security Constraint:** The code actively checks if user.email == track.track_lead. If a different Track Lead tries to edit the track, the system throws an \"Access Denied\" error.

  - **Functionality:** The authorized lead can select specific employees from their assigned pool and change their status for a specific date range. For example, if S1 reviews finish three days before the calculated ETA, the lead can change those S1 employees\' statuses from the \"Track Name\" back to \"Available,\" instantly releasing them to the company-wide resource pool.

### **11.3. Change Password**

A self-service security utility for the Track Lead.

**Logic:** The code validates that the old password is correct via a database query, ensures the new password and confirmation password match, verifies the new password is not identical to the old one, and then commits the plaintext string to the "User" table.
