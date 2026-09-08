#!/usr/bin/env bash
# ============================================================
# IdeaHub — VPS Setup Script
# Hostinger KVM 1 | Ubuntu 22.04 | idea-flows.online
#
# Run as root on a fresh VPS:
#   chmod +x deploy/setup.sh
#   sudo bash deploy/setup.sh
#
# This script is idempotent — safe to run more than once.
# ============================================================

set -e  # Exit immediately on any error
set -u  # Treat unset variables as errors

# --- Colour helpers ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
section() { echo -e "\n${GREEN}========================================${NC}"; echo -e "${GREEN} $*${NC}"; echo -e "${GREEN}========================================${NC}"; }

# ---- Configuration ----
APP_USER="ideahub"
APP_DIR="/var/www/ideahub"
LOG_DIR="/var/log/ideahub"
UPLOAD_DIR="${APP_DIR}/static/uploads/menu"
PYTHON_VERSION="python3"

section "Step 1: System update & package installation"
apt-get update -qq
apt-get install -y \
    python3 python3-pip python3-venv \
    mysql-server \
    nginx \
    certbot python3-certbot-nginx \
    git curl \
    libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf2.0-0 \
    fonts-liberation \
    ufw
info "System packages installed."

section "Step 2: Create app user"
if id "${APP_USER}" &>/dev/null; then
    warn "User '${APP_USER}' already exists — skipping."
else
    adduser --disabled-password --gecos "" "${APP_USER}"
    usermod -aG www-data "${APP_USER}"
    info "User '${APP_USER}' created."
fi

section "Step 3: Set up application directory"
if [ ! -d "${APP_DIR}" ]; then
    mkdir -p "${APP_DIR}"
    info "Created ${APP_DIR}"
else
    warn "${APP_DIR} already exists — skipping mkdir."
fi
chown -R "${APP_USER}:www-data" "${APP_DIR}"

section "Step 4: Create log & upload directories"
mkdir -p "${LOG_DIR}" "${UPLOAD_DIR}"
chown -R "${APP_USER}:www-data" "${LOG_DIR}" "${UPLOAD_DIR}"
chmod 775 "${UPLOAD_DIR}"
info "Directories ready: ${LOG_DIR}, ${UPLOAD_DIR}"

section "Step 5: MySQL setup"
systemctl start mysql
systemctl enable mysql

# Prompt for MySQL root password and new DB credentials
read -rp "MySQL root password (leave blank if none set yet): " MYSQL_ROOT_PASS
read -rp "New DB name [ideahub]: " DB_NAME;       DB_NAME="${DB_NAME:-ideahub}"
read -rp "New DB user [ideauser]: " DB_USER;      DB_USER="${DB_USER:-ideauser}"
read -rsp "New DB user password: " DB_PASS; echo

MYSQL_CMD="mysql -u root"
[ -n "${MYSQL_ROOT_PASS}" ] && MYSQL_CMD="${MYSQL_CMD} -p${MYSQL_ROOT_PASS}"

${MYSQL_CMD} <<SQL
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL
info "MySQL: database '${DB_NAME}' and user '${DB_USER}' ready."

section "Step 6: Python virtual environment & dependencies"
sudo -u "${APP_USER}" bash -c "
    cd ${APP_DIR}
    ${PYTHON_VERSION} -m venv .venv
    .venv/bin/pip install --upgrade pip --quiet
    .venv/bin/pip install -r requirements.txt --quiet
"
info "Python dependencies installed into .venv"

section "Step 7: .env file"
ENV_FILE="${APP_DIR}/.env"
if [ -f "${ENV_FILE}" ]; then
    warn ".env already exists — skipping creation. Edit it manually if needed."
else
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    cat > "${ENV_FILE}" <<ENV
FLASK_ENV=production
SECRET_KEY=${SECRET_KEY}
DATABASE_URL=mysql+pymysql://${DB_USER}:${DB_PASS}@localhost/${DB_NAME}
CORS_ORIGINS=https://idea-flows.online,https://www.idea-flows.online
UPLOAD_FOLDER=${UPLOAD_DIR}
PORT=5000
ENV
    chown "${APP_USER}:${APP_USER}" "${ENV_FILE}"
    chmod 600 "${ENV_FILE}"
    info ".env created at ${ENV_FILE} (SECRET_KEY auto-generated)"
fi

section "Step 8: Run first-time DB migration + seed"
warn "Starting app briefly to run migrations — it will be stopped immediately."
sudo -u "${APP_USER}" bash -c "
    cd ${APP_DIR}
    set -a; source .env; set +a
    timeout 30 .venv/bin/python app.py || true
"
info "Migration complete."

section "Step 9: Install systemd service"
cp "${APP_DIR}/deploy/ideahub.service" /etc/systemd/system/ideahub.service
systemctl daemon-reload
systemctl enable ideahub
systemctl start ideahub
sleep 3
systemctl status ideahub --no-pager || warn "Service may still be starting — check with: journalctl -u ideahub -n 50"

section "Step 10: Install Nginx (HTTP-only first)"
NGINX_AVAILABLE="/etc/nginx/sites-available/ideahub"
NGINX_ENABLED="/etc/nginx/sites-enabled/ideahub"

cp "${APP_DIR}/deploy/nginx-before-ssl.conf" "${NGINX_AVAILABLE}"
[ -L "${NGINX_ENABLED}" ] || ln -s "${NGINX_AVAILABLE}" "${NGINX_ENABLED}"
[ -f /etc/nginx/sites-enabled/default ] && rm /etc/nginx/sites-enabled/default || true

mkdir -p /var/www/certbot
nginx -t && systemctl reload nginx
info "Nginx configured (HTTP only)."

section "Step 11: Firewall"
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw deny 5000/tcp
ufw --force enable
info "Firewall enabled: SSH, HTTP(80), HTTPS(443) open. Port 5000 closed."

section "Step 12: SSL Certificate (Certbot)"
info "Running Certbot — this will ask for your email."
certbot --nginx \
    -d idea-flows.online \
    -d www.idea-flows.online \
    --redirect \
    --agree-tos \
    --non-interactive \
    --email "$(read -rp 'Your email for SSL cert: ' em && echo $em)" \
    || warn "Certbot failed — run manually: sudo certbot --nginx -d idea-flows.online -d www.idea-flows.online"

section "Step 13: Switch to HTTPS Nginx config"
cp "${APP_DIR}/deploy/nginx.conf" "${NGINX_AVAILABLE}"
nginx -t && systemctl reload nginx
info "Nginx updated to HTTPS config."

section "Step 14: Anti-DDoS, Rate Limiting & Bot Scraping Defense"
if [ -f "${APP_DIR}/deploy/setup_ddos_bot_defense.sh" ]; then
    bash "${APP_DIR}/deploy/setup_ddos_bot_defense.sh"
    info "Anti-DDoS & Fail2ban configured."
fi

section "✅ Setup Complete!"
echo ""
echo "  App URL:      https://idea-flows.online"
echo "  App dir:      ${APP_DIR}"
echo "  Logs:         ${LOG_DIR}/"
echo "  journalctl:   sudo journalctl -u ideahub -f"
echo "  Service:      sudo systemctl status ideahub"
echo "  Nginx test:   sudo nginx -t"
echo ""
echo "  To deploy updates:"
echo "    cd ${APP_DIR} && sudo -u ${APP_USER} git pull"
echo "    sudo systemctl restart ideahub"
echo ""
