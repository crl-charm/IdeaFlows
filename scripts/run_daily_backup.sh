#!/usr/bin/env bash
set -euo pipefail
umask 077
exec /var/www/pos/venv/bin/python /var/www/pos/scripts/run_daily_backup.py "$@"
