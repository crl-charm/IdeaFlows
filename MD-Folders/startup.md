# IdeaHub — How to Run & Technical Guide

instructions to set up and run IdeaHub locally, plus a quick guide on how the project is organized.

---

## 🚀 How to Run the Project (Step-by-Step)

Follow these steps to get the app running on your computer.

### Prerequisites
Make sure you have installed:
1. **Python** (version 3.12 or higher)
2. **MySQL** (or XAMPP with MySQL running)
3. **Git**

---

### Step 1: Open the Project Folder
Open your terminal (or PowerShell on Windows) and go to the project directory:
```bash
cd vercelIdeahub
```

### Step 2: Set Up a Python Virtual Environment
This keeps project dependencies isolated.

- **Windows (PowerShell):**
  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  ```
- **Mac / Linux:**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### Step 3: Install Required Packages
Install all required libraries by running:
```bash
pip install -r requirements.txt
```

### Step 4: Create the Database
1. Open XAMPP or your MySQL client (like phpMyAdmin or MySQL Workbench).
2. Create a new database named `ideahub_pos`:
   ```sql
   CREATE DATABASE ideahub_pos;
   ```
3. *Note:* By default, the app connects to MySQL on `localhost` with user `root` and no password. If your MySQL setup uses a password, set `DATABASE_URL` in your terminal:
   ```powershell
   $env:DATABASE_URL="mysql+pymysql://root:your_password@localhost/ideahub_pos"
   ```

### Step 5: Test the Setup (Optional)
Check if all files and modules load properly without errors:
```bash
python scripts/validate_imports.py
```

### Step 6: Start the App
Run the main app file:
```bash
python app.py
```
The app will automatically set up database tables and start running at **`http://localhost:5001`**. Open that link in your web browser!

---

## 📂 Project Structure

Here is how the main files and folders are organized inside `app/`:

- **`app/routes/`**: Web pages and API endpoints (menu, orders, payables, inventory, etc.).
- **`app/controllers/`**: Controllers for complex sections like analytics, management, and finance.
- **`app/services/`**: The business logic (calculations, report generation, rules).
- **`app/repositories/`**: Database queries (getting and saving data to MySQL).
- **`app/models/`**: Database tables defined with SQLAlchemy (User, Order, MenuItem, Payable, etc.).
- **`app/templates/`**: HTML screens and pages.
- **`app/utils/`**: Helpers like `auth.py` (login/role checks) and `uploads.py` (image uploads).
- **`config/config.py`**: Project settings (database connection, session timeouts, file limits).
- **`app.py`**: Main file that launches the server.

---

## 🔐 Built-in Security Features

- **Login & Roles**: Pages verify whether a user is logged in as staff or admin before granting access.
- **Password Safety**: Passwords are saved safely using bcrypt. Accounts lock for 15 minutes after 5 wrong password attempts.
- **Auto Logout**: Inactive sessions automatically log out after 2 hours.
- **Safe File Uploads**: Uploaded images check file extensions and headers, resize large images, and rename files with unique IDs to stay safe.
- **Database Safety**: Queries use standard SQLAlchemy parameters to prevent SQL injection.

---

## 📝 Log Files
- **`app.log`**: General system activity and application logs.
- **`security.log`**: Audit log for logins, lockouts, and administrative actions.
