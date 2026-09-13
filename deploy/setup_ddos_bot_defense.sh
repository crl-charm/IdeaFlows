#!/usr/bin/env bash
# ============================================================
# IdeaHub — Anti-DDoS, Anti-Bot & Scraper Defense Setup Script
# Hostinger KVM 1 | Ubuntu 22.04 LTS | idea-flows.online
#
# Usage (run as root on VPS):
#   chmod +x deploy/setup_ddos_bot_defense.sh
#   sudo bash deploy/setup_ddos_bot_defense.sh
#
# This script is idempotent — safe to run multiple times.
# ============================================================

set -euo pipefail

# --- Color formatting ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
section() { echo -e "\n${GREEN}========================================${NC}\n${GREEN} $*${NC}\n${GREEN}========================================${NC}"; }

# Ensure root
if [ "$(id -u)" -ne 0 ]; then
    error "This script must be run as root: sudo bash deploy/setup_ddos_bot_defense.sh"
fi

section "Step 1: Install Fail2ban & IPSet"
apt-get update -qq
apt-get install -y fail2ban ipset
systemctl enable fail2ban
info "Fail2ban and ipset installed and enabled."

section "Step 2: Configure Logrotate with copytruncate"
# Using copytruncate ensures Fail2ban maintains open file handles
# without silently breaking after daily/weekly log rotations.
cat > /etc/logrotate.d/ideahub <<'EOF'
/var/log/ideahub/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    copytruncate
    create 0640 ideahub www-data
}

/var/log/nginx/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    copytruncate
    create 0640 www-data adm
}
EOF
chmod 644 /etc/logrotate.d/ideahub
info "Logrotate configured with copytruncate at /etc/logrotate.d/ideahub"

section "Step 3: Apply Linux Kernel DDoS & SYN-Flood Hardening"
cat > /etc/sysctl.d/99-ddos-protection.conf <<'EOF'
# Protect against SYN flood attacks (TCP SYN cookies)
net.ipv4.tcp_syncookies = 1

# Increase the backlog queue for incoming SYN requests
net.ipv4.tcp_max_syn_backlog = 2048

# Lower the socket timeout for FIN-WAIT to reclaim sockets faster from slow clients
net.ipv4.tcp_fin_timeout = 15

# Enable anti-spoofing protection (Reverse Path Filtering)
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1

# Ignore ICMP echo broadcasts to prevent Smurf attacks
net.ipv4.icmp_echo_ignore_broadcasts = 1

# Ignore bogus ICMP error responses
net.ipv4.icmp_ignore_bogus_error_responses = 1

# Connection queue capacity
net.core.somaxconn = 1024
EOF

sysctl --system > /dev/null
info "Kernel sysctl DDoS protection parameters applied."

section "Step 4: Configure Fail2ban Filters"

# Filter 1: Nginx 429 Rate Limit Violations
cat > /etc/fail2ban/filter.d/nginx-req-limit.conf <<'EOF'
[Definition]
failregex = ^<HOST> -.*"(GET|POST|HEAD).*" 429
ignoreregex =
EOF

# Filter 2: IdeaHub Application Honeypot Traps
cat > /etc/fail2ban/filter.d/ideahub-honeypot.conf <<'EOF'
[Definition]
failregex = ^.*BOT_HONEYPOT_TRIGGERED: <HOST> .*$
ignoreregex =
EOF

# Filter 3: Malicious Path / Exploit Probing
cat > /etc/fail2ban/filter.d/ideahub-botsearch.conf <<'EOF'
[Definition]
failregex = ^<HOST> -.*"(GET|POST|HEAD) /(\.env|\.git|wp-admin|phpmyadmin|xmlrpc\.php).*".*
ignoreregex =
EOF

info "Fail2ban filter definitions created."

section "Step 5: Configure Fail2ban Jails"
cat > /etc/fail2ban/jail.d/ideahub.conf <<'EOF'
[DEFAULT]
# Default ban for 1 hour (3600 seconds)
bantime  = 3600
findtime = 600
maxretry = 5
banaction = ufw

# Jail 1: Ban repeat rate-limit abusers (hit 429 more than 8 times in 2 minutes)
[nginx-req-limit]
enabled  = true
filter   = nginx-req-limit
port     = http,https
logpath  = /var/log/nginx/access.log
maxretry = 8
findtime = 120
bantime  = 7200

# Jail 2: Instantly ban automated scrapers that hit the randomized honeypot trap
[ideahub-honeypot]
enabled  = true
filter   = ideahub-honeypot
port     = http,https
logpath  = /var/log/ideahub/security.log
maxretry = 1
findtime = 60
bantime  = 86400

# Jail 3: Ban vulnerability/exploit scanners probing for .env, wp-login, etc.
[ideahub-botsearch]
enabled  = true
filter   = ideahub-botsearch
port     = http,https
logpath  = /var/log/nginx/access.log
maxretry = 3
findtime = 300
bantime  = 86400
EOF

info "Fail2ban jail configuration created at /etc/fail2ban/jail.d/ideahub.conf"

section "Step 6: Firewall (UFW) SSH Rate Limiting"
ufw limit 22/tcp
info "UFW rate-limiting on SSH enabled (protects against SSH connection floods)."

section "Step 7: Verify and Restart Services"
systemctl restart fail2ban
sleep 2

if systemctl is-active --quiet fail2ban; then
    info "Fail2ban is active and running."
    fail2ban-client status
else
    error "Fail2ban failed to start. Check /var/log/fail2ban.log"
fi

# Test Nginx configuration if present
if [ -f /etc/nginx/sites-available/ideahub ]; then
    nginx -t && systemctl reload nginx
    info "Nginx configuration reloaded successfully."
fi

section "✅ Anti-DDoS & Bot Defense Setup Complete!"
echo ""
echo "  Active Jails:"
echo "    - nginx-req-limit   (bans IPs exceeding Nginx 429 rate limits)"
echo "    - ideahub-honeypot  (24h instant ban on scrapers triggering honeypot)"
echo "    - ideahub-botsearch (24h ban on vulnerability probes)"
echo ""
echo "  Useful Commands:"
echo "    - Check jail status:    sudo fail2ban-client status"
echo "    - Check specific jail:  sudo fail2ban-client status ideahub-honeypot"
echo "    - Unban an IP:          sudo fail2ban-client set <jail_name> unbanip <IP>"
echo "    - View security logs:   sudo tail -f /var/log/ideahub/security.log"
echo "    - Test logrotate:       sudo logrotate -d /etc/logrotate.d/ideahub"
echo ""
