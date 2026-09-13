# IdeaHub — VPS Deployment Guide
**Hostinger KVM 1 · Ubuntu 22.04 · idea-flows.online**

> This guide deploys the IdeaHub Flask POS app to a Hostinger KVM 1 VPS using:
> **Gunicorn gthread + simple-websocket** (Python), **MySQL 8** (database), **Nginx** (reverse proxy), **Certbot** (free SSL)

---

## Table of Contents
1. [Prerequisites](#1-prerequisites)
2. [Option A — Automated Setup (Recommended)](#2-option-a--automated-setup)
3. [Option B — Manual Step-by-Step](#3-option-b--manual-step-by-step)
4. [Updating the App](#4-updating-the-app)
5. [Common Commands](#5-common-commands)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Prerequisites

Before starting, you need:

- [ ] A Hostinger KVM 1 VPS with Ubuntu 22.04 provisioned
- [ ] SSH access as `root` (find IP in Hostinger hPanel)
- [ ] Your domain `idea-flows.online` DNS **A record** pointing to the VPS IP
  - In Cloudflare or your DNS provider: `A @ <VPS-IP>` and `A www <VPS-IP>`
  - Wait 5–30 minutes for DNS to propagate before running Certbot
- [ ] Your GitHub repo URL (to clone the project)

**Check DNS propagation first:**
```bash
ping idea-flows.online
# Should reply from your VPS IP address
```

---

## 2. Option A — Automated Setup

This is the fastest path. The `deploy/setup.sh` script handles everything.

```bash
# 1. SSH into your VPS
ssh root@<YOUR-VPS-IP>

# 2. Clone the project
git clone <your-repository-url> /var/www/ideahub
cd /var/www/ideahub

# 3. Run the setup script
chmod +x deploy/setup.sh
sudo bash deploy/setup.sh
```

The script will prompt you for:
- MySQL root password (leave blank on fresh VPS)
- New database name, username, and password
- Your email (for the SSL certificate)

When it finishes, visit `https://idea-flows.online` — your app is live.

---

## 3. Option B — Manual Step-by-Step

Follow this if you want to understand each step or if the automated script fails partway.

### Step 1 — SSH In & Update System

```bash
ssh root@<YOUR-VPS-IP>
apt update && apt upgrade -y
```

### Step 2 — Install Required Packages

```bash
apt install -y \
    python3 python3-pip python3-venv \
    mysql-server \
    nginx \
    certbot python3-certbot-nginx \
    git curl ufw \
    libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf2.0-0 fonts-liberation
```

> **Why the `libpango` / `libcairo` packages?**
> The app uses `weasyprint` and `xhtml2pdf` to generate PDF receipts. These system libraries are required by weasyprint.

### Step 3 — Create a Dedicated App User

Never run the app as `root`. Create a restricted user:

```bash
adduser --disabled-password --gecos "" ideahub
usermod -aG www-data ideahub
```

### Step 4 — Clone the Repository

```bash
mkdir -p /var/www/ideahub
git clone <your-repository-url> /var/www/ideahub
chown -R ideahub:www-data /var/www/ideahub
```

### Step 5 — Set Up MySQL Database

```bash
# Start MySQL (may already be running)
systemctl start mysql
systemctl enable mysql

# Open MySQL shell
mysql -u root
```

Inside MySQL, run:
```sql
CREATE DATABASE ideahub CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'ideauser'@'localhost' IDENTIFIED BY 'YourStrongPassword123!';
GRANT ALL PRIVILEGES ON ideahub.* TO 'ideauser'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

> **Tip:** Choose a strong password for `ideauser`. You'll put it in the `.env` file.

### Step 6 — Create Python Virtual Environment

```bash
cd /var/www/ideahub
sudo -u ideahub python3 -m venv .venv
sudo -u ideahub .venv/bin/pip install --upgrade pip
sudo -u ideahub .venv/bin/pip install -r requirements.txt
```

> **Note:** This step takes 2–5 minutes on KVM 1 due to packages like `weasyprint` and `Pillow`.

### Step 7 — Create the `.env` File

Generate a secure secret key:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# Copy this output — use it as SECRET_KEY below
```

Create the env file:
```bash
nano /var/www/ideahub/.env
```

Paste and fill in your values:
```ini
FLASK_ENV=production
SECRET_KEY=<paste-your-generated-key-here>
DATABASE_URL=mysql+pymysql://ideauser:YourStrongPassword123!@localhost/ideahub
CORS_ORIGINS=https://idea-flows.online,https://www.idea-flows.online
UPLOAD_FOLDER=/var/www/ideahub/static/uploads/menu
PORT=5000
```

Secure the file (only root/ideahub can read it):
```bash
chown ideahub:ideahub /var/www/ideahub/.env
chmod 600 /var/www/ideahub/.env
```

### Step 8 — Create Upload & Log Directories

```bash
mkdir -p /var/www/ideahub/static/uploads/menu
mkdir -p /var/log/ideahub
chown -R ideahub:www-data /var/www/ideahub/static/uploads/menu
chown -R ideahub:www-data /var/log/ideahub
chmod 775 /var/www/ideahub/static/uploads/menu
```

### Step 9 — Run First-Time DB Migration

The app auto-creates all tables on first startup:

```bash
cd /var/www/ideahub
sudo -u ideahub bash -c "set -a; source .env; set +a; .venv/bin/python app.py"
# Wait ~5 seconds for "Running on http://0.0.0.0:5000" then press Ctrl+C
```

You should see output like:
```
Startup migration warning: ... (OK if empty or says tables exist)
Running on http://0.0.0.0:5000
```

### Step 10 — Install systemd Service

```bash
cp /var/www/ideahub/deploy/ideahub.service /etc/systemd/system/ideahub.service
systemctl daemon-reload
systemctl enable ideahub    # auto-start on reboot
systemctl start ideahub     # start now
```

Check it's running:
```bash
systemctl status ideahub
# Should show: Active: active (running)
```

View live logs:
```bash
journalctl -u ideahub -f
```

### Step 11 — Install Nginx (HTTP First)

```bash
# Copy the HTTP-only config
cp /var/www/ideahub/deploy/nginx-before-ssl.conf /etc/nginx/sites-available/ideahub
ln -s /etc/nginx/sites-available/ideahub /etc/nginx/sites-enabled/ideahub

# Remove the default Nginx page
rm -f /etc/nginx/sites-enabled/default

# Create directory for Certbot ACME challenge
mkdir -p /var/www/certbot

# Test config and reload Nginx
nginx -t && systemctl reload nginx
```

Test that the site loads (without SSL for now):
```bash
curl -I http://idea-flows.online
# Should return HTTP 200
```

### Step 12 — Get Free SSL Certificate (Certbot)

```bash
certbot --nginx \
    -d idea-flows.online \
    -d www.idea-flows.online \
    --redirect \
    --agree-tos \
    -m your-email@example.com
```

Certbot will:
1. Verify you own the domain (via HTTP challenge)
2. Issue a Let's Encrypt certificate
3. Automatically modify your Nginx config to use HTTPS

### Step 13 — Switch to the Full HTTPS Nginx Config

Replace the HTTP-only config with the full HTTPS version (which includes security headers, gzip, and WebSocket support):

```bash
cp /var/www/ideahub/deploy/nginx.conf /etc/nginx/sites-available/ideahub
nginx -t && systemctl reload nginx
```

### Step 14 — Configure Firewall

```bash
ufw allow OpenSSH         # Keep SSH access!
ufw allow 'Nginx Full'    # HTTP (80) + HTTPS (443)
ufw deny 5000/tcp         # Block direct access to gunicorn
ufw enable
ufw status
```

Expected output:
```
Status: active
To                         Action      From
--                         ------      ----
OpenSSH                    ALLOW       Anywhere
Nginx Full                 ALLOW       Anywhere
5000/tcp                   DENY        Anywhere
```

### Step 15 — Smoke Test

```bash
# 1. Check the site loads with HTTPS
curl -I https://idea-flows.online
# Expect: HTTP/2 200, strict-transport-security header

# 2. Check the app service
systemctl status ideahub

# 3. Check Nginx
systemctl status nginx

# 4. Check logs for errors
tail -n 50 /var/log/ideahub/error.log
journalctl -u ideahub -n 50
```

Open in a browser: **https://idea-flows.online** → you should see the IdeaHub login page with a green padlock 🔒

---

## 4. Updating the App

When you push code changes, deploy them to the VPS like this:

```bash
# SSH into VPS
ssh root@<YOUR-VPS-IP>

# Pull latest code
cd /var/www/ideahub
sudo -u ideahub git pull

# Install any new Python dependencies
sudo -u ideahub .venv/bin/pip install -r requirements.txt

# Restart the service (migrations run automatically on startup)
systemctl restart ideahub

# Verify it's running
systemctl status ideahub
```

> **Note:** The app runs `SchemaMigrator` on startup, so new database columns/tables are applied automatically.

---

## 5. Common Commands

| Task | Command |
|------|---------|
| Start app | `systemctl start ideahub` |
| Stop app | `systemctl stop ideahub` |
| Restart app | `systemctl restart ideahub` |
| View live logs | `journalctl -u ideahub -f` |
| View last 100 log lines | `journalctl -u ideahub -n 100` |
| Reload Nginx | `systemctl reload nginx` |
| Test Nginx config | `nginx -t` |
| Renew SSL cert | `certbot renew --dry-run` |
| MySQL shell | `mysql -u ideauser -p ideahub` |
| Backup database | `mysqldump -u ideauser -p ideahub > backup_$(date +%Y%m%d).sql` |
| Restore database | `mysql -u ideauser -p ideahub < backup_20260908.sql` |

---

## 6. Troubleshooting

### 502 Bad Gateway
Nginx is running but gunicorn is not.
```bash
systemctl status ideahub        # Is it running?
journalctl -u ideahub -n 50     # Look for Python errors
cat /var/log/ideahub/error.log  # Gunicorn error log
```
Most common causes:
- `.env` file missing or has wrong `DATABASE_URL`
- MySQL is not running: `systemctl start mysql`
- Python import error: run `sudo -u ideahub .venv/bin/python -c "from app import create_app"`

### Login/Session Not Persisting
The browser is rejecting the session cookie.
- Make sure you're accessing via `https://` (not `http://`)
- Check `SESSION_COOKIE_SECURE=True` and `SESSION_COOKIE_SAMESITE=Lax` are set (they are in config.py)
- Open browser DevTools → Application → Cookies → verify `Secure` flag is present

### SocketIO / Real-Time Updates Not Working
The WebSocket connection is failing.
```bash
# Check if the /socket.io/ location is in the Nginx config
grep -A5 "socket.io" /etc/nginx/sites-available/ideahub
```
- Make sure you're using the full HTTPS Nginx config (`deploy/nginx.conf`), not the HTTP-only one
- Check browser console for WebSocket errors (F12 → Console)
- Verify `simple-websocket` is installed: `sudo -u ideahub .venv/bin/pip show simple-websocket`

### File Upload 413 Error (Request Entity Too Large)
```bash
grep "client_max_body_size" /etc/nginx/sites-available/ideahub
# Should show: client_max_body_size 10m;
```
If missing, the wrong Nginx config is installed. Recopy `deploy/nginx.conf`.

### Port 5000 Accessible from Outside
The firewall rule blocking port 5000 may not be active:
```bash
ufw status
ufw deny 5000/tcp
ufw reload
```

### SSL Certificate Renewal (Automatic)
Certbot installs a cron job that auto-renews certificates. Test it manually:
```bash
certbot renew --dry-run
```
If renewal fails, check that port 80 is open and Nginx is running.

### Database Connection Error
```bash
# Test the DB connection directly
mysql -u ideauser -p ideahub -e "SHOW TABLES;"

# Check the DATABASE_URL in .env matches your MySQL credentials
cat /var/www/ideahub/.env | grep DATABASE_URL
```

---

## Architecture Overview

```
Internet
    │
    ▼ HTTPS (443)
 Nginx  ──────── serves /static/ directly from disk
    │
    │ proxy_pass (HTTP to localhost:5000)
    ▼
 Gunicorn (gthread, 1 worker / 50 threads)
    │
    ▼
 Flask App (IdeaHub)
    │
    ├── Flask-SocketIO ←──── WebSocket /socket.io/
    ├── Flask-SQLAlchemy
    │       │
    │       ▼
    │   MySQL 8 (localhost)
    │
    └── static/uploads/menu/  (menu images on disk)
```

---

*Last updated: 2026-09-08 | VPS: Hostinger KVM 1 | Domain: idea-flows.online*
