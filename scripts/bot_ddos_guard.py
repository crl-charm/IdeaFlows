#!/usr/bin/env python3
"""
============================================================
IdeaHub — Bot Defense & DDoS Mitigation Management Utility
============================================================
Provides status reporting, IP unbanning, log inspection, and
automated testing of anti-scraping and rate-limiting rules.

Usage:
  python scripts/bot_ddos_guard.py status
  python scripts/bot_ddos_guard.py unban <IP> [jail_name]
  python scripts/bot_ddos_guard.py test
"""

import sys
import os
import subprocess
import argparse

# Ensure project root is in python path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def cmd_status(args):
    """Check live status of Fail2ban jails, Nginx, and security logs."""
    print("=" * 60)
    print(" IdeaHub DDoS & Bot Defense Status Report")
    print("=" * 60)

    # 1. Fail2ban status
    print("\n[1] Fail2ban Jails:")
    try:
        res = subprocess.run(["fail2ban-client", "status"], capture_output=True, text=True)
        if res.returncode == 0:
            print(res.stdout.strip())
            # Check individual jails if present
            for jail in ["nginx-req-limit", "ideahub-honeypot", "ideahub-botsearch"]:
                jail_res = subprocess.run(["fail2ban-client", "status", jail], capture_output=True, text=True)
                if jail_res.returncode == 0:
                    print(f"\n--- Jail: {jail} ---")
                    for line in jail_res.stdout.strip().splitlines():
                        if "Currently banned:" in line or "Banned IP list:" in line or "Total banned:" in line:
                            print(f"  {line.strip()}")
        else:
            print("  Fail2ban not running or not accessible without sudo.")
    except FileNotFoundError:
        print("  fail2ban-client not installed on this system.")

    # 2. Security Log Honeypot triggers
    print("\n[2] Recent Security Log Events:")
    candidates = [
        "/var/log/ideahub/security.log",
        os.path.join(ROOT_DIR, "security.log"),
    ]
    found_log = False
    for path in candidates:
        if os.path.isfile(path):
            found_log = True
            print(f"  Source: {path}")
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                    honeypot_lines = [l.strip() for l in lines if "BOT_HONEYPOT_TRIGGERED" in l or "BOT_TOOL_BLOCKED" in l]
                    if honeypot_lines:
                        print(f"  Last {min(5, len(honeypot_lines))} honeypot / bot events:")
                        for event in honeypot_lines[-5:]:
                            print(f"    - {event}")
                    else:
                        print("  No honeypot or bot trigger events recorded yet.")
            except Exception as e:
                print(f"  Error reading {path}: {e}")
            break

    if not found_log:
        print("  No security.log found in standard locations.")

    print("\n" + "=" * 60)


def cmd_unban(args):
    """Unban an IP address across Fail2ban jails."""
    ip = args.ip
    jail = args.jail

    jails_to_try = [jail] if jail else ["nginx-req-limit", "ideahub-honeypot", "ideahub-botsearch"]

    print(f"Attempting to unban IP: {ip}")
    success = False
    for j in jails_to_try:
        try:
            res = subprocess.run(["fail2ban-client", "set", j, "unbanip", ip], capture_output=True, text=True)
            if res.returncode == 0:
                print(f"  [SUCCESS] Unbanned {ip} from jail '{j}'.")
                success = True
            else:
                if "not found" not in res.stderr.lower():
                    print(f"  [{j}] {res.stderr.strip() or res.stdout.strip()}")
        except FileNotFoundError:
            print("  fail2ban-client command not found. Run with sudo on Linux.")
            return

    if not success:
        print(f"  IP {ip} was not currently banned in specified jails.")


def cmd_test(args):
    """
    Run self-contained verification tests against Flask application.
    Tests ProxyFix, robots.txt, honeypot traps, and composite login keying.
    """
    print("=" * 60)
    print(" Running IdeaHub Bot Defense & Rate-Limiter Tests")
    print("=" * 60)

    try:
        from app import create_app
        app = create_app()
        client = app.test_client()
    except Exception as e:
        print(f"[FAIL] Could not initialize Flask app for testing: {e}")
        return

    passed = 0
    total = 0

    # Test 1: GET /robots.txt
    total += 1
    print("\n[Test 1] Verifying /robots.txt endpoint...")
    res = client.get("/robots.txt")
    if res.status_code == 200 and b"Disallow: /admin/" in res.data and b"GPTBot" in res.data:
        print("  [PASS] /robots.txt returned 200 with strict Disallow rules.")
        passed += 1
    else:
        print(f"  [FAIL] Unexpected response: {res.status_code}, data: {res.data[:200]}")

    # Test 2: Randomized Honeypot Route
    total += 1
    print("\n[Test 2] Verifying Randomized Honeypot Route...")
    honeypot_path = app.config.get("HONEYPOT_SECRET_PATH")
    print(f"  Testing route: {honeypot_path}")
    res = client.get(honeypot_path, headers={"User-Agent": "MaliciousScraperBot/1.0"})
    if res.status_code == 403:
        print("  [PASS] Honeypot route aborted with 403 Forbidden.")
        passed += 1
    else:
        print(f"  [FAIL] Honeypot route returned {res.status_code} instead of 403.")

    # Test 3: Decoy Scanner Traps (.env, wp-login)
    total += 1
    print("\n[Test 3] Verifying Decoy Scanner Trap (/.env)...")
    res = client.get("/.env", headers={"User-Agent": "curl/7.68.0"})
    if res.status_code == 403:
        print("  [PASS] Decoy path /.env caught and returned 403.")
        passed += 1
    else:
        print(f"  [FAIL] Decoy path /.env returned {res.status_code} instead of 403.")

    # Test 4: Single-Hop ProxyFix IP forwarding
    total += 1
    print("\n[Test 4] Verifying Single-Hop ProxyFix client IP forwarding...")
    test_remote_ip = "203.0.113.195"
    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "5000",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_X_FORWARDED_FOR": test_remote_ip,
        "HTTP_X_FORWARDED_PROTO": "https",
    }
    def dummy_start_response(status, headers):
        pass
    # Exercise the full WSGI ProxyFix middleware stack
    list(app.wsgi_app(environ, dummy_start_response))
    resolved_ip = environ.get("REMOTE_ADDR")
    resolved_proto = environ.get("wsgi.url_scheme")
    if resolved_ip == test_remote_ip and resolved_proto == "https":
        print(f"  [PASS] ProxyFix correctly identified client IP: {resolved_ip} (scheme: {resolved_proto})")
        passed += 1
    else:
        print(f"  [FAIL] ProxyFix resolved IP to '{resolved_ip}', expected '{test_remote_ip}'")

    # Test 5: Composite Login Rate Limiting Key
    total += 1
    print("\n[Test 5] Verifying Composite Login Rate Limiting Key (IP + username)...")
    from app.core.bot_defense import get_login_rate_limit_key
    with app.test_request_context(
        "/api/login",
        method="POST",
        json={"username": "AliceStaff", "password": "password123"},
        environ_base={"REMOTE_ADDR": "198.51.100.22"}
    ):
        key = get_login_rate_limit_key()
        if "198.51.100.22:alicestaff" in key:
            print(f"  [PASS] Composite key correctly formed: '{key}'")
            passed += 1
        else:
            print(f"  [FAIL] Unexpected composite key: '{key}'")

    # Test 6: Exploit Scanner User-Agent Filter
    total += 1
    print("\n[Test 6] Verifying Exploit Scanner Tool Blocking (e.g. sqlmap signature)...")
    res = client.get("/", headers={"User-Agent": "sqlmap/1.5#stable (http://sqlmap.org)"})
    if res.status_code == 403:
        print("  [PASS] sqlmap signature caught and returned 403.")
        passed += 1
    else:
        print(f"  [FAIL] sqlmap signature returned {res.status_code} instead of 403.")

    print("\n" + "=" * 60)
    print(f" Test Results: {passed}/{total} Passed")
    print("=" * 60)
    print("\n* Note on User-Agent Blocking Scope:")
    print("  User-Agent checks catch naive scrapers and off-the-shelf scanner tools.")
    print("  Sophisticated scrapers that spoof regular browser headers bypass UA checks;")
    print("  Nginx rate/connection limits, the honeypot trap, and Fail2ban are the real backstops.")


def main():
    parser = argparse.ArgumentParser(description="IdeaHub DDoS & Bot Defense Management Utility")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Status subcommand
    subparsers.add_parser("status", help="Show Fail2ban and security status")

    # Unban subcommand
    unban_parser = subparsers.add_parser("unban", help="Unban an IP address")
    unban_parser.add_argument("ip", help="IP address to unban")
    unban_parser.add_argument("jail", nargs="?", default=None, help="Optional specific jail name")

    # Test subcommand
    subparsers.add_parser("test", help="Run automated test suite for defenses")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status(args)
    elif args.command == "unban":
        cmd_unban(args)
    elif args.command == "test":
        cmd_test(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
