# VPS package upgrade plan

Status: **plan only — not executed**. Target: the production Hostinger VPS running Ubuntu 26.04.1 LTS, IdeaFlow in `/var/www/pos`, and `ideahub.service`.

## Scope

The `apt list --upgradable` screenshot from 2026-09-28 showed five pending updates:

| Package | Shown update | Why to check it |
| --- | --- | --- |
| `containerd.io` | `2.3.5` → `2.3.6` | Container runtime; updating it may affect any Docker/container workloads on this VPS. |
| `python3-distupgrade` | `1:26.04.23` → `1:26.04.25` | Ubuntu release-upgrade tooling. |
| `ubuntu-release-upgrader-core` | `1:26.04.23` → `1:26.04.25` | Ubuntu release-upgrade tooling. |
| `ubuntu-minimal` | `1.570.3` → `1.570.4` | Ubuntu base metapackage. |
| `ubuntu-standard` | `1.570.3` → `1.570.4` | Ubuntu standard metapackage. |

This is a **package update on the existing 26.04 release**. Installing `python3-distupgrade` or `ubuntu-release-upgrader-core` does not itself start an OS release upgrade. Do not run `do-release-upgrade` for this work. The login notice about two additional ESM Apps updates is separate from these five packages.

## 1. Before the maintenance window

1. Choose a quiet period and tell staff that the site or any container workload may briefly restart. Keep the current SSH session open until checks finish.
2. Confirm a recent, non-empty off-site MySQL backup for `pos_db` using the [Owner Maintenance Runbook](./OWNER_MAINTENANCE_RUNBOOK.md#manual-daily-off-site-backup). If none exists, create and verify one using that runbook.
3. In Hostinger hPanel, go to **VPS → Backups & Monitoring → Snapshots & Backups** and create a fresh snapshot. Wait until it is complete. Hostinger keeps one manual snapshot, so creating a new one replaces the old one. A snapshot is a whole-server recovery point; restoring it later overwrites newer database and file changes, so keep the separate MySQL backup too.
4. Record the current site state and package proposal on the VPS:

   ```bash
   date -Is
   lsb_release -ds
   sudo git -C /var/www/pos rev-parse --short HEAD
   sudo systemctl is-active ideahub nginx mysql redis-server
   curl --fail --silent --show-error http://127.0.0.1:5000/health/ready
   df -h /
   apt list --upgradable
   apt-mark showhold
   sudo apt-get -s upgrade
   ```

5. Check whether `containerd.io` supports anything active:

   ```bash
   systemctl is-active containerd docker
   if command -v docker >/dev/null 2>&1; then sudo docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'; fi
   ```

   An inactive or missing Docker service is not a reason to install Docker. If containers are running, record them and plan for their possible interruption. Stop before upgrading if their owner or restart behavior is unknown.

**Go/no-go:** Proceed only when the database backup and snapshot are verified, disk space is adequate, the site is healthy, and the simulated APT transaction shows understood changes. If new packages appear, packages are held back, or APT proposes removals, review that output before running the upgrade. Do not force phased updates.

## 2. Apply the updates

Run these in the maintenance window, one command at a time:

```bash
sudo apt update
apt list --upgradable
sudo apt upgrade
```

Read APT's final package list before answering its confirmation prompt. Continue only if it matches the reviewed update set and has no unexpected removals or service changes. Let APT finish; do not interrupt `dpkg` or close SSH during installation. If it prompts about a locally edited configuration file, inspect the diff before choosing a version.

`apt upgrade` may keep back a phased update. Record that result and leave it for a later maintenance window; do not override phasing just to make the count zero. This plan does not include `full-upgrade`, package purges, Python virtualenv updates, or an OS release upgrade.

## 3. Verify before closing the window

```bash
sudo dpkg --audit
apt list --upgradable
sudo systemctl is-active ideahub nginx mysql redis-server
systemctl is-active containerd docker
if command -v docker >/dev/null 2>&1; then sudo docker ps --format 'table {{.Names}}\t{{.Status}}'; fi
curl --fail --silent --show-error http://127.0.0.1:5000/health/live
curl --fail --silent --show-error http://127.0.0.1:5000/health/ready
curl --fail --silent --show-error https://idea-flows.online/health/ready
sudo journalctl -u ideahub -n 50 --no-pager
test -f /var/run/reboot-required && echo 'REBOOT REQUIRED' || echo 'NO REBOOT REQUESTED'
```

If the app was still starting when the first localhost `curl` ran, wait briefly and retry before treating that single failure as an outage. If a reboot is required, schedule it in the same window, reconnect, and repeat the service and health checks. Check that any previously running containers returned. From an authenticated browser, load the admin panel and the main staff workflow once.

**Done when:** `dpkg --audit` reports no broken packages, the expected packages are updated or explicitly recorded as phased/held, required services are active, both local and public readiness return `{"status":"ready"}`, and the normal login/workflow loads. Add the date, package versions, backup/snapshot reference, and verification result to the maintenance log in the Owner Maintenance Runbook.

## 4. If something fails

1. Keep SSH open. Record the exact APT error and inspect `sudo journalctl -u ideahub -n 100 --no-pager`, `sudo systemctl status nginx mysql redis-server containerd docker --no-pager`, and `sudo dpkg --audit` as relevant.
2. If APT was interrupted, diagnose the package state before using its suggested repair command. Do not immediately purge `containerd.io` or remove Docker data.
3. If only the app failed to start, diagnose its logs and dependencies before restarting `ideahub`. A Git rollback cannot undo an OS package update.
4. If the server cannot be recovered, use the verified Hostinger snapshot or backup as the last resort. **Restoring a snapshot overwrites everything changed after it was taken**, including live sales and bookings. Preserve any newer MySQL data first and plan its recovery from the separate database backup.

## References

- [Ubuntu Server: APT upgrades and phased updates](https://documentation.ubuntu.com/server/explanation/software/about-apt-upgrade-and-phased-updates/index.html)
- [Ubuntu Server: release upgrades (a different operation)](https://documentation.ubuntu.com/server/how-to/software/upgrade-your-release/index.html)
- [Docker: Docker Engine and `containerd.io` packages on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [Hostinger: VPS snapshots and backups](https://support.hostinger.com/en/articles/1583232-how-to-back-up-or-restore-a-vps)
